from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReleasePerturbation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    std_x: float = Field(default=0.0, ge=0.0)
    std_y: float = Field(default=0.0, ge=0.0)


class SimpleControllerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spot_to_coll_scale_x: float = Field(default=50.0, gt=0.0)
    spot_to_coll_scale_y: float = Field(default=50.0, gt=0.0)
    delta_clip_x: float = Field(default=0.05, gt=0.0)
    delta_clip_y: float = Field(default=0.05, gt=0.0)
    coll_x_min: float = Field(default=-0.5)
    coll_x_max: float = Field(default=0.5)
    coll_y_min: float = Field(default=-0.5)
    coll_y_max: float = Field(default=0.5)
    release_perturbation: ReleasePerturbation = Field(default_factory=ReleasePerturbation)


class TargetSpot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spot_center_x: float
    spot_center_y: float


class InitialColl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coll_x: float = 0.0
    coll_y: float = 0.0


class ControlRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(..., min_length=1)
    algorithm: str = Field(default="simple-controller")
    config: SimpleControllerConfig = Field(default_factory=SimpleControllerConfig)
    target: TargetSpot
    initial_coll: InitialColl = Field(default_factory=InitialColl)
    max_steps: int = Field(default=20, ge=0)
    tolerance: float = Field(default=0.001, gt=0.0)
    random_seed: int | None = Field(default=None, ge=0)


class ControlStepState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_spot_center_x: float
    target_spot_center_y: float
    current_coll_x: float
    current_coll_y: float
    spot_pre_x: float
    spot_pre_y: float
    spot_post_x: float
    spot_post_y: float
    step_index: int = Field(default=0, ge=0)
    history: list[dict[str, Any]] = Field(default_factory=list)


class ControlStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: str = Field(default="simple-controller")
    config: SimpleControllerConfig = Field(default_factory=SimpleControllerConfig)
    state: ControlStepState


class ControlStepInfo(BaseModel):
    error_x: float
    error_y: float
    distance_pre: float
    distance_post: float
    bolt_offset_x: float
    bolt_offset_y: float
    clipped_x: bool
    clipped_y: bool


class ControlStepResponse(BaseModel):
    delta_coll_x: float
    delta_coll_y: float
    next_coll_x: float
    next_coll_y: float
    converged: bool
    info: ControlStepInfo


class InitialObservation(BaseModel):
    step_index: int
    initial_coll_x: float
    initial_coll_y: float
    spot_pre_x: float
    spot_pre_y: float
    spot_post_x: float
    spot_post_y: float
    boot_correction_x: float
    boot_correction_y: float


class ControlRunResponse(BaseModel):
    trial_id: str
    algorithm: str
    converged: bool
    steps: int
    initial_observation: InitialObservation
    final_spot_center_x: float
    final_spot_center_y: float
    final_spot_rms_radius: float | None
    final_distance: float


class AlgorithmDescription(BaseModel):
    name: str
    description: str
    config_schema: dict[str, Any]


class AlgorithmsResponse(BaseModel):
    algorithms: list[AlgorithmDescription]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
