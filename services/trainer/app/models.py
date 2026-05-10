from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class TrainRequest(BaseModel):
    """Request to start a training job."""

    experiment_ids: list[str] = Field(
        ..., min_length=1, description="List of experiment IDs to use for training data"
    )
    model_type: str = Field(
        default="mlp", description="Model type: 'mlp' for MLP, 'baseline_only' for baseline controller"
    )
    epochs: int = Field(default=50, ge=1, le=500)
    batch_size: int = Field(default=32, ge=1, le=256)


class TrainMetrics(BaseModel):
    """Training metrics upon completion."""

    epoch_losses: list[float] = Field(..., description="Loss per epoch (length = epochs)")
    final_train_loss: float
    epochs: int


class BenchmarkResultDetail(BaseModel):
    """Benchmark results for a single model."""

    median_final_error_mm: float
    p95_final_error_mm: float
    converge_rate: float = Field(ge=0.0, le=1.0, description="Fraction of trials that converged")
    trial_errors_mm: list[float] = Field(
        ..., description="Final error for each benchmark trial"
    )
    benchmark_trial_ids: list[str] = Field(
        ..., description="Trial IDs used for benchmarking"
    )


class TrainJobStatus(BaseModel):
    """Status and results of a training job."""

    train_job_id: str
    status: str  # "running" | "completed" | "failed" | "skipped"
    data_stats: dict | None = None
    train_metrics: TrainMetrics | None = None
    benchmark_results: dict[str, "BenchmarkResultDetail"] | None = None  # keys: "new_model", "current_model"
    promoted: bool | None = None
    promoted_version: str | None = None
    error_message: str | None = None


class TrainJobResponse(BaseModel):
    """Response to POST /train request."""

    train_job_id: str
    status: str
    message: str


class TrainJobListResponse(BaseModel):
    """Response to GET /train endpoint."""

    jobs: list[TrainJobStatus]
