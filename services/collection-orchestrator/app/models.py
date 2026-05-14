from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


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
    algorithm: Literal["simple-controller", "ai-controller"] = "simple-controller"
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
