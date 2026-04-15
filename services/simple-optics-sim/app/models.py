from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CameraSettings(BaseModel):
    """Camera settings for image generation."""
    pixel_w: int = Field(default=640, ge=64, le=4096)
    pixel_h: int = Field(default=480, ge=64, le=4096)
    pixel_pitch_um: float = Field(default=5.3, gt=0.0, le=100.0)
    gaussian_sigma_px: float = Field(default=3.0, ge=0.0, le=50.0)
    fov_width_mm: float = Field(default=1.0, gt=0.0)
    fov_height_mm: float = Field(default=1.0, gt=0.0)


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Simple engine only uses: ld_emit_w/h, coll_x/y/z_shift, ld_tilt, camera
    # Other fields optional for compatibility with KrakenOS API
    wavelength: float = Field(default=0.000638, gt=0.0, description="Laser wavelength in nm (not used)")
    ld_tilt: float = Field(default=0.0, description="LD tilt against optical axis in deg")
    ld_div_fast: float = Field(default=30.0, gt=0.0, description="Fast-axis divergence FWHM in deg (not used)")
    ld_div_slow: float = Field(default=10.0, gt=0.0, description="Slow-axis divergence FWHM in deg (not used)")
    ld_div_fast_err: float = Field(default=0.0, description="Fast-axis manufacturing error in deg (not used)")
    ld_div_slow_err: float = Field(default=0.0, description="Slow-axis manufacturing error in deg (not used)")
    ld_emit_w: float = Field(..., gt=0.0, description="Emitter width in um")
    ld_emit_h: float = Field(..., gt=0.0, description="Emitter height in um")
    num_rays: int = Field(default=10000, ge=1, le=200000, description="Number of launched rays (not used)")

    coll_r1: float = Field(default=0.0, description="Collimator surface-1 radius in mm (not used)")
    coll_r2: float = Field(default=0.0, description="Collimator surface-2 radius in mm (not used)")
    coll_k1: float = Field(default=0.0, description="Collimator surface-1 conic constant (not used)")
    coll_k2: float = Field(default=0.0, description="Collimator surface-2 conic constant (not used)")
    coll_t: float = Field(default=1.0, gt=0.0, description="Collimator center thickness in mm (not used)")
    coll_n: float = Field(default=1.5, gt=1.0, description="Collimator refractive index (not used)")
    dist_ld_coll: float = Field(default=1.0, gt=0.0, description="Distance from LD to collimator front in mm (not used)")
    coll_x_shift: float = Field(default=0.0, description="Collimator decenter in X/slow axis in mm")
    coll_y_shift: float = Field(default=0.0, description="Collimator decenter in Y/fast axis in mm")
    coll_z_shift: float = Field(default=0.0, description="Collimator decenter in Z/optical axis in mm")

    obj_f: float = Field(default=1.0, gt=0.0, description="Objective focal length in mm (not used)")
    dist_coll_obj: float = Field(default=1.0, gt=0.0, description="Distance from collimator back to objective in mm (not used)")
    sensor_pos: float = Field(default=1.0, gt=0.0, description="Distance from objective to sensor in mm (not used)")

    return_ray_hits: bool = Field(default=False)
    return_ray_path_image: bool = Field(default=False)
    return_spot_diagram_image: bool = Field(default=False)

    camera: CameraSettings | None = Field(default=None, description="Camera settings")


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

    spot_warnings: list[str] | None = Field(default=None, description="Warnings if any")

    computation_time_ms: int


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
