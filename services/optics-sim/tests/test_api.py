import base64

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture(autouse=True)
def enable_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_SIMULATION", "true")


def build_payload() -> dict:
    return {
        "wavelength": 780.0,
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
        "coll_x_shift": 0.0,
        "coll_y_shift": 0.0,
        "obj_f": 4.0,
        "dist_coll_obj": 50.0,
        "sensor_pos": 4.0,
        "return_ray_hits": False,
        "return_ray_path_image": False,
        "return_spot_diagram_image": False,
    }


@pytest.mark.asyncio
async def test_post_simulate_success() -> None:
    payload = build_payload()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/simulate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "spot_center_x",
        "spot_center_y",
        "spot_rms_radius",
        "spot_geo_radius",
        "spot_peak_x",
        "spot_peak_y",
        "num_rays_launched",
        "num_rays_arrived",
        "vignetting_ratio",
        "ray_hits",
        "ray_path_image",
        "spot_diagram_image",
        "computation_time_ms",
    }
    assert body["ray_hits"] is None
    assert body["ray_path_image"] is None
    assert body["spot_diagram_image"] is None


@pytest.mark.asyncio
async def test_spot_center_changes_with_collimator_shift() -> None:
    payload_base = build_payload()
    payload_shifted = build_payload()
    payload_shifted["coll_x_shift"] = 0.2
    payload_shifted["coll_y_shift"] = -0.15

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        baseline = await client.post("/simulate", json=payload_base)
        shifted = await client.post("/simulate", json=payload_shifted)

    assert baseline.status_code == 200
    assert shifted.status_code == 200

    baseline_json = baseline.json()
    shifted_json = shifted.json()

    assert shifted_json["spot_center_x"] != pytest.approx(baseline_json["spot_center_x"])
    assert shifted_json["spot_center_y"] != pytest.approx(baseline_json["spot_center_y"])


@pytest.mark.asyncio
async def test_return_ray_hits_true_returns_array() -> None:
    payload = build_payload()
    payload["return_ray_hits"] = True

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/simulate", json=payload)

    body = response.json()
    assert response.status_code == 200
    assert isinstance(body["ray_hits"], list)
    assert len(body["ray_hits"]) == body["num_rays_arrived"]
    assert set(body["ray_hits"][0].keys()) == {"x", "y"}


@pytest.mark.asyncio
async def test_return_ray_path_image_true_returns_base64_png() -> None:
    payload = build_payload()
    payload["return_ray_path_image"] = True

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/simulate", json=payload)

    assert response.status_code == 200
    encoded = response.json()["ray_path_image"]
    assert isinstance(encoded, str)
    decoded = base64.b64decode(encoded)
    assert decoded.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_return_spot_diagram_image_true_returns_base64_png() -> None:
    payload = build_payload()
    payload["return_spot_diagram_image"] = True

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/simulate", json=payload)

    assert response.status_code == 200
    encoded = response.json()["spot_diagram_image"]
    assert isinstance(encoded, str)
    decoded = base64.b64decode(encoded)
    assert decoded.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_num_rays_launched_equals_request_num_rays() -> None:
    payload = build_payload()
    payload["num_rays"] = 777

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/simulate", json=payload)

    assert response.status_code == 200
    assert response.json()["num_rays_launched"] == 777


@pytest.mark.asyncio
async def test_post_simulate_missing_parameter_returns_422() -> None:
    payload = build_payload()
    payload.pop("coll_r1")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/simulate", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_health() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "optics-sim",
        "version": "0.1.0",
    }


@pytest.mark.asyncio
async def test_mock_simulation_mode_is_deterministic_for_same_payload() -> None:
    payload = build_payload()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.post("/simulate", json=payload)
        second = await client.post("/simulate", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200

    first_body = first.json()
    second_body = second.json()

    for key in (
        "spot_center_x",
        "spot_center_y",
        "spot_rms_radius",
        "spot_geo_radius",
        "spot_peak_x",
        "spot_peak_y",
        "num_rays_launched",
        "num_rays_arrived",
        "vignetting_ratio",
    ):
        assert first_body[key] == pytest.approx(second_body[key])
