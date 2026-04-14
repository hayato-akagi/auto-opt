import pytest
from httpx import ASGITransport, AsyncClient

from app import core
from app.main import app


def build_payload(random_seed: int | None = 42) -> dict:
    return {
        "torque_upper": 0.5,
        "torque_lower": 0.5,
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
        "random_seed": random_seed,
    }


@pytest.mark.asyncio
async def test_post_bolt_apply_success() -> None:
    payload = build_payload(random_seed=42)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/bolt/apply", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"delta_x", "delta_y", "used_seed", "detail"}
    assert set(body["detail"].keys()) == {"upper", "lower"}


@pytest.mark.asyncio
async def test_seed_reproducibility() -> None:
    payload = build_payload(random_seed=12345)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.post("/bolt/apply", json=payload)
        second = await client.post("/bolt/apply", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()


@pytest.mark.asyncio
async def test_null_seed_generates_different_used_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    generated = [
        (111).to_bytes(4, "big"),
        (222).to_bytes(4, "big"),
    ]

    def fake_urandom(_: int) -> bytes:
        return generated.pop(0)

    monkeypatch.setattr(core.os, "urandom", fake_urandom)

    payload = build_payload(random_seed=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.post("/bolt/apply", json=payload)
        second = await client.post("/bolt/apply", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["used_seed"] != second.json()["used_seed"]


@pytest.mark.asyncio
async def test_zero_noise_matches_torque_times_shift() -> None:
    payload = build_payload(random_seed=7)
    payload["bolt_model"]["upper"]["noise_std_x"] = 0.0
    payload["bolt_model"]["upper"]["noise_std_y"] = 0.0
    payload["bolt_model"]["lower"]["noise_std_x"] = 0.0
    payload["bolt_model"]["lower"]["noise_std_y"] = 0.0

    expected_upper_x = payload["torque_upper"] * payload["bolt_model"]["upper"]["shift_x_per_nm"]
    expected_upper_y = payload["torque_upper"] * payload["bolt_model"]["upper"]["shift_y_per_nm"]
    expected_lower_x = payload["torque_lower"] * payload["bolt_model"]["lower"]["shift_x_per_nm"]
    expected_lower_y = payload["torque_lower"] * payload["bolt_model"]["lower"]["shift_y_per_nm"]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/bolt/apply", json=payload)

    body = response.json()
    assert response.status_code == 200
    assert body["detail"]["upper"]["delta_x"] == pytest.approx(expected_upper_x)
    assert body["detail"]["upper"]["delta_y"] == pytest.approx(expected_upper_y)
    assert body["detail"]["lower"]["delta_x"] == pytest.approx(expected_lower_x)
    assert body["detail"]["lower"]["delta_y"] == pytest.approx(expected_lower_y)
    assert body["delta_x"] == pytest.approx(expected_upper_x + expected_lower_x)
    assert body["delta_y"] == pytest.approx(expected_upper_y + expected_lower_y)


@pytest.mark.asyncio
async def test_detail_sums_match_total() -> None:
    payload = build_payload(random_seed=999)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/bolt/apply", json=payload)

    body = response.json()
    assert response.status_code == 200
    assert body["delta_x"] == pytest.approx(
        body["detail"]["upper"]["delta_x"] + body["detail"]["lower"]["delta_x"]
    )
    assert body["delta_y"] == pytest.approx(
        body["detail"]["upper"]["delta_y"] + body["detail"]["lower"]["delta_y"]
    )


@pytest.mark.asyncio
async def test_post_bolt_apply_missing_parameter_returns_422() -> None:
    payload = build_payload(random_seed=42)
    payload.pop("torque_lower")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/bolt/apply", json=payload)

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
        "service": "bolt-service",
        "version": "0.1.0",
    }
