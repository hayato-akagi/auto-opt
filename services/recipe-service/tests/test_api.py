from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.errors import DownstreamServiceError, DownstreamTimeoutError
from app.main import create_app


class FakeDownstreamClients:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_next_bolt = False
        self.timeout_next_bolt = False
        self.fail_next_optics = False

    async def close(self) -> None:
        return None

    async def apply_position(self, coll_x: float, coll_y: float) -> dict[str, Any]:
        payload = {"coll_x": coll_x, "coll_y": coll_y}
        self.calls.append(("position", payload))
        return {"coll_x_shift": coll_x, "coll_y_shift": coll_y}

    async def apply_bolt(
        self,
        torque_upper: float,
        torque_lower: float,
        bolt_model: dict[str, Any],
        random_seed: int | None,
    ) -> dict[str, Any]:
        payload = {
            "torque_upper": torque_upper,
            "torque_lower": torque_lower,
            "bolt_model": bolt_model,
            "random_seed": random_seed,
        }
        self.calls.append(("bolt", payload))

        if self.timeout_next_bolt:
            self.timeout_next_bolt = False
            raise DownstreamTimeoutError(
                detail="timeout calling bolt-service",
                downstream="bolt-service",
            )
        if self.fail_next_bolt:
            self.fail_next_bolt = False
            raise DownstreamServiceError(
                detail="bolt-service returned error: forced",
                downstream="bolt-service",
            )

        return {
            "delta_x": 0.003,
            "delta_y": 0.008,
            "used_seed": 123456,
            "detail": {
                "upper": {"delta_x": 0.0015, "delta_y": 0.0055},
                "lower": {"delta_x": 0.0015, "delta_y": 0.0025},
            },
        }

    async def simulate(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("simulate", dict(payload)))

        if self.fail_next_optics:
            self.fail_next_optics = False
            raise DownstreamServiceError(
                detail="optics-sim returned error: forced",
                downstream="optics-sim",
            )

        coll_x_shift = float(payload["coll_x_shift"])
        coll_y_shift = float(payload["coll_y_shift"])
        num_rays = int(payload["num_rays"])
        num_rays_arrived = max(num_rays - 13, 0)
        vignetting_ratio = 0.0
        if num_rays > 0:
            vignetting_ratio = (num_rays - num_rays_arrived) / num_rays

        response: dict[str, Any] = {
            "spot_center_x": round(coll_x_shift * 0.5, 6),
            "spot_center_y": round(coll_y_shift * 0.5, 6),
            "spot_rms_radius": round(0.004 + abs(coll_x_shift) * 0.02 + abs(coll_y_shift) * 0.02, 6),
            "spot_geo_radius": round(0.010 + abs(coll_x_shift) * 0.03 + abs(coll_y_shift) * 0.03, 6),
            "spot_peak_x": round(coll_x_shift * 0.5 + 0.001, 6),
            "spot_peak_y": round(coll_y_shift * 0.5 + 0.001, 6),
            "num_rays_launched": num_rays,
            "num_rays_arrived": num_rays_arrived,
            "vignetting_ratio": round(vignetting_ratio, 6),
            "ray_hits": None,
            "ray_path_image": None,
            "spot_diagram_image": None,
            "computation_time_ms": 15,
        }

        if payload.get("return_ray_hits"):
            response["ray_hits"] = [{"x": coll_x_shift, "y": coll_y_shift}]
        if payload.get("return_ray_path_image"):
            response["ray_path_image"] = "ray_path_image_base64"
        if payload.get("return_spot_diagram_image"):
            response["spot_diagram_image"] = "spot_diagram_image_base64"

        return response


@pytest_asyncio.fixture
async def client_bundle(tmp_path: Path):
    fake_clients = FakeDownstreamClients()
    app = create_app(settings=Settings(data_dir=tmp_path), clients=fake_clients)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client, tmp_path, fake_clients


def build_experiment_payload(name: str = "baseline_780nm") -> dict[str, Any]:
    return {
        "name": name,
        "optical_system": {
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
        "bolt_model": {
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
    }


def build_step_payload() -> dict[str, Any]:
    return {
        "coll_x": 0.02,
        "coll_y": -0.05,
        "torque_upper": 0.5,
        "torque_lower": 0.5,
        "options": {
            "return_ray_hits": False,
            "return_images": False,
        },
    }


async def create_experiment_and_trial(client: AsyncClient) -> tuple[str, str]:
    exp_response = await client.post("/experiments", json=build_experiment_payload())
    assert exp_response.status_code == 201
    experiment_id = exp_response.json()["experiment_id"]

    trial_response = await client.post(
        f"/experiments/{experiment_id}/trials",
        json={"mode": "manual", "control": None},
    )
    assert trial_response.status_code == 201
    trial_id = trial_response.json()["trial_id"]
    return experiment_id, trial_id


@pytest.mark.asyncio
async def test_post_experiments_creates_experiment_json(client_bundle) -> None:
    client, tmp_path, _ = client_bundle

    response = await client.post("/experiments", json=build_experiment_payload())

    assert response.status_code == 201
    body = response.json()
    exp_file = tmp_path / "experiments" / body["experiment_id"] / "experiment.json"
    assert exp_file.exists()


@pytest.mark.asyncio
async def test_post_trials_creates_trial_meta_json(client_bundle) -> None:
    client, tmp_path, _ = client_bundle
    exp_response = await client.post("/experiments", json=build_experiment_payload())
    experiment_id = exp_response.json()["experiment_id"]

    response = await client.post(
        f"/experiments/{experiment_id}/trials",
        json={"mode": "manual", "control": None},
    )

    assert response.status_code == 201
    trial_id = response.json()["trial_id"]
    trial_meta = tmp_path / "experiments" / experiment_id / trial_id / "trial_meta.json"
    assert trial_meta.exists()


@pytest.mark.asyncio
async def test_post_steps_creates_step_json(client_bundle) -> None:
    client, tmp_path, _ = client_bundle
    experiment_id, trial_id = await create_experiment_and_trial(client)

    response = await client.post(
        f"/experiments/{experiment_id}/trials/{trial_id}/steps",
        json=build_step_payload(),
    )

    assert response.status_code == 200
    step_file = tmp_path / "experiments" / experiment_id / trial_id / "step_000.json"
    assert step_file.exists()

    data = json.loads(step_file.read_text(encoding="utf-8"))
    assert "ray_path_image" not in data["sim_after_position"]
    assert "spot_diagram_image" not in data["sim_after_position"]


@pytest.mark.asyncio
async def test_step_orchestration_order_is_correct(client_bundle) -> None:
    client, _, fake_clients = client_bundle
    experiment_id, trial_id = await create_experiment_and_trial(client)

    response = await client.post(
        f"/experiments/{experiment_id}/trials/{trial_id}/steps",
        json=build_step_payload(),
    )

    assert response.status_code == 200
    call_names = [name for name, _ in fake_clients.calls]
    assert call_names == ["position", "simulate", "bolt", "simulate"]


@pytest.mark.asyncio
async def test_atomicity_when_bolt_fails(client_bundle) -> None:
    client, tmp_path, fake_clients = client_bundle
    experiment_id, trial_id = await create_experiment_and_trial(client)
    fake_clients.fail_next_bolt = True

    response = await client.post(
        f"/experiments/{experiment_id}/trials/{trial_id}/steps",
        json=build_step_payload(),
    )

    assert response.status_code == 502
    assert response.json()["downstream"] == "bolt-service"

    trial_dir = tmp_path / "experiments" / experiment_id / trial_id
    assert list(trial_dir.glob("step_*.json")) == []


@pytest.mark.asyncio
async def test_error_conversion_502_and_504(client_bundle) -> None:
    client, _, fake_clients = client_bundle
    experiment_id, trial_id = await create_experiment_and_trial(client)

    fake_clients.fail_next_optics = True
    optics_response = await client.post(
        f"/experiments/{experiment_id}/trials/{trial_id}/steps",
        json=build_step_payload(),
    )
    assert optics_response.status_code == 502
    assert optics_response.json()["downstream"] == "optics-sim"

    fake_clients.timeout_next_bolt = True
    bolt_response = await client.post(
        f"/experiments/{experiment_id}/trials/{trial_id}/steps",
        json=build_step_payload(),
    )
    assert bolt_response.status_code == 504
    assert bolt_response.json()["downstream"] == "bolt-service"


@pytest.mark.asyncio
async def test_complete_generates_summary_and_second_call_is_409(client_bundle) -> None:
    client, tmp_path, _ = client_bundle
    experiment_id, trial_id = await create_experiment_and_trial(client)

    step_response = await client.post(
        f"/experiments/{experiment_id}/trials/{trial_id}/steps",
        json=build_step_payload(),
    )
    assert step_response.status_code == 200

    first_complete = await client.post(
        f"/experiments/{experiment_id}/trials/{trial_id}/complete"
    )
    assert first_complete.status_code == 200
    summary_file = tmp_path / "experiments" / experiment_id / trial_id / "summary.json"
    assert summary_file.exists()

    second_complete = await client.post(
        f"/experiments/{experiment_id}/trials/{trial_id}/complete"
    )
    assert second_complete.status_code == 409


@pytest.mark.asyncio
async def test_step_images_endpoint_uses_phase_shift(client_bundle) -> None:
    client, _, fake_clients = client_bundle
    experiment_id, trial_id = await create_experiment_and_trial(client)

    step_response = await client.post(
        f"/experiments/{experiment_id}/trials/{trial_id}/steps",
        json=build_step_payload(),
    )
    assert step_response.status_code == 200

    fake_clients.calls.clear()
    images_response = await client.post(
        f"/experiments/{experiment_id}/trials/{trial_id}/steps/0/images",
        json={"phase": "after_bolt"},
    )

    assert images_response.status_code == 200
    images = images_response.json()
    assert images["ray_path_image"] == "ray_path_image_base64"
    assert images["spot_diagram_image"] == "spot_diagram_image_base64"

    assert len(fake_clients.calls) == 1
    call_name, sim_payload = fake_clients.calls[0]
    assert call_name == "simulate"

    expected_after_bolt = step_response.json()["after_bolt"]
    assert sim_payload["coll_x_shift"] == expected_after_bolt["coll_x_shift"]
    assert sim_payload["coll_y_shift"] == expected_after_bolt["coll_y_shift"]
    assert sim_payload["return_ray_path_image"] is True
    assert sim_payload["return_spot_diagram_image"] is True


@pytest.mark.asyncio
async def test_sweep_creates_multiple_steps_and_summary(client_bundle) -> None:
    client, tmp_path, _ = client_bundle

    exp_response = await client.post("/experiments", json=build_experiment_payload())
    experiment_id = exp_response.json()["experiment_id"]

    sweep_payload = {
        "experiment_id": experiment_id,
        "base_command": {
            "coll_x": 0.0,
            "coll_y": 0.0,
            "torque_upper": 0.5,
            "torque_lower": 0.5,
        },
        "sweep": {
            "param_name": "coll_y",
            "values": [-0.1, 0.0, 0.1],
        },
    }

    response = await client.post("/recipes/sweep", json=sweep_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "sweep"
    assert len(body["results"]) == 3

    trial_id = body["trial_id"]
    trial_dir = tmp_path / "experiments" / experiment_id / trial_id
    step_files = sorted(path.name for path in trial_dir.glob("step_*.json"))
    assert step_files == ["step_000.json", "step_001.json", "step_002.json"]
    assert (trial_dir / "summary.json").exists()


@pytest.mark.asyncio
async def test_id_auto_increment_for_experiments_and_trials(client_bundle) -> None:
    client, _, _ = client_bundle

    exp1 = await client.post("/experiments", json=build_experiment_payload(name="exp1"))
    exp2 = await client.post("/experiments", json=build_experiment_payload(name="exp2"))

    exp1_id = exp1.json()["experiment_id"]
    exp2_id = exp2.json()["experiment_id"]

    assert exp1_id == "exp_001"
    assert exp2_id == "exp_002"

    trial1 = await client.post(
        f"/experiments/{exp1_id}/trials",
        json={"mode": "manual", "control": None},
    )
    trial2 = await client.post(
        f"/experiments/{exp1_id}/trials",
        json={"mode": "control_loop", "control": {"algorithm": "pid"}},
    )
    trial3 = await client.post(
        f"/experiments/{exp2_id}/trials",
        json={"mode": "manual", "control": None},
    )

    assert trial1.json()["trial_id"] == "trial_001"
    assert trial2.json()["trial_id"] == "trial_002"
    assert trial3.json()["trial_id"] == "trial_001"


@pytest.mark.asyncio
async def test_get_health(client_bundle) -> None:
    client, _, _ = client_bundle

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "recipe-service",
        "version": "0.1.0",
    }
