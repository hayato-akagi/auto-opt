from __future__ import annotations

from typing import Any

import pytest

from app.errors import DownstreamServiceError
from app.models import ExperimentCreateRequest, StepExecuteRequest
from app.orchestrator import RecipeOrchestrator
from app.storage import RecipeStorage


def build_experiment_request() -> ExperimentCreateRequest:
    return ExperimentCreateRequest(
        name="baseline_780nm",
        optical_system={
            "wavelength": 780,
            "ld_tilt": 0.0,
            "ld_div_fast": 25.0,
            "ld_div_slow": 8.0,
            "ld_div_fast_err": 0.0,
            "ld_div_slow_err": 0.0,
            "ld_emit_w": 3.0,
            "ld_emit_h": 1.0,
            "num_rays": 500,
            "coll_r1": -3.5,
            "coll_r2": -15.0,
            "coll_k1": -1.0,
            "coll_k2": 0.0,
            "coll_t": 2.0,
            "coll_n": 1.517,
            "dist_ld_coll": 4.0,
            "obj_f": 4.0,
            "dist_coll_obj": 50.0,
            "sensor_pos": 4.0,
        },
        bolt_model={
            "upper": {
                "shift_x_per_nm": 0.001,
                "shift_y_per_nm": 0.003,
                "noise_std_x": 0.002,
                "noise_std_y": 0.005,
            },
            "lower": {
                "shift_x_per_nm": -0.0005,
                "shift_y_per_nm": 0.002,
                "noise_std_x": 0.001,
                "noise_std_y": 0.003,
            },
        },
    )


class OrderedClients:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def apply_position(self, coll_x: float, coll_y: float) -> dict[str, Any]:
        self.calls.append("position")
        return {"coll_x_shift": coll_x, "coll_y_shift": coll_y}

    async def simulate(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("simulate")
        shift_x = float(payload["coll_x_shift"])
        shift_y = float(payload["coll_y_shift"])
        return {
            "spot_center_x": shift_x,
            "spot_center_y": shift_y,
            "spot_rms_radius": 0.01,
            "spot_geo_radius": 0.02,
            "spot_peak_x": shift_x,
            "spot_peak_y": shift_y,
            "num_rays_launched": int(payload["num_rays"]),
            "num_rays_arrived": int(payload["num_rays"]),
            "vignetting_ratio": 0.0,
            "ray_hits": None,
            "ray_path_image": None,
            "spot_diagram_image": None,
            "computation_time_ms": 10,
        }

    async def apply_bolt(
        self,
        torque_upper: float,
        torque_lower: float,
        bolt_model: dict[str, Any],
        random_seed: int | None,
    ) -> dict[str, Any]:
        self.calls.append("bolt")
        return {
            "delta_x": 0.001,
            "delta_y": 0.002,
            "used_seed": 100,
            "detail": {
                "upper": {"delta_x": 0.001, "delta_y": 0.001},
                "lower": {"delta_x": 0.0, "delta_y": 0.001},
            },
        }


class BoltFailClients(OrderedClients):
    async def apply_bolt(
        self,
        torque_upper: float,
        torque_lower: float,
        bolt_model: dict[str, Any],
        random_seed: int | None,
    ) -> dict[str, Any]:
        self.calls.append("bolt")
        raise DownstreamServiceError(
            detail="bolt-service returned error: forced",
            downstream="bolt-service",
        )


@pytest.mark.asyncio
async def test_orchestration_order_is_position_sim_bolt_sim(tmp_path) -> None:
    storage = RecipeStorage(tmp_path)
    experiment = await storage.create_experiment(build_experiment_request())
    trial = await storage.create_trial(
        experiment_id=experiment["experiment_id"],
        mode="manual",
        control=None,
    )

    clients = OrderedClients()
    orchestrator = RecipeOrchestrator(storage, clients)

    result = await orchestrator.execute_step(
        experiment["experiment_id"],
        trial["trial_id"],
        StepExecuteRequest(
            coll_x=0.02,
            coll_y=-0.05,
            torque_upper=0.5,
            torque_lower=0.5,
        ),
    )

    assert result["step_index"] == 0
    assert clients.calls == ["position", "simulate", "bolt", "simulate"]


@pytest.mark.asyncio
async def test_bolt_failure_does_not_save_step(tmp_path) -> None:
    storage = RecipeStorage(tmp_path)
    experiment = await storage.create_experiment(build_experiment_request())
    trial = await storage.create_trial(
        experiment_id=experiment["experiment_id"],
        mode="manual",
        control=None,
    )

    clients = BoltFailClients()
    orchestrator = RecipeOrchestrator(storage, clients)

    with pytest.raises(DownstreamServiceError):
        await orchestrator.execute_step(
            experiment["experiment_id"],
            trial["trial_id"],
            StepExecuteRequest(
                coll_x=0.02,
                coll_y=-0.05,
                torque_upper=0.5,
                torque_lower=0.5,
            ),
        )

    assert await storage.count_steps(experiment["experiment_id"], trial["trial_id"]) == 0
