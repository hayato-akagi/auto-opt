"""Generation pipeline orchestrator.

Runs alternating collection (simple/ai-controller) and training phases.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any

from .clients import ControllerClient, RecipeClient, TrainerClient
from .models import (
    BoltModelDistribution,
    GenerationResult,
    PipelineConfig,
)
from .storage import InMemoryJobStore

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sample_range(rng: random.Random, lo_hi: tuple[float, float]) -> float:
    lo, hi = lo_hi
    if lo == hi:
        return float(lo)
    return rng.uniform(float(lo), float(hi))


def _sample_bolt_unit(rng: random.Random, unit) -> dict[str, float]:
    return {
        "x0_bias_x": _sample_range(rng, unit.x0_bias_x),
        "x0_bias_y": _sample_range(rng, unit.x0_bias_y),
        "a_x": _sample_range(rng, unit.a_x),
        "b_x": _sample_range(rng, unit.b_x),
        "a_y": _sample_range(rng, unit.a_y),
        "b_y": _sample_range(rng, unit.b_y),
        "noise_ratio_min_x": unit.noise_ratio_min_x,
        "noise_ratio_max_x": unit.noise_ratio_max_x,
        "noise_ratio_min_y": unit.noise_ratio_min_y,
        "noise_ratio_max_y": unit.noise_ratio_max_y,
    }


def _sample_envs(
    distribution: BoltModelDistribution,
    n_envs: int,
) -> list[dict[str, Any]]:
    """Deterministically sample n_envs bolt_model dicts from the distribution."""
    rng = random.Random(distribution.seed)
    envs: list[dict[str, Any]] = []
    for _ in range(n_envs):
        envs.append({
            "upper": _sample_bolt_unit(rng, distribution.upper),
            "lower": _sample_bolt_unit(rng, distribution.lower),
        })
    return envs


class GenerationOrchestrator:
    """Manages a multi-generation collection + training pipeline."""

    def __init__(
        self,
        *,
        controller_client: ControllerClient,
        trainer_client: TrainerClient,
        recipe_client: RecipeClient,
        store: InMemoryJobStore,
        # Path inside the trainer container where models are saved.
        # Same path must be mounted (shared volume) into ai-controller as model_path.
        trainer_model_dir: str = "/app/models",
    ) -> None:
        self._controller = controller_client
        self._trainer = trainer_client
        self._recipe = recipe_client
        self._store = store
        self._trainer_model_dir = trainer_model_dir.rstrip("/")

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------

    async def run(
        self,
        *,
        pipeline_id: str,
        experiment_id: str,
        config: PipelineConfig,
    ) -> None:
        """Run the full pipeline, persisting status into the store."""
        try:
            # Verify experiment exists
            await self._recipe.get_experiment(experiment_id)

            # Pre-sample environments (bolt_model variants) once per pipeline
            envs: list[dict[str, Any]] | None = None
            if config.bolt_distribution is not None:
                envs = _sample_envs(config.bolt_distribution, config.n_parallel_envs)
                logger.info(
                    f"[{pipeline_id}] sampled {len(envs)} envs from bolt_distribution"
                )

            generations: list[GenerationResult] = []
            self._update(pipeline_id, generations=generations, status="running")

            last_model_path: str | None = None
            consecutive_success = 0

            for gen_id in range(config.n_generations):
                controller = config.gen0_controller if gen_id == 0 else config.gen1plus_controller
                gen = GenerationResult(
                    gen_id=gen_id,
                    status="collecting",
                    controller=controller,
                    model_path=last_model_path,
                    started_at=_now_iso(),
                )
                generations.append(gen)
                self._update(
                    pipeline_id,
                    generations=generations,
                    current_generation=gen_id,
                    progress=gen_id / max(config.n_generations, 1),
                )

                # 1) Collection phase
                try:
                    total, converged, steps_list, dist_list, trial_ids = await self._run_collection(
                        gen_id=gen_id,
                        experiment_id=experiment_id,
                        controller=controller,
                        model_path=last_model_path,
                        config=config,
                        envs=envs,
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    gen.status = "failed"
                    gen.error = f"collection failed: {exc}"
                    gen.finished_at = _now_iso()
                    self._update(pipeline_id, generations=generations, status="failed",
                                 finished_at=_now_iso(), error=gen.error)
                    return

                gen.total_trials = total
                gen.converged_trials = converged
                gen.success_rate = (converged / total) if total > 0 else 0.0
                gen.steps_per_trial = steps_list
                gen.final_distances = dist_list
                gen.trial_ids = trial_ids

                # 2) Training phase (skip on last gen)
                if gen_id < config.n_generations - 1:
                    gen.status = "training"
                    self._update(pipeline_id, generations=generations)
                    try:
                        train_job_id, final_loss, epoch_losses = await self._run_training(
                            experiment_id=experiment_id,
                            config=config,
                            init_from_model_path=last_model_path if config.model_config_train.warm_start else None,
                        )
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.error(
                            f"[{pipeline_id}] gen{gen_id} training failed: "
                            f"{type(exc).__name__}: {exc!r}",
                            exc_info=True,
                        )
                        gen.status = "failed"
                        gen.error = f"training failed: {type(exc).__name__}: {exc!r}"
                        gen.finished_at = _now_iso()
                        self._update(pipeline_id, generations=generations, status="failed",
                                     finished_at=_now_iso(), error=gen.error)
                        return

                    gen.train_job_id = train_job_id
                    gen.final_train_loss = final_loss
                    gen.epoch_losses = epoch_losses
                    gen.model_path = f"{self._trainer_model_dir}/{train_job_id}.pt"
                    last_model_path = gen.model_path

                gen.status = "completed"
                gen.finished_at = _now_iso()
                self._update(pipeline_id, generations=generations)

                # 3) Early stopping
                if gen.success_rate is not None and gen.success_rate >= config.stopping.target_success_rate:
                    consecutive_success += 1
                else:
                    consecutive_success = 0
                if consecutive_success >= config.stopping.early_stopping_patience:
                    logger.info(
                        f"[{pipeline_id}] early stop at gen {gen_id} "
                        f"({consecutive_success} consecutive successes)"
                    )
                    break

            self._update(
                pipeline_id,
                generations=generations,
                status="completed",
                current_generation=len(generations),
                progress=1.0,
                finished_at=_now_iso(),
            )

        except Exception as exc:
            logger.error(f"[{pipeline_id}] pipeline failed: {exc}", exc_info=True)
            self._update(
                pipeline_id,
                status="failed",
                finished_at=_now_iso(),
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_collection(
        self,
        *,
        gen_id: int,
        experiment_id: str,
        controller: str,
        model_path: str | None,
        config: PipelineConfig,
        envs: list[dict[str, Any]] | None,
    ) -> tuple[int, int, list[int], list[float], list[str]]:
        """Run collection phase.

        Returns:
            (total_trials, converged_trials, steps_per_trial, final_distances)
        """
        n_total = config.n_parallel_envs * config.trials_per_env
        base_seed = gen_id * 10_000

        # Build per-controller config payload
        ctrl_config: dict[str, Any] = config.controller_config.model_dump()
        if controller == "ai-controller":
            ctrl_config["model_type"] = "mlp"
            ctrl_config["model_path"] = model_path
            ctrl_config["n_history"] = config.model_config_train.n_history
        elif controller == "lstm-controller":
            ctrl_config["model_type"] = "lstm"
            ctrl_config["model_path"] = model_path
        elif controller == "adaptive-controller":
            ctrl_config["alpha"] = config.adaptive_alpha

        semaphore = asyncio.Semaphore(max(1, config.n_parallel_envs))

        async def _one(trial_idx: int) -> dict[str, Any]:
            env_idx = trial_idx // config.trials_per_env  # round-robin per env
            bolt_override = envs[env_idx] if envs is not None else None

            # Randomize initial coll position per trial using a separate seed namespace
            # to avoid correlation with the controller's random_seed.
            if config.initial_coll_range_x > 0.0 or config.initial_coll_range_y > 0.0:
                init_rng = random.Random(base_seed + trial_idx + 1_000_000)
                initial_coll = {
                    "coll_x": config.initial_coll.coll_x + init_rng.uniform(
                        -config.initial_coll_range_x, config.initial_coll_range_x
                    ),
                    "coll_y": config.initial_coll.coll_y + init_rng.uniform(
                        -config.initial_coll_range_y, config.initial_coll_range_y
                    ),
                }
            else:
                initial_coll = config.initial_coll.model_dump()

            payload = {
                "experiment_id": experiment_id,
                "algorithm": controller,
                "config": ctrl_config,
                "target": config.target.model_dump(),
                "initial_coll": initial_coll,
                "max_steps": config.max_steps,
                "tolerance": config.tolerance,
                "random_seed": base_seed + trial_idx,
                "bolt_model_override": bolt_override,
            }
            async with semaphore:
                try:
                    return await self._controller.run_control(controller, payload)
                except Exception as exc:
                    return {"error": str(exc), "converged": False}

        results = await asyncio.gather(*[_one(i) for i in range(n_total)])

        converged = sum(1 for r in results if r.get("converged"))
        steps_list = [int(r.get("steps") or 0) for r in results]
        dist_list = [
            float(r["final_distance"])
            for r in results
            if isinstance(r.get("final_distance"), (int, float))
        ]
        trial_ids = [str(r["trial_id"]) for r in results if r.get("trial_id")]
        return n_total, converged, steps_list, dist_list, trial_ids

    async def _run_training(
        self,
        *,
        experiment_id: str,
        config: PipelineConfig,
        init_from_model_path: str | None,
    ) -> tuple[str, float | None, list[float]]:
        """Run training. Polls until completion.

        Returns:
            (train_job_id, final_loss, epoch_losses)
        """
        m = config.model_config_train
        all_experiment_ids = [experiment_id] + list(config.extra_experiment_ids)
        model_type = "lstm" if config.gen1plus_controller == "lstm-controller" else "mlp"
        payload: dict[str, Any] = {
            "experiment_ids": all_experiment_ids,
            "model_type": model_type,
            "epochs": m.epochs,
            "batch_size": m.batch_size,
            "n_history": m.n_history,
            "hidden_dim": m.hidden_dim,
            "num_layers": m.num_layers,
            "learning_rate": m.learning_rate,
            "only_converged": m.only_converged,
        }
        if init_from_model_path:
            payload["init_from_model_path"] = init_from_model_path

        started = await self._trainer.start_training(payload)
        train_job_id = started["train_job_id"]

        # Poll, tolerating transient network errors
        deadline = asyncio.get_event_loop().time() + config.train_timeout_sec
        consecutive_errors = 0
        max_consecutive_errors = 5
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(config.poll_interval_sec)
            try:
                status = await self._trainer.get_job(train_job_id)
            except Exception as exc:
                consecutive_errors += 1
                logger.warning(
                    f"poll error for {train_job_id} "
                    f"({consecutive_errors}/{max_consecutive_errors}): "
                    f"{type(exc).__name__}: {exc!r}"
                )
                if consecutive_errors >= max_consecutive_errors:
                    raise RuntimeError(
                        f"trainer poll failed {consecutive_errors} times for {train_job_id}: "
                        f"{type(exc).__name__}: {exc!r}"
                    ) from exc
                continue
            consecutive_errors = 0
            s = status.get("status")
            if s == "completed":
                metrics = status.get("train_metrics") or {}
                return (
                    train_job_id,
                    metrics.get("final_train_loss"),
                    list(metrics.get("epoch_losses") or []),
                )
            if s == "failed":
                raise RuntimeError(
                    f"trainer job {train_job_id} failed: "
                    f"{status.get('error_message') or '<no message>'}"
                )
        raise TimeoutError(f"training job {train_job_id} timed out")

    def _update(self, pipeline_id: str, **fields: Any) -> None:
        """Helper to update store entry. Converts GenerationResult list to dicts."""
        if "generations" in fields:
            fields["generations"] = [g.model_dump() for g in fields["generations"]]
        self._store.update(pipeline_id, fields)
