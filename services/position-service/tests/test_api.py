import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_post_position_apply_success() -> None:
    payload = {"coll_x": 0.02, "coll_y": -0.05}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/position/apply", json=payload)

    assert response.status_code == 200
    assert response.json() == {"coll_x_shift": 0.02, "coll_y_shift": -0.05}


@pytest.mark.asyncio
async def test_post_position_apply_missing_parameter_returns_422() -> None:
    payload = {"coll_x": 0.02}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/position/apply", json=payload)

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
        "service": "position-service",
        "version": "0.1.0",
    }


@pytest.mark.asyncio
async def test_commanded_and_effective_values_are_identical() -> None:
    payload = {"coll_x": 1.234, "coll_y": -9.876}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/position/apply", json=payload)

    body = response.json()
    assert response.status_code == 200
    assert body["coll_x_shift"] == payload["coll_x"]
    assert body["coll_y_shift"] == payload["coll_y"]
