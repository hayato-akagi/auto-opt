import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.models import ControlRunResponse


# bolt shifts spot right by 0.02 consistently in this fake
FAKE_BOLT_SHIFT_X = 0.02
FAKE_BOLT_SHIFT_Y = -0.01


class FakeRecipeClient:
    def __init__(self) -> None:
        self.step_calls: list[tuple[float, float]] = []

    async def close(self) -> None:
        return None

    async def create_trial(self, experiment_id: str, control: dict, **kwargs) -> dict:
        assert experiment_id == "exp_001"
        assert control["algorithm"] == "adaptive-controller"
        return {"trial_id": "trial_001"}

    async def execute_step(
        self, experiment_id: str, trial_id: str, coll_x: float, coll_y: float, **kwargs
    ) -> dict:
        self.step_calls.append((coll_x, coll_y))
        call_index = len(self.step_calls)

        if call_index == 1:
            # Step 0: initial observation — bolt shifts spot by FAKE_BOLT_SHIFT
            return {
                "step_index": 0,
                "sim_after_position": {
                    "spot_center_x": 0.05,
                    "spot_center_y": -0.03,
                    "spot_rms_radius": 0.01,
                },
                "sim_after_bolt": {
                    "spot_center_x": 0.05 + FAKE_BOLT_SHIFT_X,
                    "spot_center_y": -0.03 + FAKE_BOLT_SHIFT_Y,
                    "spot_rms_radius": 0.01,
                },
            }

        # Subsequent steps: near-target result to trigger convergence
        return {
            "step_index": call_index - 1,
            "sim_after_position": {
                "spot_center_x": 0.0003,
                "spot_center_y": -0.0002,
                "spot_rms_radius": 0.005,
            },
            "sim_after_bolt": {
                "spot_center_x": 0.0003 + FAKE_BOLT_SHIFT_X,
                "spot_center_y": -0.0002 + FAKE_BOLT_SHIFT_Y,
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
    assert response.json() == {
        "status": "ok",
        "service": "adaptive-controller",
        "version": "0.1.0",
    }


@pytest.mark.asyncio
async def test_algorithms_endpoint() -> None:
    app = create_app(recipe_client=FakeRecipeClient())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/control/algorithms")

    assert response.status_code == 200
    body = response.json()
    assert body["algorithms"][0]["name"] == "adaptive-controller"


@pytest.mark.asyncio
async def test_control_step_no_estimate() -> None:
    # With no estimate, should behave like simple-controller
    app = create_app(recipe_client=FakeRecipeClient())

    payload = {
        "algorithm": "adaptive-controller",
        "config": {
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.05,
            "delta_clip_y": 0.05,
            "coll_x_min": -0.5,
            "coll_x_max": 0.5,
            "coll_y_min": -0.5,
            "coll_y_max": 0.5,
            "alpha": 0.5,
            "release_perturbation": {"std_x": 0.0, "std_y": 0.0},
        },
        "state": {
            "target_spot_center_x": 0.0,
            "target_spot_center_y": 0.0,
            "current_coll_x": 0.0,
            "current_coll_y": 0.0,
            "spot_pre_x": 0.02,
            "spot_pre_y": -0.01,
            "spot_post_x": 0.0,
            "spot_post_y": 0.0,
            "step_index": 0,
            "history": [],
            "bolt_shift_estimate_x": 0.0,
            "bolt_shift_estimate_y": 0.0,
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/control/step", json=payload)

    assert response.status_code == 200
    body = response.json()
    # baseline only: -0.02/50 = -0.0004
    assert body["delta_coll_x"] == pytest.approx(-0.02 / 50.0)
    assert body["delta_coll_y"] == pytest.approx(0.01 / 50.0)


@pytest.mark.asyncio
async def test_control_step_with_estimate() -> None:
    # With estimate, adaptive correction should be added
    app = create_app(recipe_client=FakeRecipeClient())

    payload = {
        "algorithm": "adaptive-controller",
        "config": {
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.05,
            "delta_clip_y": 0.05,
            "coll_x_min": -0.5,
            "coll_x_max": 0.5,
            "coll_y_min": -0.5,
            "coll_y_max": 0.5,
            "alpha": 0.5,
            "release_perturbation": {"std_x": 0.0, "std_y": 0.0},
        },
        "state": {
            "target_spot_center_x": 0.0,
            "target_spot_center_y": 0.0,
            "current_coll_x": 0.0,
            "current_coll_y": 0.0,
            "spot_pre_x": 0.02,
            "spot_pre_y": 0.0,
            "spot_post_x": 0.0,
            "spot_post_y": 0.0,
            "step_index": 1,
            "history": [],
            "bolt_shift_estimate_x": 0.04,
            "bolt_shift_estimate_y": 0.0,
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/control/step", json=payload)

    assert response.status_code == 200
    body = response.json()
    # baseline = -0.02/50, adaptive = -0.04/50 → total = -0.06/50 = -0.0012
    assert body["delta_coll_x"] == pytest.approx((-0.02 - 0.04) / 50.0)
    assert body["info"]["baseline_delta_x"] == pytest.approx(-0.02 / 50.0)
    assert body["info"]["adaptive_delta_x"] == pytest.approx(-0.04 / 50.0)


@pytest.mark.asyncio
async def test_control_run_uses_bolt_shift_from_step0() -> None:
    fake = FakeRecipeClient()
    app = create_app(recipe_client=fake)

    payload = {
        "experiment_id": "exp_001",
        "algorithm": "adaptive-controller",
        "config": {
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.05,
            "delta_clip_y": 0.05,
            "coll_x_min": -0.5,
            "coll_x_max": 0.5,
            "coll_y_min": -0.5,
            "coll_y_max": 0.5,
            "alpha": 1.0,  # always use latest observation
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
    assert body.trial_id == "trial_001"
    assert body.algorithm == "adaptive-controller"
    assert body.converged is True
    assert body.steps >= 1
    assert len(fake.step_calls) >= 2  # step0 + at least 1 control step

    # The initial bolt_shift should be detected from step 0
    assert body.initial_observation.initial_bolt_shift_x == pytest.approx(FAKE_BOLT_SHIFT_X)
    assert body.initial_observation.initial_bolt_shift_y == pytest.approx(FAKE_BOLT_SHIFT_Y)

    # Final estimate should reflect the observed bolt shift
    assert body.bolt_shift_estimate_x == pytest.approx(FAKE_BOLT_SHIFT_X)
    assert body.bolt_shift_estimate_y == pytest.approx(FAKE_BOLT_SHIFT_Y)


@pytest.mark.asyncio
async def test_unsupported_algorithm_returns_422() -> None:
    app = create_app(recipe_client=FakeRecipeClient())

    payload = {
        "algorithm": "simple-controller",  # wrong algorithm
        "config": {
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.05,
            "delta_clip_y": 0.05,
            "coll_x_min": -0.5,
            "coll_x_max": 0.5,
            "coll_y_min": -0.5,
            "coll_y_max": 0.5,
            "alpha": 0.5,
            "release_perturbation": {"std_x": 0.0, "std_y": 0.0},
        },
        "state": {
            "target_spot_center_x": 0.0,
            "target_spot_center_y": 0.0,
            "current_coll_x": 0.0,
            "current_coll_y": 0.0,
            "spot_pre_x": 0.0,
            "spot_pre_y": 0.0,
            "spot_post_x": 0.0,
            "spot_post_y": 0.0,
            "step_index": 0,
            "history": [],
            "bolt_shift_estimate_x": 0.0,
            "bolt_shift_estimate_y": 0.0,
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/control/step", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_max_steps_zero_returns_step0_result() -> None:
    fake = FakeRecipeClient()
    app = create_app(recipe_client=fake)

    payload = {
        "experiment_id": "exp_001",
        "algorithm": "adaptive-controller",
        "config": {
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.05,
            "delta_clip_y": 0.05,
            "coll_x_min": -0.5,
            "coll_x_max": 0.5,
            "coll_y_min": -0.5,
            "coll_y_max": 0.5,
            "alpha": 0.5,
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
