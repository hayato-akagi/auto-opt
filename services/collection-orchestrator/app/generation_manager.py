"""Generation pipeline orchestrator.

Runs alternating collection (simple/ai-controller) and training phases.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from .clients import ControllerClient, RecipeClient, TrainerClient
from .eval_runner import run_trial_batch
from .models import (
    GenerationResult,
    PipelineConfig,
)
from .storage import InMemoryJobStore

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
                    total, converged, steps_list, dist_list, trial_ids, converged_flags = (
                        await self._run_collection(
                            gen_id=gen_id,
                            experiment_id=experiment_id,
                            controller=controller,
                            model_path=last_model_path,
                            config=config,
                        )
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
                gen.converged_flags = converged_flags

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
    ) -> tuple[int, int, list[int], list[float], list[str], list[bool]]:
        """Run collection phase.

        Returns:
            (total_trials, converged_trials, steps_per_trial, final_distances,
             trial_ids, converged_flags)
            final_distances, trial_ids, and converged_flags are aligned by
            index (one entry per trial that actually produced a trial_id).

        Env sampling (when config.bolt_distribution is set) is deterministic in
        (seed, n_envs), so calling run_trial_batch fresh each generation yields
        the same envs every time rather than needing to precompute them once.
        """
        result = await run_trial_batch(
            controller_client=self._controller,
            experiment_id=experiment_id,
            algorithm=controller,
            controller_config=config.controller_config,
            target=config.target,
            initial_coll=config.initial_coll,
            max_steps=config.max_steps,
            tolerance=config.tolerance,
            n_envs=config.n_parallel_envs,
            trials_per_env=config.trials_per_env,
            base_seed=gen_id * 10_000,
            model_path=model_path,
            n_history=config.model_config_train.n_history,
            adaptive_alpha=config.adaptive_alpha,
            bolt_distribution=config.bolt_distribution,
            initial_coll_range_x=config.initial_coll_range_x,
            initial_coll_range_y=config.initial_coll_range_y,
        )
        return (
            result.total_trials,
            result.converged_trials,
            result.steps_per_trial,
            result.final_distances,
            result.trial_ids,
            result.converged_flags,
        )

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
