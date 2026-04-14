from __future__ import annotations

import base64
from io import BytesIO

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _figure_to_base64_png(fig: plt.Figure) -> str:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def render_ray_path_image(z_positions: np.ndarray, x_paths: np.ndarray, y_paths: np.ndarray) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharex=True)

    for x_path in x_paths:
        axes[0].plot(z_positions, x_path, color="#1f77b4", alpha=0.3, linewidth=0.8)
    axes[0].set_title("X-Z projection")
    axes[0].set_xlabel("Z [mm]")
    axes[0].set_ylabel("X [mm]")
    axes[0].grid(alpha=0.3)

    for y_path in y_paths:
        axes[1].plot(z_positions, y_path, color="#ff7f0e", alpha=0.3, linewidth=0.8)
    axes[1].set_title("Y-Z projection")
    axes[1].set_xlabel("Z [mm]")
    axes[1].set_ylabel("Y [mm]")
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    return _figure_to_base64_png(fig)


def render_spot_diagram_image(hits: np.ndarray) -> str:
    fig, ax = plt.subplots(figsize=(5, 5))

    ax.scatter(hits[:, 0], hits[:, 1], s=9, alpha=0.7, edgecolors="none")
    ax.axhline(0.0, color="black", linewidth=0.8, alpha=0.5)
    ax.axvline(0.0, color="black", linewidth=0.8, alpha=0.5)
    ax.set_title("Spot diagram")
    ax.set_xlabel("X [mm]")
    ax.set_ylabel("Y [mm]")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.3)

    fig.tight_layout()
    return _figure_to_base64_png(fig)
