from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from .models import RayHit, SimulationRequest, SimulationResponse
from .visualization import render_gaussian_spot_image


def _get_env_float(key: str, default: float) -> float:
    """Get float value from environment variable."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_env_int(key: str, default: int) -> int:
    """Get int value from environment variable."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass
class GaussianSpotParams:
    """Parameters for Gaussian spot calculation."""
    sigma_x_cam: float  # Camera coordinate sigma X (mm)
    sigma_y_cam: float  # Camera coordinate sigma Y (mm)
    spot_center_x: float  # mm
    spot_center_y: float  # mm
    intensity_scale: float  # Intensity scaling factor
    fov_width_mm: float  # Field of view width (mm)
    fov_height_mm: float  # Field of view height (mm)
    pixel_w: int
    pixel_h: int


def run_simulation(params: SimulationRequest) -> SimulationResponse:
    """Run simple Gaussian-based optical simulation."""
    start = time.perf_counter()

    # Get camera settings (from request or environment)
    camera = params.camera
    if camera is None:
        pixel_w = _get_env_int("CAMERA_WIDTH_PX", 640)
        pixel_h = _get_env_int("CAMERA_HEIGHT_PX", 480)
        fov_width_mm = _get_env_float("CAMERA_FOV_WIDTH_MM", 1.0)
        fov_height_mm = _get_env_float("CAMERA_FOV_HEIGHT_MM", 1.0)
    else:
        pixel_w = camera.pixel_w
        pixel_h = camera.pixel_h
        fov_width_mm = camera.fov_width_mm
        fov_height_mm = camera.fov_height_mm

    # Get simulation parameters from environment
    magnification = _get_env_float("MAGNIFICATION", 50.0)
    defocus_coeff = _get_env_float("DEFOCUS_COEFFICIENT", 10.0)
    tilt_sens_x = _get_env_float("TILT_SENSITIVITY_X", 0.1)
    tilt_sens_y = _get_env_float("TILT_SENSITIVITY_Y", 0.1)

    # 1. Base sigma (from LD emission size, 1/e^2 criterion)
    sigma_x_base = (params.ld_emit_w * 1e-3) / 2.0  # um -> mm
    sigma_y_base = (params.ld_emit_h * 1e-3) / 2.0

    # 2. Defocus effect (z-axis shift)
    if params.coll_z_shift != 0:
        defocus_factor = 1.0 + abs(params.coll_z_shift) * defocus_coeff
        sigma_x_eff = sigma_x_base * defocus_factor
        sigma_y_eff = sigma_y_base * defocus_factor
    else:
        sigma_x_eff = sigma_x_base
        sigma_y_eff = sigma_y_base

    # 3. Intensity scaling (area ratio for defocus)
    intensity_scale = (sigma_x_base * sigma_y_base) / (sigma_x_eff * sigma_y_eff)

    # 4. Spot center position (magnification + LD tilt offset)
    tilt_offset_x = params.ld_tilt * tilt_sens_x
    tilt_offset_y = params.ld_tilt * tilt_sens_y
    spot_center_x = params.coll_x_shift * magnification + tilt_offset_x
    spot_center_y = params.coll_y_shift * magnification + tilt_offset_y

    # 5. Camera coordinate sigma
    sigma_cam_x = sigma_x_eff * magnification
    sigma_cam_y = sigma_y_eff * magnification

    # 6. RMS and geometric radius
    spot_rms_radius = float(np.sqrt(sigma_cam_x**2 + sigma_cam_y**2))
    spot_geo_radius = 3.0 * spot_rms_radius

    # 7. Check if spot is outside FOV
    warnings: list[str] = []
    actual_fov_width = fov_width_mm
    actual_fov_height = fov_height_mm
    
    if abs(spot_center_x) > fov_width_mm / 2 or abs(spot_center_y) > fov_height_mm / 2:
        warnings.append("Spot center is outside the field of view")
        # Auto-expand FOV to include spot (2.5x margin)
        actual_fov_width = max(fov_width_mm, abs(spot_center_x) * 2.5)
        actual_fov_height = max(fov_height_mm, abs(spot_center_y) * 2.5)

    # 8. Generate ray hits if requested
    ray_hits: list[RayHit] | None = None
    if params.return_ray_hits:
        rng = np.random.default_rng()
        x_hits = rng.normal(spot_center_x, sigma_cam_x, params.num_rays)
        y_hits = rng.normal(spot_center_y, sigma_cam_y, params.num_rays)
        ray_hits = [
            RayHit(x=float(x), y=float(y))
            for x, y in zip(x_hits, y_hits)
        ]

    # 9. Generate images if requested
    spot_params = GaussianSpotParams(
        sigma_x_cam=sigma_cam_x,
        sigma_y_cam=sigma_cam_y,
        spot_center_x=spot_center_x,
        spot_center_y=spot_center_y,
        intensity_scale=intensity_scale,
        fov_width_mm=actual_fov_width,
        fov_height_mm=actual_fov_height,
        pixel_w=pixel_w,
        pixel_h=pixel_h,
    )

    ray_path_image: str | None = None
    spot_diagram_image: str | None = None

    if params.return_ray_path_image:
        ray_path_image = render_gaussian_spot_image(spot_params)

    if params.return_spot_diagram_image:
        spot_diagram_image = render_gaussian_spot_image(spot_params)

    elapsed_ms = max(1, int(round((time.perf_counter() - start) * 1000)))

    return SimulationResponse(
        spot_center_x=spot_center_x,
        spot_center_y=spot_center_y,
        spot_rms_radius=spot_rms_radius,
        spot_geo_radius=spot_geo_radius,
        spot_peak_x=spot_center_x,  # Same as center for Gaussian
        spot_peak_y=spot_center_y,
        num_rays_launched=params.num_rays,
        num_rays_arrived=params.num_rays,  # No vignetting in simple model
        vignetting_ratio=0.0,
        ray_hits=ray_hits,
        ray_path_image=ray_path_image,
        spot_diagram_image=spot_diagram_image,
        spot_warnings=warnings if warnings else None,
        computation_time_ms=elapsed_ms,
    )
