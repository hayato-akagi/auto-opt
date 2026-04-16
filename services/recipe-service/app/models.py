from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OpticalSystem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wavelength: float = Field(..., gt=0.0)
    ld_tilt: float
    ld_div_fast: float = Field(..., gt=0.0)
    ld_div_slow: float = Field(..., gt=0.0)
    ld_div_fast_err: float
    ld_div_slow_err: float
    ld_emit_w: float = Field(..., gt=0.0)
    ld_emit_h: float = Field(..., gt=0.0)
    num_rays: int = Field(..., ge=1, le=200000)

    coll_r1: float
    coll_r2: float
    coll_k1: float
    coll_k2: float
    coll_t: float = Field(..., gt=0.0)
    coll_n: float = Field(..., gt=1.0)
    dist_ld_coll: float = Field(..., gt=0.0)

    obj_f: float = Field(..., gt=0.0)
    dist_coll_obj: float = Field(..., gt=0.0)
    sensor_pos: float = Field(..., gt=0.0)


class BoltUnitModel(BaseModel):
    """Bolt unit model with position-dependent power-law displacement."""
    model_config = ConfigDict(extra="forbid")

    # Power-law coefficients: Δx = a_x × x0^b_x, Δy = a_y × y0^b_y
    a_x: float = Field(..., ge=-0.5, le=0.5)
    b_x: float = Field(..., gt=0.0, le=2.0)
    a_y: float = Field(..., ge=-0.5, le=0.5)
    b_y: float = Field(..., gt=0.0, le=2.0)
    
    # Position-dependent noise: σ(|x0|) = σ_base + σ_prop × |x0|
    noise_base_x: float = Field(..., ge=0.0)
    noise_prop_x: float = Field(..., ge=0.0)
    noise_base_y: float = Field(..., ge=0.0)
    noise_prop_y: float = Field(..., ge=0.0)


class BoltModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upper: BoltUnitModel
    lower: BoltUnitModel


class CameraSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pixel_w: int = Field(default=640, ge=64, le=4096)
    pixel_h: int = Field(default=480, ge=64, le=4096)
    pixel_pitch_um: float = Field(default=5.3, gt=0.0, le=100.0)
    gaussian_sigma_px: float = Field(default=3.0, ge=0.0, le=50.0)
    fov_width_mm: float = Field(default=1.0, gt=0.0)
    fov_height_mm: float = Field(default=1.0, gt=0.0)


class ExperimentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    engine_type: Literal["KrakenOS", "Simple"] = Field(default="Simple")
    optical_system: OpticalSystem
    bolt_model: BoltModel
    camera: CameraSettings | None = None


class ExperimentCreateResponse(BaseModel):
    experiment_id: str
    name: str
    engine_type: str
    created_at: str


class ExperimentSummary(BaseModel):
    experiment_id: str
    name: str
    engine_type: str
    created_at: str


class ExperimentListResponse(BaseModel):
    experiments: list[ExperimentSummary]


class TrialStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["manual", "control_loop"]
    control: dict[str, Any] | None = None


class TrialCreateResponse(BaseModel):
    trial_id: str
    experiment_id: str
    mode: str
    started_at: str


class TrialListItem(BaseModel):
    trial_id: str
    mode: str
    started_at: str
    total_steps: int
    completed: bool


class TrialListResponse(BaseModel):
    trials: list[TrialListItem]


class StepOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    return_ray_hits: bool = False
    return_images: bool = False


class StepExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coll_x: float
    coll_y: float
    options: StepOptions = Field(default_factory=StepOptions)


class StepExecuteResponse(BaseModel):
    step_index: int
    after_position: dict[str, float]
    sim_after_position: dict[str, Any]
    bolt_shift: dict[str, Any]
    after_bolt: dict[str, float]
    sim_after_bolt: dict[str, Any]
    saved_to: str


class StepRecord(BaseModel):
    step_index: int
    timestamp: str
    command: dict[str, float]
    after_position: dict[str, float]
    sim_after_position: dict[str, Any]
    bolt_shift: dict[str, Any]
    after_bolt: dict[str, float]
    sim_after_bolt: dict[str, Any]


class StepSummary(BaseModel):
    step_index: int
    command: dict[str, float]
    sim_after_position: dict[str, float | None]
    sim_after_bolt: dict[str, float | None]


class StepListResponse(BaseModel):
    steps: list[StepSummary]


class CompleteTrialResponse(BaseModel):
    trial_id: str
    experiment_id: str
    mode: str
    total_steps: int
    final_step: dict[str, float | None] | None
    finished_at: str


class StepImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: Literal["after_position", "after_bolt"]


class StepImagesResponse(BaseModel):
    ray_path_image: str
    spot_diagram_image: str


SweepParamName = Literal["coll_x", "coll_y"]


class SweepBaseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coll_x: float
    coll_y: float


class SweepSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    param_name: SweepParamName
    values: list[float] = Field(..., min_length=1)


class SweepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    base_command: SweepBaseCommand
    sweep: SweepSpec


class SweepResultItem(BaseModel):
    step_index: int
    param_value: float
    sim_after_position: dict[str, float | None]
    sim_after_bolt: dict[str, float | None]


class SweepResponse(BaseModel):
    trial_id: str
    mode: Literal["sweep"]
    sweep_param: SweepParamName
    results: list[SweepResultItem]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
