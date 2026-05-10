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
async def test_post_models_registers_model():
    """POST /models registers a new model version."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/models",
            json={
                "version": "v1.0.0",
                "model_type": "mlp",
                "status": "candidate",
                "benchmark_metrics": {"median_error_mm": 0.05},
                "benchmark_trial_ids": ["trial_001", "trial_002"],
                "benchmark_experiment_ids": ["exp_001"],
                "train_job_id": "train_job_001",
                "created_at": "2024-01-01T00:00:00Z",
            },
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "v1.0.0"
    assert data["model_type"] == "mlp"
    assert data["status"] == "candidate"


@pytest.mark.asyncio
async def test_post_models_duplicate_fails():
    """POST /models with duplicate version fails."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First registration
        await client.post(
            "/models",
            json={
                "version": "v1.1.0",
                "model_type": "mlp",
                "status": "candidate",
                "created_at": "2024-01-01T00:00:00Z",
            },
        )
        
        # Duplicate registration
        response = await client.post(
            "/models",
            json={
                "version": "v1.1.0",
                "model_type": "mlp",
                "status": "candidate",
                "created_at": "2024-01-01T00:00:00Z",
            },
        )
    
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_get_models_lists_all():
    """GET /models lists all registered models."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register two models
        await client.post(
            "/models",
            json={
                "version": "v2.0.0",
                "model_type": "mlp",
                "status": "candidate",
                "created_at": "2024-01-01T00:00:00Z",
            },
        )
        await client.post(
            "/models",
            json={
                "version": "v2.1.0",
                "model_type": "mlp",
                "status": "candidate",
                "created_at": "2024-01-02T00:00:00Z",
            },
        )
        
        # List all
        response = await client.get("/models")
    
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert len(data["models"]) >= 2
    versions = [m["version"] for m in data["models"]]
    assert "v2.0.0" in versions
    assert "v2.1.0" in versions


@pytest.mark.asyncio
async def test_get_model_by_version():
    """GET /models/{version} retrieves a specific model."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register a model
        await client.post(
            "/models",
            json={
                "version": "v3.0.0",
                "model_type": "baseline_only",
                "status": "candidate",
                "created_at": "2024-01-01T00:00:00Z",
            },
        )
        
        # Get it
        response = await client.get("/models/v3.0.0")
    
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "v3.0.0"
    assert data["model_type"] == "baseline_only"


@pytest.mark.asyncio
async def test_get_model_not_found():
    """GET /models/{version} returns 404 for non-existent model."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/models/v999.0.0")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_promote_model_to_current():
    """POST /models/{version}/promote promotes a model to current."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register model
        await client.post(
            "/models",
            json={
                "version": "v4.0.0",
                "model_type": "mlp",
                "status": "candidate",
                "created_at": "2024-01-01T00:00:00Z",
            },
        )
        
        # Promote it
        response = await client.post(
            "/models/v4.0.0/promote",
            json={"version": "v4.0.0"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "v4.0.0"
        assert data["new_status"] == "current"
        assert "promoted_at" in data
        
        # Verify it was promoted
        get_response = await client.get("/models/v4.0.0")
        assert get_response.json()["status"] == "current"


@pytest.mark.asyncio
async def test_promote_nonexistent_model_fails():
    """POST /models/{version}/promote fails for non-existent model."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/models/v999.0.0/promote",
            json={"version": "v999.0.0"},
        )
    
    assert response.status_code == 404

