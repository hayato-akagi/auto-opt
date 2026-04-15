from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CameraSettings(BaseModel):
    """Camera settings for image generation (ignored by KrakenOS engine)."""
    pixel_w: int = Field(default=640, ge=64, le=4096)
    pixel_h: int = Field(default=480, ge=64, le=4096)
    pixel_pitch_um: float = Field(default=5.3, gt=0.0, le=100.0)
    gaussian_sigma_px: float = Field(default=3.0, ge=0.0, le=50.0)
    fov_width_mm: float = Field(default=1.0, gt=0.0)
    fov_height_mm: float = Field(default=1.0, gt=0.0)


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Changed from forbid to ignore for forward compatibility

    wavelength: float = Field(..., gt=0.0, description="Laser wavelength in nm")
    ld_tilt: float = Field(..., description="LD tilt against optical axis in deg")
    ld_div_fast: float = Field(..., gt=0.0, description="Fast-axis divergence FWHM in deg")
    ld_div_slow: float = Field(..., gt=0.0, description="Slow-axis divergence FWHM in deg")
    ld_div_fast_err: float = Field(..., description="Fast-axis manufacturing error in deg")
    ld_div_slow_err: float = Field(..., description="Slow-axis manufacturing error in deg")
    ld_emit_w: float = Field(..., gt=0.0, description="Emitter width in um")
    ld_emit_h: float = Field(..., gt=0.0, description="Emitter height in um")
    num_rays: int = Field(..., ge=1, le=200000, description="Number of launched rays")

    coll_r1: float = Field(..., description="Collimator surface-1 radius in mm")
    coll_r2: float = Field(..., description="Collimator surface-2 radius in mm")
    coll_k1: float = Field(..., description="Collimator surface-1 conic constant")
    coll_k2: float = Field(..., description="Collimator surface-2 conic constant")
    coll_t: float = Field(..., gt=0.0, description="Collimator center thickness in mm")
    coll_n: float = Field(..., gt=1.0, description="Collimator refractive index")
    dist_ld_coll: float = Field(..., gt=0.0, description="Distance from LD to collimator front in mm")
    coll_x_shift: float = Field(..., description="Collimator decenter in X/slow axis in mm")
    coll_y_shift: float = Field(..., description="Collimator decenter in Y/fast axis in mm")

    obj_f: float = Field(..., gt=0.0, description="Objective focal length in mm")
    dist_coll_obj: float = Field(..., gt=0.0, description="Distance from collimator back to objective in mm")
    sensor_pos: float = Field(..., gt=0.0, description="Distance from objective to sensor in mm")

    return_ray_hits: bool = Field(default=False)
    return_ray_path_image: bool = Field(default=False)
    return_spot_diagram_image: bool = Field(default=False)

    camera: CameraSettings | None = Field(default=None, description="Camera settings (ignored by KrakenOS)")


class RayHit(BaseModel):
    x: float
    y: float


class SimulationResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    spot_center_x: float
    spot_center_y: float
    spot_rms_radius: float
    spot_geo_radius: float
    spot_peak_x: float
    spot_peak_y: float

    num_rays_launched: int
    num_rays_arrived: int
    vignetting_ratio: float

    ray_hits: list[RayHit] | None = None
    ray_path_image: str | None = None
    spot_diagram_image: str | None = None

    spot_warnings: list[str] | None = Field(default=None, description="Warnings (always None for KrakenOS)")

    computation_time_ms: int


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
