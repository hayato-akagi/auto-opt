from pydantic import BaseModel, Field


class BoltUnitModel(BaseModel):
    """Bolt unit model parameters for position-dependent power-law displacement.
    
    Displacement model:
        Δx = a_x × x0^b_x + N(0, σ_x(|x0|)²)
        Δy = a_y × y0^b_y + N(0, σ_y(|y0|)²)
    
    Position-dependent noise:
        σ(|x0|) = max(0, σ_base + σ_prop × |x0|)
    """
    # Power-law coefficients for X direction
    a_x: float = Field(..., ge=-0.5, le=0.5, description="X direction coefficient (dimensionless)")
    b_x: float = Field(..., gt=0.0, le=2.0, description="X direction power exponent (dimensionless)")
    
    # Power-law coefficients for Y direction
    a_y: float = Field(..., ge=-0.5, le=0.5, description="Y direction coefficient (dimensionless)")
    b_y: float = Field(..., gt=0.0, le=2.0, description="Y direction power exponent (dimensionless)")
    
    # Position-dependent noise: σ(|x0|) = σ_base + σ_prop × |x0|
    noise_base_x: float = Field(..., ge=0.0, description="X-axis base noise (mm)")
    noise_prop_x: float = Field(..., ge=0.0, description="X-axis position-proportional noise (dimensionless)")
    noise_base_y: float = Field(..., ge=0.0, description="Y-axis base noise (mm)")
    noise_prop_y: float = Field(..., ge=0.0, description="Y-axis position-proportional noise (dimensionless)")


class BoltModel(BaseModel):
    upper: BoltUnitModel
    lower: BoltUnitModel


class BoltApplyRequest(BaseModel):
    x0: float = Field(..., description="Initial X position before bolt fastening in mm")
    y0: float = Field(..., description="Initial Y position before bolt fastening in mm")
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
