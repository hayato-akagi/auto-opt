from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReleasePerturbationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    std_x: float = Field(default=0.01, ge=0.0,
                         description="Gaussian std of bolt-release observation noise in x (mm)")
    std_y: float = Field(default=0.01, ge=0.0,
                         description="Gaussian std of bolt-release observation noise in y (mm)")


class ControllerConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    spot_to_coll_scale_x: float = Field(default=50.0)
    spot_to_coll_scale_y: float = Field(default=50.0)
    delta_clip_x: float = Field(default=0.1)
    delta_clip_y: float = Field(default=0.1)
    coll_x_min: float = Field(default=-0.5)
    coll_x_max: float = Field(default=0.5)
    coll_y_min: float = Field(default=-0.5)
    coll_y_max: float = Field(default=0.5)
    release_perturbation: ReleasePerturbationConfig = Field(
        default_factory=ReleasePerturbationConfig
    )


class TargetSpot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spot_center_x: float
    spot_center_y: float


class InitialColl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coll_x: float = 0.0
    coll_y: float = 0.0


class CollectionTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(..., min_length=1)
    seeds: list[int] = Field(default_factory=list)


class CollectionJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str | None = None
    algorithm: Literal["simple-controller", "ai-controller", "adaptive-controller", "lstm-controller"] = "simple-controller"
    controller_config: ControllerConfig = Field(default_factory=ControllerConfig)
    target: TargetSpot
    initial_coll: InitialColl = Field(default_factory=InitialColl)
    max_steps: int = Field(default=10, ge=0)
    tolerance: float = Field(default=0.05, gt=0.0)
    tasks: list[CollectionTask] = Field(default_factory=list)
    max_workers: int = Field(default=4, ge=1, le=32)


class TaskResult(BaseModel):
    experiment_id: str
    seed: int
    trial_id: str | None = None
    converged: bool | None = None
    steps: int | None = None
    error: str | None = None


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    total_tasks: int
    created_at: str


class JobStatusResponse(BaseModel):
    job_id: str
    algorithm: str
    status: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    started_at: str
    finished_at: str | None = None
    task_results: list[TaskResult] = Field(default_factory=list)


class JobListResponse(BaseModel):
    jobs: list[JobStatusResponse]


# ---------- Generation Pipeline ----------


class PipelineModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_history: int = Field(default=3, ge=1, le=10)
    hidden_dim: int = Field(default=128, gt=0, le=2048)
    num_layers: int = Field(default=2, ge=1, le=8, description="LSTM layers (ignored for MLP)")
    epochs: int = Field(default=20, ge=1, le=500)
    batch_size: int = Field(default=32, ge=1, le=256)
    learning_rate: float = Field(default=1e-3, gt=0.0)
    only_converged: bool = Field(default=False)
    warm_start: bool = Field(
        default=True,
        description="Initialize trainer with the previous generation's weights",
    )


class PipelineStoppingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_success_rate: float = Field(default=0.95, gt=0.0, le=1.0)
    early_stopping_patience: int = Field(default=3, ge=1)


class BoltUnitRange(BaseModel):
    """Sampling ranges for a single bolt unit (upper or lower).

    Each parameter is [min, max]. min==max means a fixed value (no variation).
    Defaults are 0 (no effect) so unspecified units don't perturb spots.
    """
    model_config = ConfigDict(extra="forbid")

    x0_bias_x: tuple[float, float] = Field(default=(0.0, 0.0))
    x0_bias_y: tuple[float, float] = Field(default=(0.0, 0.0))
    a_x: tuple[float, float] = Field(default=(0.0, 0.0))
    b_x: tuple[float, float] = Field(default=(1.0, 1.0))
    a_y: tuple[float, float] = Field(default=(0.0, 0.0))
    b_y: tuple[float, float] = Field(default=(1.0, 1.0))
    noise_ratio_min_x: float = Field(default=0.01, ge=0.0, le=1.0)
    noise_ratio_max_x: float = Field(default=0.05, ge=0.0, le=1.0)
    noise_ratio_min_y: float = Field(default=0.01, ge=0.0, le=1.0)
    noise_ratio_max_y: float = Field(default=0.05, ge=0.0, le=1.0)


class BoltModelDistribution(BaseModel):
    """Per-environment bolt_model sampling distribution.

    If None, the orchestrator falls back to the experiment's default bolt_model
    (all envs identical).
    """
    model_config = ConfigDict(extra="forbid")

    upper: BoltUnitRange = Field(default_factory=BoltUnitRange)
    lower: BoltUnitRange = Field(default_factory=BoltUnitRange)
    seed: int = Field(default=0, description="Seed for deterministic env sampling")


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gen0_controller: Literal["simple-controller", "adaptive-controller"] = Field(
        default="simple-controller",
        description="Controller used for Gen 0 data collection",
    )
    gen1plus_controller: Literal["ai-controller", "lstm-controller"] = Field(
        default="ai-controller",
        description="Controller used for Gen 1+ data collection",
    )
    adaptive_alpha: float = Field(
        default=1.0, gt=0.0, le=1.0,
        description="EMA weight for bolt_shift update in adaptive-controller (1.0 = latest obs only)",
    )
    n_parallel_envs: int = Field(default=10, ge=1, le=1000)
    trials_per_env: int = Field(default=1, ge=1, le=50)
    n_generations: int = Field(default=5, ge=1, le=100)
    max_steps: int = Field(default=10, ge=1, le=200)
    tolerance: float = Field(default=0.05, gt=0.0)
    controller_config: ControllerConfig = Field(default_factory=ControllerConfig)
    target: TargetSpot
    initial_coll: InitialColl = Field(default_factory=InitialColl)
    model_config_train: PipelineModelConfig = Field(default_factory=PipelineModelConfig)
    stopping: PipelineStoppingConfig = Field(default_factory=PipelineStoppingConfig)
    bolt_distribution: BoltModelDistribution | None = Field(
        default=None,
        description="If set, each env gets a unique bolt_model sampled from this distribution",
    )
    initial_coll_range_x: float = Field(
        default=0.0, ge=0.0,
        description="Each trial's initial coll_x is sampled from Uniform(base ± range). 0 = fixed.",
    )
    initial_coll_range_y: float = Field(
        default=0.0, ge=0.0,
        description="Each trial's initial coll_y is sampled from Uniform(base ± range). 0 = fixed.",
    )
    extra_experiment_ids: list[str] = Field(
        default_factory=list,
        description="Additional experiment IDs from past pipeline runs to include in every training job",
    )
    poll_interval_sec: float = Field(default=2.0, gt=0.0)
    train_timeout_sec: float = Field(default=1800.0, gt=0.0)


class PipelineCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(..., min_length=1)
    config: PipelineConfig


class GenerationResult(BaseModel):
    gen_id: int
    status: str  # pending|collecting|training|completed|failed
    controller: str
    model_path: str | None = None
    train_job_id: str | None = None
    total_trials: int = 0
    converged_trials: int = 0
    success_rate: float | None = None
    final_train_loss: float | None = None
    # Detailed metrics
    steps_per_trial: list[int] = Field(default_factory=list)
    final_distances: list[float] = Field(default_factory=list)
    epoch_losses: list[float] = Field(default_factory=list)
    trial_ids: list[str] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class PipelineCreateResponse(BaseModel):
    pipeline_id: str
    status: str
    experiment_id: str
    created_at: str


class PipelineStatusResponse(BaseModel):
    pipeline_id: str
    experiment_id: str
    status: str  # running|completed|failed|stopped
    current_generation: int = 0
    total_generations: int
    progress: float = 0.0
    generations: list[GenerationResult] = Field(default_factory=list)
    started_at: str
    finished_at: str | None = None
    error: str | None = None


class PipelineListResponse(BaseModel):
    pipelines: list[PipelineStatusResponse]
