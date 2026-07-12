from __future__ import annotations

import asyncio

import pytest

from app.env_sampling import sample_envs
from app.eval_runner import run_trial_batch
from app.models import BoltModelDistribution, BoltUnitRange, ControllerConfig, InitialColl, TargetSpot


class RecordingControllerClient:
    """Fake controller client that records payloads and can fail on demand."""

    def __init__(self, fail_seeds: set[int] | None = None) -> None:
        self.fail_seeds = fail_seeds or set()
        self.payloads: list[dict] = []

    async def run_control(self, algorithm: str, payload: dict) -> dict:
        await asyncio.sleep(0)
        self.payloads.append(payload)
        if payload["random_seed"] in self.fail_seeds:
            raise RuntimeError("simulated downstream failure")
        return {
            "trial_id": f"trial_{payload['random_seed']}",
            "converged": True,
            "steps": 3,
            "final_distance": 0.01,
        }


def _controller_config() -> ControllerConfig:
    return ControllerConfig()


@pytest.mark.asyncio
async def test_run_trial_batch_counts_all_trials() -> None:
    client = RecordingControllerClient()
    result = await run_trial_batch(
        controller_client=client,
        experiment_id="exp_1",
        algorithm="simple-controller",
        controller_config=_controller_config(),
        target=TargetSpot(spot_center_x=0.0, spot_center_y=0.0),
        initial_coll=InitialColl(),
        max_steps=5,
        tolerance=0.05,
        n_envs=3,
        trials_per_env=2,
        base_seed=0,
    )
    assert result.total_trials == 6
    assert result.converged_trials == 6
    assert len(result.trial_ids) == 6
    assert len(result.final_distances) == 6
    assert len(client.payloads) == 6


@pytest.mark.asyncio
async def test_run_trial_batch_excludes_failed_trials_from_aligned_lists() -> None:
    client = RecordingControllerClient(fail_seeds={0, 2})
    result = await run_trial_batch(
        controller_client=client,
        experiment_id="exp_1",
        algorithm="simple-controller",
        controller_config=_controller_config(),
        target=TargetSpot(spot_center_x=0.0, spot_center_y=0.0),
        initial_coll=InitialColl(),
        max_steps=5,
        tolerance=0.05,
        n_envs=4,
        trials_per_env=1,
        base_seed=0,
    )
    assert result.total_trials == 4
    # Two trials raised, so only 2 made it into the aligned lists.
    assert len(result.trial_ids) == 2
    assert len(result.final_distances) == 2
    assert len(result.converged_flags) == 2


@pytest.mark.asyncio
async def test_run_trial_batch_passes_bolt_override_round_robin() -> None:
    client = RecordingControllerClient()
    dist = BoltModelDistribution(
        upper=BoltUnitRange(a_x=(-0.2, 0.2)),
        lower=BoltUnitRange(),
        seed=0,
    )
    expected_envs = sample_envs(dist, 2)
    await run_trial_batch(
        controller_client=client,
        experiment_id="exp_1",
        algorithm="lstm-controller",
        controller_config=_controller_config(),
        target=TargetSpot(spot_center_x=0.0, spot_center_y=0.0),
        initial_coll=InitialColl(),
        max_steps=5,
        tolerance=0.05,
        n_envs=2,
        trials_per_env=2,
        base_seed=0,
        model_path="/app/models/x.pt",
        bolt_distribution=dist,
    )
    # 2 envs x 2 trials_per_env = 4 trials, round-robin env_idx = trial_idx // trials_per_env
    overrides = [p["bolt_model_override"] for p in client.payloads]
    assert overrides[0] == overrides[1] == expected_envs[0]  # both from env 0
    assert overrides[2] == overrides[3] == expected_envs[1]  # both from env 1
    # model routing injected model_type/model_path for lstm-controller
    assert all(p["config"]["model_type"] == "lstm" for p in client.payloads)
    assert all(p["config"]["model_path"] == "/app/models/x.pt" for p in client.payloads)
