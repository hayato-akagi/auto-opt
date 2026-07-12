"""Generalization sweep orchestrator.

Trains one generation pipeline per level (each with its own bolt_model
distribution), then cross-evaluates every trained model against every level's
distribution to build a train x eval success-rate matrix. The diagonal shows
in-distribution performance; off-diagonal cells (especially "trained narrow,
evaluated wide") show the generalization gap referenced in
docs/19-generalization-experiment-plan.md.
"""

from __future__ import annotations

import asyncio
import logging
import zlib
from datetime import datetime, timezone

from .clients import ControllerClient, RecipeClient, TrainerClient
from .eval_runner import run_trial_batch
from .generation_manager import GenerationOrchestrator
from .models import (
    GeneralizationLevel,
    SweepCellResult,
    SweepCreateRequest,
    SweepLevelStatus,
)
from .storage import InMemoryJobStore

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cell_seed(train_level: str, eval_level: str) -> int:
    """Deterministic (not PYTHONHASHSEED-dependent) seed for one matrix cell."""
    return zlib.crc32(f"{train_level}:{eval_level}".encode()) % 1_000_000


class SweepOrchestrator:
    """Runs a generalization sweep: train N levels, then cross-evaluate N x N."""

    def __init__(
        self,
        *,
        controller_client: ControllerClient,
        trainer_client: TrainerClient,
        recipe_client: RecipeClient,
        sweeps_store: InMemoryJobStore,
        pipelines_store: InMemoryJobStore,
    ) -> None:
        self._controller = controller_client
        self._trainer = trainer_client
        self._recipe = recipe_client
        self._sweeps = sweeps_store
        self._pipelines = pipelines_store
        self._matrix_lock = asyncio.Lock()

    async def run(
        self,
        *,
        sweep_id: str,
        experiment_id: str,
        request: SweepCreateRequest,
    ) -> None:
        try:
            await self._recipe.get_experiment(experiment_id)

            levels = [
                SweepLevelStatus(name=lvl.name, pipeline_id=f"{sweep_id}__{lvl.name}")
                for lvl in request.levels
            ]
            self._sync_levels(sweep_id, levels)

            await self._train_levels(
                sweep_id=sweep_id,
                experiment_id=experiment_id,
                request=request,
                levels=levels,
            )

            trained_levels = [lvl for lvl in levels if lvl.model_path]
            if not trained_levels:
                self._sweeps.update(
                    sweep_id,
                    {
                        "status": "failed",
                        "finished_at": _now_iso(),
                        "error": "no level produced a trained model to evaluate",
                    },
                )
                return

            matrix = await self._evaluate_matrix(
                sweep_id=sweep_id,
                experiment_id=experiment_id,
                request=request,
                trained_levels=trained_levels,
            )

            any_level_failed = any(lvl.status == "failed" for lvl in levels)
            any_cell_failed = any(cell.status == "failed" for cell in matrix)
            final_status = (
                "completed_with_errors"
                if (any_level_failed or any_cell_failed)
                else "completed"
            )
            self._sweeps.update(sweep_id, {"status": final_status, "finished_at": _now_iso()})

        except Exception as exc:
            logger.error(f"[{sweep_id}] sweep failed: {exc}", exc_info=True)
            self._sweeps.update(
                sweep_id,
                {"status": "failed", "finished_at": _now_iso(), "error": str(exc)},
            )

    # ------------------------------------------------------------------
    # Phase 1: sequential training, one pipeline per level
    # ------------------------------------------------------------------

    async def _train_levels(
        self,
        *,
        sweep_id: str,
        experiment_id: str,
        request: SweepCreateRequest,
        levels: list[SweepLevelStatus],
    ) -> None:
        orchestrator = GenerationOrchestrator(
            controller_client=self._controller,
            trainer_client=self._trainer,
            recipe_client=self._recipe,
            store=self._pipelines,
        )

        for lvl_status, level in zip(levels, request.levels):
            lvl_status.status = "running"
            self._sync_levels(sweep_id, levels)

            level_config = request.base_config.model_copy(
                update={"bolt_distribution": level.bolt_distribution}
            )
            self._pipelines.create(
                lvl_status.pipeline_id,
                {
                    "pipeline_id": lvl_status.pipeline_id,
                    "experiment_id": experiment_id,
                    "status": "running",
                    "current_generation": 0,
                    "total_generations": level_config.n_generations,
                    "progress": 0.0,
                    "generations": [],
                    "started_at": _now_iso(),
                    "finished_at": None,
                    "error": None,
                },
            )

            # Awaited directly (not fire-and-forget): the sweep processes levels
            # one at a time so training load on trainer/controllers stays bounded.
            await orchestrator.run(
                pipeline_id=lvl_status.pipeline_id,
                experiment_id=experiment_id,
                config=level_config,
            )

            record = self._pipelines.get(lvl_status.pipeline_id) or {}
            generations = record.get("generations") or []
            last_gen = generations[-1] if generations else None
            if record.get("status") == "completed" and last_gen and last_gen.get("model_path"):
                lvl_status.status = "completed"
                lvl_status.model_path = last_gen["model_path"]
                lvl_status.train_success_rate = last_gen.get("success_rate")
            else:
                lvl_status.status = "failed"
                lvl_status.error = (
                    record.get("error")
                    or "no trained model produced (base_config.n_generations must be >= 2)"
                )
            self._sync_levels(sweep_id, levels)

    def _sync_levels(self, sweep_id: str, levels: list[SweepLevelStatus]) -> None:
        self._sweeps.update(sweep_id, {"levels": [lvl.model_dump() for lvl in levels]})

    # ------------------------------------------------------------------
    # Phase 2: cross-evaluation matrix (train_level x eval_level)
    # ------------------------------------------------------------------

    async def _evaluate_matrix(
        self,
        *,
        sweep_id: str,
        experiment_id: str,
        request: SweepCreateRequest,
        trained_levels: list[SweepLevelStatus],
    ) -> list[SweepCellResult]:
        eval_levels: list[GeneralizationLevel] = request.levels
        matrix: list[SweepCellResult] = []
        semaphore = asyncio.Semaphore(request.max_concurrent_eval_cells)

        async def _run_cell(train_lvl: SweepLevelStatus, eval_lvl: GeneralizationLevel) -> None:
            async with semaphore:
                cell = SweepCellResult(
                    train_level=train_lvl.name, eval_level=eval_lvl.name, status="running"
                )
                try:
                    result = await run_trial_batch(
                        controller_client=self._controller,
                        experiment_id=experiment_id,
                        algorithm=request.base_config.gen1plus_controller,
                        controller_config=request.base_config.controller_config,
                        target=request.base_config.target,
                        initial_coll=request.base_config.initial_coll,
                        max_steps=request.base_config.max_steps,
                        tolerance=request.base_config.tolerance,
                        n_envs=request.eval_n_envs,
                        trials_per_env=request.eval_trials_per_env,
                        base_seed=_cell_seed(train_lvl.name, eval_lvl.name),
                        model_path=train_lvl.model_path,
                        n_history=request.base_config.model_config_train.n_history,
                        bolt_distribution=eval_lvl.bolt_distribution,
                    )
                    cell.status = "completed"
                    cell.total_trials = result.total_trials
                    cell.converged_trials = result.converged_trials
                    cell.success_rate = (
                        result.converged_trials / result.total_trials
                        if result.total_trials > 0
                        else 0.0
                    )
                    cell.final_distances = result.final_distances
                except Exception as exc:
                    cell.status = "failed"
                    cell.error = str(exc)

                async with self._matrix_lock:
                    matrix.append(cell)
                    self._sweeps.update(sweep_id, {"matrix": [c.model_dump() for c in matrix]})

        cells = [
            (train_lvl, eval_lvl) for train_lvl in trained_levels for eval_lvl in eval_levels
        ]
        await asyncio.gather(*[_run_cell(t, e) for t, e in cells])
        return matrix
