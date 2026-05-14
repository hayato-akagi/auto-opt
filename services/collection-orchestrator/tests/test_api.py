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
        }


@pytest.mark.asyncio
async def test_health() -> None:
    app = create_app(controller_client=FakeControllerClient())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_and_get_job() -> None:
    app = create_app(controller_client=FakeControllerClient())
    payload = {
        "algorithm": "simple-controller",
        "controller_config": {
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.1,
            "delta_clip_y": 0.1,
            "coll_x_min": -0.5,
            "coll_x_max": 0.5,
            "coll_y_min": -0.5,
            "coll_y_max": 0.5,
        },
        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
        "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
        "max_steps": 2,
        "tolerance": 0.05,
        "tasks": [{"experiment_id": "exp_001", "seeds": [1, 2]}],
        "max_workers": 2,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_res = await client.post("/jobs", json=payload)
        assert create_res.status_code == 202
        job_id = create_res.json()["job_id"]

        for _ in range(20):
            get_res = await client.get(f"/jobs/{job_id}")
            assert get_res.status_code == 200
            body = get_res.json()
            if body["status"] != "running":
                break
            await asyncio.sleep(0.01)

        assert body["status"] in {"completed", "partial", "failed"}
        assert body["total_tasks"] == 2
        assert body["completed_tasks"] == 2


@pytest.mark.asyncio
async def test_list_jobs() -> None:
    app = create_app(controller_client=FakeControllerClient())
    payload = {
        "algorithm": "simple-controller",
        "controller_config": {
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.1,
            "delta_clip_y": 0.1,
            "coll_x_min": -0.5,
            "coll_x_max": 0.5,
            "coll_y_min": -0.5,
            "coll_y_max": 0.5,
        },
        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
        "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
        "max_steps": 1,
        "tolerance": 0.05,
        "tasks": [{"experiment_id": "exp_001", "seeds": [1]}],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/jobs", json=payload)
        res = await client.get("/jobs")
        assert res.status_code == 200
        assert len(res.json()["jobs"]) >= 1


@pytest.mark.asyncio
async def test_create_job_requires_non_empty_tasks() -> None:
    app = create_app(controller_client=FakeControllerClient())
    payload = {
        "algorithm": "simple-controller",
        "controller_config": {
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.1,
            "delta_clip_y": 0.1,
            "coll_x_min": -0.5,
            "coll_x_max": 0.5,
            "coll_y_min": -0.5,
            "coll_y_max": 0.5,
        },
        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
        "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
        "max_steps": 1,
        "tolerance": 0.05,
        "tasks": [{"experiment_id": "exp_001", "seeds": []}],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/jobs", json=payload)

    assert res.status_code == 422
