from fastapi import FastAPI
from .models import (
    HealthResponse,
    TrainRequest,
    TrainJobResponse,
    TrainJobListResponse,
    TrainJobStatus,
    TrainMetrics,
    BenchmarkResultDetail,
)

app = FastAPI(title="trainer", version="0.1.0")

# In-memory training job storage for testing
_jobs: dict[str, TrainJobStatus] = {}
_job_counter = 0


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
        data_stats=None,
        train_metrics=None,
        benchmark_results=None,
        promoted=None,
        promoted_version=None,
    )
    _jobs[train_job_id] = job
    
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
        # Return a dummy completed job for testing
        return TrainJobStatus(
            train_job_id=train_job_id,
            status="completed",
            data_stats={"total_steps": 100},
            train_metrics=TrainMetrics(
                epoch_losses=[0.5, 0.45, 0.4, 0.35, 0.3],
                final_train_loss=0.3,
                epochs=5,
            ),
            benchmark_results={
                "new_model": BenchmarkResultDetail(
                    median_final_error_mm=0.05,
                    p95_final_error_mm=0.10,
                    converge_rate=0.95,
                    trial_errors_mm=[0.02, 0.05, 0.08, 0.03, 0.07],
                    benchmark_trial_ids=["trial_001", "trial_002", "trial_003", "trial_004", "trial_005"],
                ),
                "current_model": BenchmarkResultDetail(
                    median_final_error_mm=0.08,
                    p95_final_error_mm=0.15,
                    converge_rate=0.90,
                    trial_errors_mm=[0.05, 0.08, 0.12, 0.06, 0.10],
                    benchmark_trial_ids=["trial_001", "trial_002", "trial_003", "trial_004", "trial_005"],
                ),
            },
            promoted=True,
            promoted_version="v1.0.0",
        )
    
    return _jobs[train_job_id]
