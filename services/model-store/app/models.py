from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class ModelMeta(BaseModel):
    """Metadata about a trained model."""

    version: str = Field(..., description="Model version string (e.g., v1.0.0)")
    model_type: str = Field(..., description="Type: 'mlp' or 'baseline_only'")
    status: str = Field(
        ..., description="Status: 'current' (in use), 'candidate' (awaiting approval), 'archived'"
    )
    benchmark_metrics: dict | None = Field(
        default=None, description="Benchmark results (from trainer)"
    )
    benchmark_trial_ids: list[str] = Field(
        default_factory=list, description="Trial IDs used for benchmarking"
    )
    benchmark_experiment_ids: list[str] = Field(
        default_factory=list, description="Experiment IDs used for benchmarking"
    )
    train_job_id: str | None = Field(default=None, description="Associated training job ID")
    created_at: str = Field(..., description="ISO timestamp when model was created")
    promoted_at: str | None = Field(default=None, description="ISO timestamp when model was promoted to 'current'")


class ModelListResponse(BaseModel):
    """Response to GET /models endpoint."""

    models: list[ModelMeta]
    current_version: str | None = Field(default=None)


class ModelPromoteRequest(BaseModel):
    """Request to promote a model to 'current' status."""

    version: str


class ModelPromoteResponse(BaseModel):
    """Response to promoting a model."""

    version: str
    new_status: str
    promoted_at: str

