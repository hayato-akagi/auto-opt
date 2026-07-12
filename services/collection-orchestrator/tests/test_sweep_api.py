from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


class FakeControllerClient:
    async def close(self) -> None:
        return None

    async def run_control(self, algorithm: str, payload: dict) -> dict:
        await asyncio.sleep(0)
        return {
            "trial_id": f"trial_{payload['random_seed']:03d}",
            "converged": True,
            "steps": 2,
            "final_distance": 0.01,
        }


class FakeRecipeClient:
    async def close(self) -> None:
        return None

    async def get_experiment(self, experiment_id: str) -> dict:
        await asyncio.sleep(0)
        return {"experiment_id": experiment_id}


class FakeTrainerClient:
    def __init__(self) -> None:
        self._counter = 0

    async def close(self) -> None:
        return None

    async def start_training(self, payload: dict) -> dict:
        await asyncio.sleep(0)
        self._counter += 1
        return {"train_job_id": f"train_job_{self._counter:03d}"}

    async def get_job(self, train_job_id: str) -> dict:
        await asyncio.sleep(0)
        return {
            "status": "completed",
            "train_metrics": {"final_train_loss": 0.0001, "epoch_losses": [0.001, 0.0001]},
        }


def _sweep_payload() -> dict:
    def level(name: str, x0_bias_x: tuple[float, float]) -> dict:
        return {
            "name": name,
            "bolt_distribution": {
                "upper": {
                    "x0_bias_x": list(x0_bias_x),
                    "a_x": [0.01, 0.01],
                    "b_x": [1.0, 1.0],
                },
                "lower": {},
                "seed": 0,
            },
        }

    return {
        "experiment_id": "exp_001",
        "base_config": {
            "gen0_controller": "simple-controller",
            "gen1plus_controller": "lstm-controller",
            "n_parallel_envs": 2,
            "trials_per_env": 1,
            "n_generations": 2,
            "max_steps": 2,
            "tolerance": 0.05,
            "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
            "poll_interval_sec": 0.01,
            "train_timeout_sec": 5.0,
        },
        "levels": [level("G0", (0.0, 0.0)), level("G1", (0.0, 0.1))],
        "eval_n_envs": 2,
        "eval_trials_per_env": 1,
        "max_concurrent_eval_cells": 5,
    }


@pytest.mark.asyncio
async def test_sweep_trains_each_level_and_builds_matrix() -> None:
    app = create_app(
        controller_client=FakeControllerClient(),
        recipe_client=FakeRecipeClient(),
        trainer_client=FakeTrainerClient(),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_res = await client.post("/sweeps", json=_sweep_payload())
        assert create_res.status_code == 202
        sweep_id = create_res.json()["sweep_id"]

        body = {}
        for _ in range(200):
            get_res = await client.get(f"/sweeps/{sweep_id}")
            assert get_res.status_code == 200
            body = get_res.json()
            if body["status"] != "running":
                break
            await asyncio.sleep(0.02)

        assert body["status"] == "completed"
        assert len(body["levels"]) == 2
        for level in body["levels"]:
            assert level["status"] == "completed"
            assert level["model_path"]
            assert level["train_success_rate"] == pytest.approx(1.0)

        # 2 trained levels x 2 eval levels = 4 cells
        assert len(body["matrix"]) == 4
        for cell in body["matrix"]:
            assert cell["status"] == "completed"
            assert cell["success_rate"] == pytest.approx(1.0)
            assert cell["total_trials"] == 2


@pytest.mark.asyncio
async def test_sweep_not_found() -> None:
    app = create_app(
        controller_client=FakeControllerClient(),
        recipe_client=FakeRecipeClient(),
        trainer_client=FakeTrainerClient(),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/sweeps/does-not-exist")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_sweep_requires_at_least_two_levels() -> None:
    app = create_app(
        controller_client=FakeControllerClient(),
        recipe_client=FakeRecipeClient(),
        trainer_client=FakeTrainerClient(),
    )
    payload = _sweep_payload()
    payload["levels"] = payload["levels"][:1]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/sweeps", json=payload)
    assert res.status_code == 422
