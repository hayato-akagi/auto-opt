from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReleasePerturbation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    std_x: float = Field(default=0.01, ge=0.0)
    std_y: float = Field(default=0.01, ge=0.0)


class LstmControllerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_type: str = Field(default="baseline_only")
    model_version: str | None = Field(default=None)
    model_path: str | None = Field(default=None)
    spot_to_coll_scale_x: float = Field(default=50.0, gt=0.0)
    spot_to_coll_scale_y: float = Field(default=50.0, gt=0.0)
    delta_clip_x: float = Field(default=0.05, gt=0.0)
    delta_clip_y: float = Field(default=0.05, gt=0.0)
    coll_x_min: float = Field(default=-0.5)
    coll_x_max: float = Field(default=0.5)
    coll_y_min: float = Field(default=-0.5)
    coll_y_max: float = Field(default=0.5)
    safety_threshold: float = Field(default=0.5, ge=0.0)
    safety_bias: float = Field(default=0.01, ge=0.0)
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
    algorithm: str = Field(default="lstm-controller")
    config: LstmControllerConfig = Field(default_factory=LstmControllerConfig)
    target: TargetSpot
    initial_coll: InitialColl = Field(default_factory=InitialColl)
    max_steps: int = Field(default=20, ge=0)
    tolerance: float = Field(default=0.001, gt=0.0)
    random_seed: int | None = Field(default=None, ge=0)
    bolt_model_override: dict[str, Any] | None = Field(default=None)


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
    model_version: str | None = None
    model_type: str
    converged: bool
    steps: int
    initial_observation: InitialObservation
    final_spot_center_x: float
    final_spot_center_y: float
    final_spot_rms_radius: float | None
    final_distance: float


class ModelReloadResponse(BaseModel):
    loaded_version: str | None
    model_type: str


class ModelStatusResponse(BaseModel):
    loaded_version: str | None
    model_type: str
    loaded_at: str
    device: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
