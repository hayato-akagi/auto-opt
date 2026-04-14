from pydantic import BaseModel, Field


class BoltUnitModel(BaseModel):
    shift_x_per_nm: float = Field(..., description="X shift per torque")
    shift_y_per_nm: float = Field(..., description="Y shift per torque")
    noise_std_x: float = Field(..., ge=0.0, description="X-axis noise standard deviation")
    noise_std_y: float = Field(..., ge=0.0, description="Y-axis noise standard deviation")


class BoltModel(BaseModel):
    upper: BoltUnitModel
    lower: BoltUnitModel


class BoltApplyRequest(BaseModel):
    torque_upper: float = Field(..., ge=0.0, le=2.0, description="Upper bolt torque in N.m")
    torque_lower: float = Field(..., ge=0.0, le=2.0, description="Lower bolt torque in N.m")
    bolt_model: BoltModel
    random_seed: int | None = Field(default=None, ge=0, description="Optional random seed")


class BoltAxisDelta(BaseModel):
    delta_x: float
    delta_y: float


class BoltDetail(BaseModel):
    upper: BoltAxisDelta
    lower: BoltAxisDelta


class BoltResult(BaseModel):
    delta_x: float
    delta_y: float
    used_seed: int
    detail: BoltDetail


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
