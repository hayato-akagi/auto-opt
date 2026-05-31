import asyncio
import os
from datetime import datetime, timezone

from fastapi import FastAPI

from .clients import RecipeServiceClient
from .job_runner import run_training_job
from .models import (
    HealthResponse,
    TrainRequest,
    TrainJobResponse,
    TrainJobListResponse,
    TrainJobStatus,
)

app = FastAPI(title="trainer", version="0.1.0")

# In-memory training job storage
_jobs: dict[str, TrainJobStatus] = {}
_job_counter = 0

# Recipe service client
_recipe_client: RecipeServiceClient | None = None


def _get_recipe_client() -> RecipeServiceClient:
    global _recipe_client
    if _recipe_client is None:
        base_url = os.getenv("RECIPE_SERVICE_URL", "http://recipe-service:8002")
        _recipe_client = RecipeServiceClient(base_url)
    return _recipe_client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global _recipe_client
    if _recipe_client is not None:
        _recipe_client.close()
        _recipe_client = None


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/train", response_model=TrainJobResponse)
async def start_training(request: TrainRequest) -> TrainJobResponse:
    """Start a new training job."""
    global _job_counter
    _job_counter += 1
    train_job_id = f"train_job_{_job_counter:06d}"
    
    # Initialize job with "running" status
    job = TrainJobStatus(
        train_job_id=train_job_id,
        status="running",
        data_stats={"experiment_count": len(request.experiment_ids)},
        started_at=_utc_now_iso(),
        updated_at=_utc_now_iso(),
        total_epochs=request.epochs,
        current_epoch=0,
        progress_rate=0.0,
        last_loss=None,
        epoch_logs=[],
        train_metrics=None,
        benchmark_results=None,
        promoted=None,
        promoted_version=None,
    )
    _jobs[train_job_id] = job

    # Start background training job
    recipe_client = _get_recipe_client()
    asyncio.create_task(run_training_job(train_job_id, request, _jobs, recipe_client))
    
    return TrainJobResponse(
        train_job_id=train_job_id,
        status="running",
        message=f"Training job {train_job_id} started",
    )


@app.get("/train", response_model=TrainJobListResponse)
async def list_training_jobs() -> TrainJobListResponse:
    """List all training jobs."""
    jobs = list(_jobs.values())
    return TrainJobListResponse(jobs=jobs)


@app.get("/train/{train_job_id}", response_model=TrainJobStatus)
async def get_training_job_status(train_job_id: str) -> TrainJobStatus:
    """Get status of a training job."""
    if train_job_id not in _jobs:
        # Keep backward-compatible response shape but return explicit failure.
        return TrainJobStatus(
            train_job_id=train_job_id,
            status="failed",
            error_message="train_job_id not found",
        )
    
    return _jobs[train_job_id]

