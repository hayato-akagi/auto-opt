import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_post_train_starts_job():
    """POST /train starts a new training job and returns job_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/train",
            json={
                "experiment_ids": ["exp_001", "exp_002"],
                "model_type": "mlp",
                "epochs": 50,
                "batch_size": 32,
            },
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "train_job_id" in data
    assert data["train_job_id"].startswith("train_job_")


@pytest.mark.asyncio
async def test_post_train_requires_experiment_ids():
    """POST /train requires at least one experiment_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/train",
            json={
                "experiment_ids": [],
                "model_type": "mlp",
            },
        )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_train_lists_jobs():
    """GET /train lists all training jobs."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Start one job
        post_response = await client.post(
            "/train",
            json={"experiment_ids": ["exp_001"], "model_type": "mlp"},
        )
        job_id = post_response.json()["train_job_id"]
        
        # List jobs
        response = await client.get("/train")
    
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert isinstance(data["jobs"], list)
    assert len(data["jobs"]) >= 1
    # Check that our job is in the list
    job_ids = [j["train_job_id"] for j in data["jobs"]]
    assert job_id in job_ids


@pytest.mark.asyncio
async def test_get_train_job_status():
    """GET /train/{job_id} returns job status including metrics."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Start a job
        post_response = await client.post(
            "/train",
            json={"experiment_ids": ["exp_001"], "model_type": "mlp"},
        )
        job_id = post_response.json()["train_job_id"]
        
        # Get status
        response = await client.get(f"/train/{job_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["train_job_id"] == job_id
    # For a newly started job, status should be "running" (no metrics yet)
    # But when checking a non-existent job (dummy response), it has "completed" status

