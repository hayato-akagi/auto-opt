from __future__ import annotations

import base64
from io import BytesIO
from typing import TYPE_CHECKING

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from .simulation import GaussianSpotParams


def render_gaussian_spot_image(params: GaussianSpotParams) -> str:
    """
    Render Gaussian intensity distribution as grayscale image.
    
    Args:
        params: GaussianSpotParams with sigma_x_cam, sigma_y_cam, spot_center_x/y,
                intensity_scale, fov_width_mm, fov_height_mm, pixel_w, pixel_h
    
    Returns:
        Base64-encoded PNG image string
    """
    
    # Create coordinate grid
    x = np.linspace(
        -params.fov_width_mm / 2,
        params.fov_width_mm / 2,
        params.pixel_w
    )
    y = np.linspace(
        -params.fov_height_mm / 2,
        params.fov_height_mm / 2,
        params.pixel_h
    )
    X, Y = np.meshgrid(x, y)
    
    # Calculate 2D Gaussian distribution
    dx = X - params.spot_center_x
    dy = Y - params.spot_center_y
    
    if params.sigma_x_cam > 0 and params.sigma_y_cam > 0:
        intensity = np.exp(
            -(dx**2 / (2 * params.sigma_x_cam**2) + dy**2 / (2 * params.sigma_y_cam**2))
        )
    else:
        # If sigma is zero, create delta function-like peak
        intensity = np.zeros_like(X)
        center_idx_y = params.pixel_h // 2
        center_idx_x = params.pixel_w // 2
        intensity[center_idx_y, center_idx_x] = 1.0
    
    # Apply intensity scaling (for defocus effect)
    intensity_scaled = intensity * params.intensity_scale
    
    # Convert to grayscale (0-255), clipped
    grayscale = np.clip(intensity_scaled * 255, 0, 255).astype(np.uint8)
    
    # Create matplotlib figure
    fig, ax = plt.subplots(figsize=(6, 6))
    
    # Display grayscale image (Y axis: bottom to top as in matplotlib default)
    ax.imshow(
        grayscale,
        extent=[-params.fov_width_mm/2, params.fov_width_mm/2,
                -params.fov_height_mm/2, params.fov_height_mm/2],
        origin='lower',
        cmap='gray',
        vmin=0,
        vmax=255
    )
    
    # Add crosshair at optical axis
    ax.axhline(0.0, color='red', linewidth=0.5, alpha=0.5, linestyle='--')
    ax.axvline(0.0, color='red', linewidth=0.5, alpha=0.5, linestyle='--')
    
    ax.set_xlabel('X [mm] (Slow axis)')
    ax.set_ylabel('Y [mm] (Fast axis)')
    ax.set_title('Gaussian Spot Intensity')
    ax.set_aspect('equal', adjustable='box')
    ax.grid(alpha=0.3, linewidth=0.5)
    
    fig.tight_layout()
    
    # Convert to base64 PNG
    buffer = BytesIO()
    fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
    plt.close(fig)
    
    return base64.b64encode(buffer.getvalue()).decode('ascii')
