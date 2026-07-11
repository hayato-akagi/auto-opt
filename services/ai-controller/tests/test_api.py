from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


class FakeRecipeClient:
    def __init__(self) -> None:
        self.step_calls: list[tuple[float, float, dict | None]] = []

    async def close(self) -> None:
        return None

    async def create_trial(self, experiment_id: str, control: dict) -> dict:
        assert experiment_id == "exp_001"
        assert control["algorithm"] == "ai-controller"
        return {"trial_id": "trial_001"}

    async def execute_step(
        self,
        experiment_id: str,
        trial_id: str,
        coll_x: float,
        coll_y: float,
        *,
        ai_step_log: dict | None = None,
        observed_spot_x: float | None = None,
        observed_spot_y: float | None = None,
    ) -> dict:
        self.step_calls.append((coll_x, coll_y, ai_step_log))

        if len(self.step_calls) == 1:
            return {
                "step_index": 0,
                "sim_after_position": {
                    "spot_center_x": 0.1,
                    "spot_center_y": -0.1,
                    "spot_rms_radius": 0.01,
                },
                "sim_after_bolt": {
                    "spot_center_x": 0.2,
                    "spot_center_y": -0.2,
                    "spot_rms_radius": 0.02,
                },
            }

        return {
            "step_index": len(self.step_calls) - 1,
            "sim_after_position": {
                "spot_center_x": 0.001,
                "spot_center_y": -0.001,
                "spot_rms_radius": 0.005,
            },
            "sim_after_bolt": {
                "spot_center_x": 0.0002,
                "spot_center_y": -0.0001,
                "spot_rms_radius": 0.004,
            },
        }

    async def complete_trial(self, experiment_id: str, trial_id: str) -> dict:
        return {"trial_id": trial_id}


@pytest.mark.asyncio
async def test_health() -> None:
    app = create_app(recipe_client=FakeRecipeClient())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_model_status_and_reload() -> None:
    app = create_app(recipe_client=FakeRecipeClient())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status_res = await client.get("/model/status")
        reload_res = await client.post("/model/reload")

    assert status_res.status_code == 200
    assert "model_type" in status_res.json()
    assert reload_res.status_code == 200
    assert "loaded_version" in reload_res.json()


@pytest.mark.asyncio
async def test_control_run_endpoint() -> None:
    fake = FakeRecipeClient()
    app = create_app(recipe_client=fake)

    payload = {
        "experiment_id": "exp_001",
        "algorithm": "ai-controller",
        "config": {
            "model_type": "baseline_only",
            "model_version": "v0",
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.05,
            "delta_clip_y": 0.05,
            "coll_x_min": -0.5,
            "coll_x_max": 0.5,
            "coll_y_min": -0.5,
            "coll_y_max": 0.5,
            "safety_threshold": 0.5,
            "safety_bias": 0.01,
            "release_perturbation": {"std_x": 0.0, "std_y": 0.0},
        },
        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
        "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
        "max_steps": 5,
        "tolerance": 0.01,
        "random_seed": 1,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/control/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["trial_id"] == "trial_001"
    assert body["algorithm"] == "ai-controller"
    assert body["model_type"] == "baseline_only"
    assert body["steps"] == 1
    assert len(fake.step_calls) == 2
    # 2nd call is control step and should contain ai_step_log
    assert fake.step_calls[1][2] is not None
    assert fake.step_calls[1][2]["model_version"] == "v0"


@pytest.mark.asyncio
async def test_unsupported_algorithm_returns_422() -> None:
    app = create_app(recipe_client=FakeRecipeClient())

    payload = {
        "experiment_id": "exp_001",
        "algorithm": "simple-controller",
        "config": {"model_type": "baseline_only"},
        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
        "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
        "max_steps": 1,
        "tolerance": 0.01,
        "random_seed": 1,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/control/run", json=payload)

    assert response.status_code == 422
