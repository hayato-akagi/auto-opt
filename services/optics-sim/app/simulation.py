from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from .models import RayHit, SimulationRequest, SimulationResponse
from .visualization import render_ray_path_image, render_spot_diagram_image


class SimulationError(RuntimeError):
    """Raised when the simulation backend cannot produce a result."""


@dataclass
class TraceResult:
    launched: int
    hits: np.ndarray
    z_positions: np.ndarray
    x_paths: np.ndarray
    y_paths: np.ndarray


def run_simulation(params: SimulationRequest) -> SimulationResponse:
    start = time.perf_counter()

    try:
        if _mock_mode_enabled():
            trace = _run_mock_trace(params)
        else:
            trace = _run_kraken_trace(params)
    except SimulationError:
        raise
    except Exception as exc:  # pragma: no cover - defensive error conversion
        raise SimulationError(str(exc)) from exc

    elapsed_ms = max(1, int(round((time.perf_counter() - start) * 1000)))
    return _build_response(params=params, trace=trace, computation_time_ms=elapsed_ms)


def _mock_mode_enabled() -> bool:
    value = os.getenv("MOCK_SIMULATION", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _run_mock_trace(params: SimulationRequest) -> TraceResult:
    seed = _deterministic_seed(params)
    rng = np.random.default_rng(seed)
    return _trace_optical_system(params=params, rng=rng, deterministic=True)


def _run_kraken_trace(params: SimulationRequest) -> TraceResult:
    kraken, surf_class, setup_class, kraken_sys, ray_keeper = _import_kraken_modules()

    rng = np.random.default_rng()
    x0, y0, z0, l_dir, m_dir, n_dir = _sample_source_rays(params, rng)

    try:
        surfaces = _build_kraken_surfaces(params, surf_class)
        setup = setup_class.Setup()
        system = kraken_sys.system(surfaces, setup)
        keeper = ray_keeper.raykeeper(system)

        # KrakenOS expects array-like ray bundles and wavelength in um.
        kraken.TraceLoop(
            x0,
            y0,
            z0,
            l_dir,
            m_dir,
            n_dir,
            params.wavelength * 1e-3,
            keeper,
            1,
        )
    except Exception as exc:
        raise SimulationError(f"KrakenOS trace failed: {exc}") from exc

    valid_paths: list[np.ndarray] = []
    for path in keeper.valid_XYZ:
        array_path = np.asarray(path, dtype=float)
        if array_path.ndim == 2 and array_path.shape[0] > 0 and array_path.shape[1] >= 3:
            valid_paths.append(array_path)

    if not valid_paths:
        raise SimulationError("no rays reached the sensor")

    hits = np.array([[float(path[-1, 0]), float(path[-1, 1])] for path in valid_paths], dtype=float)

    sampled_paths = _sample_paths(valid_paths, max_count=120)
    min_len = min(path.shape[0] for path in sampled_paths)
    trimmed_paths = [path[:min_len, :3] for path in sampled_paths]

    z_positions = trimmed_paths[0][:, 2]
    x_paths = np.stack([path[:, 0] for path in trimmed_paths], axis=0)
    y_paths = np.stack([path[:, 1] for path in trimmed_paths], axis=0)

    return TraceResult(
        launched=params.num_rays,
        hits=hits,
        z_positions=z_positions,
        x_paths=x_paths,
        y_paths=y_paths,
    )


def _import_kraken_modules() -> tuple[Any, Any, Any, Any, Any]:
    try:
        import KrakenOS as kraken  # type: ignore[import-not-found]
        import KrakenOS.KrakenSys as kraken_sys  # type: ignore[import-not-found]
        import KrakenOS.RayKeeper as ray_keeper  # type: ignore[import-not-found]
        import KrakenOS.SetupClass as setup_class  # type: ignore[import-not-found]
        import KrakenOS.SurfClass as surf_class  # type: ignore[import-not-found]
    except Exception as exc:
        raise SimulationError(
            "KrakenOS is not available. Install KrakenOS or set MOCK_SIMULATION=true."
        ) from exc

    return kraken, surf_class, setup_class, kraken_sys, ray_keeper


def _build_kraken_surfaces(params: SimulationRequest, surf_class: Any) -> list[Any]:
    emit_w_mm = params.ld_emit_w * 1e-3
    emit_h_mm = params.ld_emit_h * 1e-3

    reference_index = 1.517
    index_scale = (reference_index - 1.0) / max(1e-6, params.coll_n - 1.0)
    coll_r1_eff = params.coll_r1 * index_scale
    coll_r2_eff = params.coll_r2 * index_scale

    coll_diameter = max(3.0, 0.5 * max(abs(coll_r1_eff), abs(coll_r2_eff), 1.0))
    obj_diameter = max(3.0, params.obj_f * 1.6)

    return [
        surf_class.surf(
            Thickness=params.dist_ld_coll,
            Diameter=max(0.2, max(emit_w_mm, emit_h_mm) * 20.0),
            Glass="AIR",
            Name="ld-source-plane",
        ),
        surf_class.surf(
            Rc=coll_r1_eff,
            k=params.coll_k1,
            Thickness=params.coll_t,
            Diameter=coll_diameter,
            Glass="BK7",
            ShiftX=params.coll_x_shift,
            ShiftY=params.coll_y_shift,
            Name="collimator-s1",
        ),
        surf_class.surf(
            Rc=coll_r2_eff,
            k=params.coll_k2,
            Thickness=params.dist_coll_obj,
            Diameter=coll_diameter,
            Glass="AIR",
            ShiftX=params.coll_x_shift,
            ShiftY=params.coll_y_shift,
            Name="collimator-s2",
        ),
        surf_class.surf(
            Thin_Lens=params.obj_f,
            Thickness=params.sensor_pos,
            Diameter=obj_diameter,
            Glass="AIR",
            Name="objective-thin-lens",
        ),
        surf_class.surf(
            Thickness=0.0,
            Diameter=max(15.0, obj_diameter * 2.5),
            Glass="AIR",
            Name="sensor-plane",
        ),
    ]


def _sample_source_rays(
    params: SimulationRequest,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    launched = params.num_rays

    emit_w_mm = params.ld_emit_w * 1e-3
    emit_h_mm = params.ld_emit_h * 1e-3

    x0 = rng.uniform(-emit_w_mm / 2.0, emit_w_mm / 2.0, launched)
    y0 = rng.uniform(-emit_h_mm / 2.0, emit_h_mm / 2.0, launched)
    z0 = np.zeros(launched, dtype=float)

    slow_sigma_deg = _fwhm_to_sigma(max(1e-6, params.ld_div_slow + params.ld_div_slow_err))
    fast_sigma_deg = _fwhm_to_sigma(max(1e-6, params.ld_div_fast + params.ld_div_fast_err))

    theta_x = np.deg2rad(rng.normal(loc=params.ld_tilt, scale=slow_sigma_deg, size=launched))
    theta_y = np.deg2rad(rng.normal(loc=0.0, scale=fast_sigma_deg, size=launched))

    vx = np.tan(theta_x)
    vy = np.tan(theta_y)
    vz = np.ones(launched, dtype=float)

    norm = np.sqrt(vx * vx + vy * vy + vz * vz)
    l_dir = vx / norm
    m_dir = vy / norm
    n_dir = vz / norm

    return x0, y0, z0, l_dir, m_dir, n_dir


def _sample_paths(paths: list[np.ndarray], max_count: int) -> list[np.ndarray]:
    if len(paths) <= max_count:
        return paths

    indices = np.linspace(0, len(paths) - 1, max_count, dtype=int)
    return [paths[int(index)] for index in indices]


def _deterministic_seed(params: SimulationRequest) -> int:
    key = "|".join(
        [
            f"{params.wavelength:.9f}",
            f"{params.ld_tilt:.9f}",
            f"{params.ld_div_fast:.9f}",
            f"{params.ld_div_slow:.9f}",
            f"{params.ld_div_fast_err:.9f}",
            f"{params.ld_div_slow_err:.9f}",
            f"{params.ld_emit_w:.9f}",
            f"{params.ld_emit_h:.9f}",
            str(params.num_rays),
            f"{params.coll_r1:.9f}",
            f"{params.coll_r2:.9f}",
            f"{params.coll_k1:.9f}",
            f"{params.coll_k2:.9f}",
            f"{params.coll_t:.9f}",
            f"{params.coll_n:.9f}",
            f"{params.dist_ld_coll:.9f}",
            f"{params.coll_x_shift:.9f}",
            f"{params.coll_y_shift:.9f}",
            f"{params.obj_f:.9f}",
            f"{params.dist_coll_obj:.9f}",
            f"{params.sensor_pos:.9f}",
        ]
    )
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**32)


def _trace_optical_system(
    params: SimulationRequest,
    rng: np.random.Generator,
    deterministic: bool,
) -> TraceResult:
    launched = params.num_rays

    emit_w_mm = params.ld_emit_w * 1e-3
    emit_h_mm = params.ld_emit_h * 1e-3

    x0 = rng.uniform(-emit_w_mm / 2.0, emit_w_mm / 2.0, launched)
    y0 = rng.uniform(-emit_h_mm / 2.0, emit_h_mm / 2.0, launched)

    slow_sigma_deg = _fwhm_to_sigma(max(1e-6, params.ld_div_slow + params.ld_div_slow_err))
    fast_sigma_deg = _fwhm_to_sigma(max(1e-6, params.ld_div_fast + params.ld_div_fast_err))

    tx0 = np.tan(np.deg2rad(rng.normal(loc=params.ld_tilt, scale=slow_sigma_deg, size=launched)))
    ty0 = np.tan(np.deg2rad(rng.normal(loc=0.0, scale=fast_sigma_deg, size=launched)))

    z_ld = 0.0
    z_coll_front = params.dist_ld_coll
    z_coll_back = z_coll_front + params.coll_t
    z_obj = z_coll_back + params.dist_coll_obj
    z_sensor = z_obj + params.sensor_pos

    z_positions = np.array([z_ld, z_coll_front, z_obj, z_sensor], dtype=float)

    x1 = x0 + (z_coll_front - z_ld) * tx0
    y1 = y0 + (z_coll_front - z_ld) * ty0

    x_lens = x1 - params.coll_x_shift
    y_lens = y1 - params.coll_y_shift

    f_coll = _estimate_collimator_focal_length(params)
    tx1 = tx0 - (x_lens / f_coll)
    ty1 = ty0 - (y_lens / f_coll)

    asphere_strength = 1e-4 * (1.0 + 0.2 * (params.coll_k1 + params.coll_k2))
    tx1 -= asphere_strength * np.power(x_lens, 3)
    ty1 -= asphere_strength * np.power(y_lens, 3)

    x2 = x1 + (z_obj - z_coll_front) * tx1
    y2 = y1 + (z_obj - z_coll_front) * ty1

    tx2 = tx1 - (x2 / params.obj_f)
    ty2 = ty1 - (y2 / params.obj_f)

    x3 = x2 + (z_sensor - z_obj) * tx2
    y3 = y2 + (z_sensor - z_obj) * ty2

    coll_aperture_radius = max(0.35, 0.35 * max(abs(params.coll_r1), abs(params.coll_r2), 1.0))
    obj_aperture_radius = max(0.5, params.obj_f * 0.45)

    inside_collimator = np.hypot(x_lens, y_lens) <= coll_aperture_radius
    inside_objective = np.hypot(x2, y2) <= obj_aperture_radius
    arrived_mask = inside_collimator & inside_objective

    if not deterministic:
        base_loss = np.clip(
            0.01
            + 0.006 * (abs(params.coll_x_shift) + abs(params.coll_y_shift))
            + 0.0008 * abs(params.ld_tilt),
            0.0,
            0.35,
        )
        arrived_mask &= rng.random(launched) >= base_loss

    if not np.any(arrived_mask):
        arrived_mask[int(np.argmin(np.hypot(x3, y3)))] = True

    hits = np.column_stack((x3[arrived_mask], y3[arrived_mask]))

    sample_count = min(120, launched)
    if sample_count == launched:
        sample_indices = np.arange(launched)
    else:
        sample_indices = np.linspace(0, launched - 1, sample_count, dtype=int)

    x_paths = np.column_stack(
        (
            x0[sample_indices],
            x1[sample_indices],
            x2[sample_indices],
            x3[sample_indices],
        )
    )
    y_paths = np.column_stack(
        (
            y0[sample_indices],
            y1[sample_indices],
            y2[sample_indices],
            y3[sample_indices],
        )
    )

    return TraceResult(
        launched=launched,
        hits=hits,
        z_positions=z_positions,
        x_paths=x_paths,
        y_paths=y_paths,
    )


def _estimate_collimator_focal_length(params: SimulationRequest) -> float:
    epsilon = 1e-9

    r1 = params.coll_r1 if abs(params.coll_r1) > epsilon else math.copysign(epsilon, params.coll_r1 or 1.0)
    r2 = params.coll_r2 if abs(params.coll_r2) > epsilon else math.copysign(epsilon, params.coll_r2 or 1.0)

    power = (params.coll_n - 1.0) * (
        (1.0 / r1)
        - (1.0 / r2)
        + ((params.coll_n - 1.0) * params.coll_t) / (params.coll_n * r1 * r2)
    )

    if abs(power) < epsilon:
        return 1e9

    return 1.0 / power


def _fwhm_to_sigma(fwhm: float) -> float:
    return fwhm / (2.0 * math.sqrt(2.0 * math.log(2.0)))


def _compute_peak_xy(hits: np.ndarray) -> tuple[float, float]:
    if hits.shape[0] == 1:
        return float(hits[0, 0]), float(hits[0, 1])

    bins = max(8, min(64, int(round(math.sqrt(hits.shape[0])))))
    histogram, x_edges, y_edges = np.histogram2d(hits[:, 0], hits[:, 1], bins=bins)
    ix, iy = np.unravel_index(int(np.argmax(histogram)), histogram.shape)

    peak_x = float((x_edges[ix] + x_edges[ix + 1]) * 0.5)
    peak_y = float((y_edges[iy] + y_edges[iy + 1]) * 0.5)
    return peak_x, peak_y


def _build_response(
    params: SimulationRequest,
    trace: TraceResult,
    computation_time_ms: int,
) -> SimulationResponse:
    hits = trace.hits

    center_x = float(np.mean(hits[:, 0]))
    center_y = float(np.mean(hits[:, 1]))

    dx = hits[:, 0] - center_x
    dy = hits[:, 1] - center_y
    radius_sq = dx * dx + dy * dy

    rms_radius = float(math.sqrt(float(np.mean(radius_sq))))
    geo_radius = float(math.sqrt(float(np.max(radius_sq))))

    peak_x, peak_y = _compute_peak_xy(hits)

    arrived = int(hits.shape[0])
    vignetting_ratio = 1.0 - (arrived / trace.launched)

    ray_hits = None
    if params.return_ray_hits:
        ray_hits = [RayHit(x=float(x), y=float(y)) for x, y in hits]

    ray_path_image = None
    if params.return_ray_path_image:
        ray_path_image = render_ray_path_image(trace.z_positions, trace.x_paths, trace.y_paths)

    spot_diagram_image = None
    if params.return_spot_diagram_image:
        spot_diagram_image = render_spot_diagram_image(hits)

    return SimulationResponse(
        spot_center_x=center_x,
        spot_center_y=center_y,
        spot_rms_radius=rms_radius,
        spot_geo_radius=geo_radius,
        spot_peak_x=peak_x,
        spot_peak_y=peak_y,
        num_rays_launched=trace.launched,
        num_rays_arrived=arrived,
        vignetting_ratio=float(np.clip(vignetting_ratio, 0.0, 1.0)),
        ray_hits=ray_hits,
        ray_path_image=ray_path_image,
        spot_diagram_image=spot_diagram_image,
        computation_time_ms=computation_time_ms,
    )
