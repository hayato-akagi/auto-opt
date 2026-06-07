"""API integration tests for lstm-controller."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.model import BoltShiftLSTM, ModelManager
from app.models import ControlRunResponse

BOLT_SHIFT_X = 0.02
BOLT_SHIFT_Y = -0.01


def _make_mm_with_lstm() -> ModelManager:
    mm = ModelManager(model_type="baseline_only")
    model = BoltShiftLSTM(input_dim=8, hidden_dim=32, num_layers=1)
    model.eval()
    mm._model = model
    mm._model_type = "lstm"
    return mm


class FakeRecipeClient:
    def __init__(self) -> None:
        self.step_calls: list[tuple[float, float]] = []

    async def close(self) -> None:
        pass

    async def create_trial(self, experiment_id: str, control: dict, **kwargs) -> dict:
        assert experiment_id == "exp_001"
        assert control["algorithm"] == "lstm-controller"
        return {"trial_id": "trial_lstm_001"}

    async def execute_step(
        self, experiment_id: str, trial_id: str, coll_x: float, coll_y: float, **kwargs
    ) -> dict:
        self.step_calls.append((coll_x, coll_y))
        call_index = len(self.step_calls)

        # All steps: near-target to force convergence after 1 step
        return {
            "step_index": call_index - 1,
            "command": {"coll_x": coll_x, "coll_y": coll_y},
            "sim_after_position": {
                "spot_center_x": 0.0003,
                "spot_center_y": -0.0002,
                "spot_rms_radius": 0.005,
            },
            "sim_after_bolt": {
                "spot_center_x": 0.0003 + BOLT_SHIFT_X,
                "spot_center_y": -0.0002 + BOLT_SHIFT_Y,
                "spot_rms_radius": 0.005,
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
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "lstm-controller"


@pytest.mark.asyncio
async def test_model_status() -> None:
    mm = _make_mm_with_lstm()
    app = create_app(recipe_client=FakeRecipeClient(), model_manager=mm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/model/status")
    assert response.status_code == 200
    assert response.json()["model_type"] == "lstm"


@pytest.mark.asyncio
async def test_control_run_baseline_only() -> None:
    fake = FakeRecipeClient()
    app = create_app(recipe_client=fake)
    payload = {
        "experiment_id": "exp_001",
        "algorithm": "lstm-controller",
        "config": {
            "model_type": "baseline_only",
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.05,
            "delta_clip_y": 0.05,
            "coll_x_min": -0.5, "coll_x_max": 0.5,
            "coll_y_min": -0.5, "coll_y_max": 0.5,
            "safety_threshold": 0.5,
            "safety_bias": 0.01,
            "release_perturbation": {"std_x": 0.0, "std_y": 0.0},
        },
        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
        "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
        "max_steps": 5,
        "tolerance": 0.1,
        "random_seed": 42,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/control/run", json=payload)
    assert response.status_code == 200
    body = ControlRunResponse.model_validate(response.json())
    assert body.trial_id == "trial_lstm_001"
    assert body.algorithm == "lstm-controller"
    assert body.converged is True
    assert len(fake.step_calls) >= 2  # step0 + at least 1


@pytest.mark.asyncio
async def test_control_run_with_lstm_model() -> None:
    fake = FakeRecipeClient()
    mm = _make_mm_with_lstm()
    app = create_app(recipe_client=fake, model_manager=mm)
    payload = {
        "experiment_id": "exp_001",
        "algorithm": "lstm-controller",
        "config": {
            "model_type": "lstm",
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.05,
            "delta_clip_y": 0.05,
            "coll_x_min": -0.5, "coll_x_max": 0.5,
            "coll_y_min": -0.5, "coll_y_max": 0.5,
            "safety_threshold": 0.5,
            "safety_bias": 0.01,
            "release_perturbation": {"std_x": 0.0, "std_y": 0.0},
        },
        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
        "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
        "max_steps": 5,
        "tolerance": 0.1,
        "random_seed": 0,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/control/run", json=payload)
    assert response.status_code == 200
    body = ControlRunResponse.model_validate(response.json())
    assert body.model_type == "lstm"
    assert body.converged is True


@pytest.mark.asyncio
async def test_unsupported_algorithm_returns_422() -> None:
    app = create_app(recipe_client=FakeRecipeClient())
    payload = {
        "experiment_id": "exp_001",
        "algorithm": "ai-controller",  # wrong
        "config": {
            "model_type": "baseline_only",
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.05,
            "delta_clip_y": 0.05,
            "coll_x_min": -0.5, "coll_x_max": 0.5,
            "coll_y_min": -0.5, "coll_y_max": 0.5,
            "safety_threshold": 0.5,
            "safety_bias": 0.01,
            "release_perturbation": {"std_x": 0.0, "std_y": 0.0},
        },
        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
        "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
        "max_steps": 3,
        "tolerance": 0.001,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/control/run", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_max_steps_zero() -> None:
    fake = FakeRecipeClient()
    app = create_app(recipe_client=fake)
    payload = {
        "experiment_id": "exp_001",
        "algorithm": "lstm-controller",
        "config": {
            "model_type": "baseline_only",
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.05,
            "delta_clip_y": 0.05,
            "coll_x_min": -0.5, "coll_x_max": 0.5,
            "coll_y_min": -0.5, "coll_y_max": 0.5,
            "safety_threshold": 0.5,
            "safety_bias": 0.01,
            "release_perturbation": {"std_x": 0.0, "std_y": 0.0},
        },
        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
        "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
        "max_steps": 0,
        "tolerance": 0.001,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/control/run", json=payload)
    assert response.status_code == 200
    body = ControlRunResponse.model_validate(response.json())
    assert body.steps == 0
    assert len(fake.step_calls) == 1  # only step0
