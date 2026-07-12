"""Shared trial-batch execution: env sampling -> parallel controller calls -> aggregation.

Used by both the generation pipeline's collection phase (generation_manager.py) and
the generalization sweep's held-out evaluation phase (sweep_manager.py), so that
training and evaluation runs always go through the same "sample envs, run trials,
aggregate" code path.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any

from .clients import ControllerClient
from .env_sampling import sample_envs
from .models import BoltModelDistribution, ControllerConfig, InitialColl, TargetSpot


@dataclass
class TrialBatchResult:
    total_trials: int
    converged_trials: int
    steps_per_trial: list[int] = field(default_factory=list)
    final_distances: list[float] = field(default_factory=list)
    trial_ids: list[str] = field(default_factory=list)
    converged_flags: list[bool] = field(default_factory=list)


async def run_trial_batch(
    *,
    controller_client: ControllerClient,
    experiment_id: str,
    algorithm: str,
    controller_config: ControllerConfig,
    target: TargetSpot,
    initial_coll: InitialColl,
    max_steps: int,
    tolerance: float,
    n_envs: int,
    trials_per_env: int,
    base_seed: int,
    model_path: str | None = None,
    n_history: int | None = None,
    adaptive_alpha: float | None = None,
    bolt_distribution: BoltModelDistribution | None = None,
    initial_coll_range_x: float = 0.0,
    initial_coll_range_y: float = 0.0,
    max_concurrency: int | None = None,
) -> TrialBatchResult:
    """Run n_envs * trials_per_env trials against `algorithm` and aggregate results.

    envs, trial_ids, final_distances, and converged_flags are aligned by index
    (one entry per trial that actually produced a trial_id). Trials whose
    controller call raised (timeout, downstream error, ...) are excluded from
    those three lists but still counted in total_trials/steps_per_trial.
    """
    n_total = n_envs * trials_per_env
    envs = sample_envs(bolt_distribution, n_envs) if bolt_distribution is not None else None

    ctrl_config: dict[str, Any] = controller_config.model_dump()
    if algorithm == "ai-controller":
        ctrl_config["model_type"] = "mlp"
        ctrl_config["model_path"] = model_path
        if n_history is not None:
            ctrl_config["n_history"] = n_history
    elif algorithm == "lstm-controller":
        ctrl_config["model_type"] = "lstm"
        ctrl_config["model_path"] = model_path
    elif algorithm == "adaptive-controller" and adaptive_alpha is not None:
        ctrl_config["alpha"] = adaptive_alpha

    semaphore = asyncio.Semaphore(max(1, max_concurrency or n_envs))

    async def _one(trial_idx: int) -> dict[str, Any]:
        env_idx = trial_idx // trials_per_env
        bolt_override = envs[env_idx] if envs is not None else None

        if initial_coll_range_x > 0.0 or initial_coll_range_y > 0.0:
            init_rng = random.Random(base_seed + trial_idx + 1_000_000)
            initial_coll_payload = {
                "coll_x": initial_coll.coll_x + init_rng.uniform(
                    -initial_coll_range_x, initial_coll_range_x
                ),
                "coll_y": initial_coll.coll_y + init_rng.uniform(
                    -initial_coll_range_y, initial_coll_range_y
                ),
            }
        else:
            initial_coll_payload = initial_coll.model_dump()

        payload = {
            "experiment_id": experiment_id,
            "algorithm": algorithm,
            "config": ctrl_config,
            "target": target.model_dump(),
            "initial_coll": initial_coll_payload,
            "max_steps": max_steps,
            "tolerance": tolerance,
            "random_seed": base_seed + trial_idx,
            "bolt_model_override": bolt_override,
        }
        async with semaphore:
            try:
                return await controller_client.run_control(algorithm, payload)
            except Exception as exc:
                return {"error": str(exc), "converged": False}

    results = await asyncio.gather(*[_one(i) for i in range(n_total)])

    converged = sum(1 for r in results if r.get("converged"))
    steps_list = [int(r.get("steps") or 0) for r in results]

    trial_records = [r for r in results if r.get("trial_id")]
    trial_ids = [str(r["trial_id"]) for r in trial_records]
    dist_list = [float(r["final_distance"]) for r in trial_records]
    converged_flags = [bool(r.get("converged")) for r in trial_records]

    return TrialBatchResult(
        total_trials=n_total,
        converged_trials=converged,
        steps_per_trial=steps_list,
        final_distances=dist_list,
        trial_ids=trial_ids,
        converged_flags=converged_flags,
    )
