import os

import numpy as np

from .models import BoltAxisDelta, BoltDetail, BoltModel, BoltResult, BoltUnitModel


def _sample_signed_ratio(rng: np.random.Generator, min_ratio: float, max_ratio: float) -> float:
    """Sample a signed relative ratio in [min_ratio, max_ratio] with random sign.

    Returns 0 when max_ratio <= 0.
    """
    max_r = max(0.0, float(max_ratio))
    min_r = max(0.0, min(float(min_ratio), max_r))
    if max_r == 0.0:
        return 0.0
    abs_ratio = float(rng.uniform(min_r, max_r))
    sign = -1.0 if rng.random() < 0.5 else 1.0
    return sign * abs_ratio


def _compute_single_bolt_delta(
    x0: float,
    y0: float,
    bolt_unit: BoltUnitModel,
    rng: np.random.Generator,
) -> BoltAxisDelta:
    """Compute displacement for a single bolt with position-dependent power-law model.
    
    Model:
        x_eff = x0 + x0_bias_x
        y_eff = y0 + x0_bias_y
        Δ_det_x = sign(x_eff) × a_x × |x_eff|^b_x
        Δ_det_y = sign(y_eff) × a_y × |y_eff|^b_y
        Δx = Δ_det_x × (1 + r_x), r_x in ±[noise_ratio_min_x, noise_ratio_max_x]
        Δy = Δ_det_y × (1 + r_y), r_y in ±[noise_ratio_min_y, noise_ratio_max_y]
    
    Args:
        x0: Initial X position before bolt fastening (mm)
        y0: Initial Y position before bolt fastening (mm)
        bolt_unit: Bolt unit model parameters
        rng: Random number generator
    
    Returns:
        BoltAxisDelta with computed displacements
    """
    # Effective positions with bias (modeling preload / reference shift).
    x_eff = x0 + bolt_unit.x0_bias_x
    y_eff = y0 + bolt_unit.x0_bias_y

    # Deterministic component from power-law at effective position
    # Handle negative values: preserve sign and use absolute value for power
    if x_eff == 0:
        delta_x_det = 0.0
    else:
        delta_x_det = np.sign(x_eff) * bolt_unit.a_x * (abs(x_eff) ** bolt_unit.b_x)
    
    if y_eff == 0:
        delta_y_det = 0.0
    else:
        delta_y_det = np.sign(y_eff) * bolt_unit.a_y * (abs(y_eff) ** bolt_unit.b_y)
    
    # Multiplicative relative noise around deterministic displacement.
    ratio_x = _sample_signed_ratio(rng, bolt_unit.noise_ratio_min_x, bolt_unit.noise_ratio_max_x)
    ratio_y = _sample_signed_ratio(rng, bolt_unit.noise_ratio_min_y, bolt_unit.noise_ratio_max_y)

    delta_x = delta_x_det * (1.0 + ratio_x)
    delta_y = delta_y_det * (1.0 + ratio_y)
    
    return BoltAxisDelta(delta_x=delta_x, delta_y=delta_y)


def apply_bolt(
    x0: float,
    y0: float,
    bolt_model: BoltModel,
    random_seed: int | None,
) -> BoltResult:
    used_seed = random_seed
    if used_seed is None:
        used_seed = int.from_bytes(os.urandom(4), "big")

    rng = np.random.default_rng(used_seed)

    upper_delta = _compute_single_bolt_delta(x0, y0, bolt_model.upper, rng)
    lower_delta = _compute_single_bolt_delta(x0, y0, bolt_model.lower, rng)

    delta_x = upper_delta.delta_x + lower_delta.delta_x
    delta_y = upper_delta.delta_y + lower_delta.delta_y

    return BoltResult(
        delta_x=delta_x,
        delta_y=delta_y,
        used_seed=used_seed,
        detail=BoltDetail(upper=upper_delta, lower=lower_delta),
    )
