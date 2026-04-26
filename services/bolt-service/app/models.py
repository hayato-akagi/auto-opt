from pydantic import BaseModel, Field


class BoltUnitModel(BaseModel):
    """Bolt unit model parameters for position-dependent power-law displacement.
    
    Displacement model:
        x_eff = x0 + x0_bias_x
        y_eff = y0 + x0_bias_y
        Δ_det_x = sign(x_eff) × a_x × |x_eff|^b_x
        Δ_det_y = sign(y_eff) × a_y × |y_eff|^b_y
        r_x ~ Uniform([noise_ratio_min_x, noise_ratio_max_x]) with random sign ±
        r_y ~ Uniform([noise_ratio_min_y, noise_ratio_max_y]) with random sign ±
        Δx = Δ_det_x × (1 + r_x)
        Δy = Δ_det_y × (1 + r_y)
    
    Noise is multiplicative relative noise on deterministic displacement.
    """
    # Bias added to initial position before power-law evaluation.
    # This creates non-zero displacement near x0=0 without adding direct delta offsets.
    x0_bias_x: float = Field(default=0.0, description="X initial-position bias (mm)")
    x0_bias_y: float = Field(default=0.0, description="Y initial-position bias (mm)")

    # Power-law coefficients for X direction
    a_x: float = Field(..., ge=-0.5, le=0.5, description="X direction coefficient (dimensionless)")
    b_x: float = Field(..., gt=0.0, le=2.0, description="X direction power exponent (dimensionless)")
    
    # Power-law coefficients for Y direction
    a_y: float = Field(..., ge=-0.5, le=0.5, description="Y direction coefficient (dimensionless)")
    b_y: float = Field(..., gt=0.0, le=2.0, description="Y direction power exponent (dimensionless)")
    
    # Relative noise ratio (deterministic displacement ±[min,max]%)
    noise_ratio_min_x: float = Field(default=0.01, ge=0.0, le=1.0, description="X-axis minimum relative noise ratio")
    noise_ratio_max_x: float = Field(default=0.05, ge=0.0, le=1.0, description="X-axis maximum relative noise ratio")
    noise_ratio_min_y: float = Field(default=0.01, ge=0.0, le=1.0, description="Y-axis minimum relative noise ratio")
    noise_ratio_max_y: float = Field(default=0.05, ge=0.0, le=1.0, description="Y-axis maximum relative noise ratio")

    # Deprecated legacy parameters kept for backward compatibility.
    noise_base_x: float = Field(default=0.0, ge=0.0, description="[Deprecated] X-axis base noise (mm)")
    noise_prop_x: float = Field(default=0.0, ge=0.0, description="[Deprecated] X-axis position-proportional noise")
    noise_base_y: float = Field(default=0.0, ge=0.0, description="[Deprecated] Y-axis base noise (mm)")
    noise_prop_y: float = Field(default=0.0, ge=0.0, description="[Deprecated] Y-axis position-proportional noise")


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
