import os

import numpy as np

from .models import BoltAxisDelta, BoltDetail, BoltModel, BoltResult, BoltUnitModel


def _sample_noise(rng: np.random.Generator, std_dev: float) -> float:
    """Sample noise from normal distribution.
    
    Args:
        rng: Random number generator
        std_dev: Standard deviation (sigma)
    
    Returns:
        Sampled noise value
    """
    if std_dev == 0.0:
        return 0.0
    return float(rng.normal(0.0, std_dev))


def _compute_single_bolt_delta(
    x0: float,
    y0: float,
    bolt_unit: BoltUnitModel,
    rng: np.random.Generator,
) -> BoltAxisDelta:
    """Compute displacement for a single bolt with position-dependent power-law model.
    
    Model:
        Δx = a_x × x0^b_x + N(0, σ_x(|x0|)²)
        Δy = a_y × y0^b_y + N(0, σ_y(|y0|)²)
    
    Position-dependent noise:
        σ_x(|x0|) = noise_base_x + noise_prop_x × |x0|
        σ_y(|y0|) = noise_base_y + noise_prop_y × |y0|
    
    Args:
        x0: Initial X position before bolt fastening (mm)
        y0: Initial Y position before bolt fastening (mm)
        bolt_unit: Bolt unit model parameters
        rng: Random number generator
    
    Returns:
        BoltAxisDelta with computed displacements
    """
    # Deterministic component (power-law model)
    # Handle negative values: preserve sign and use absolute value for power
    if x0 == 0:
        delta_x_det = 0.0
    else:
        delta_x_det = np.sign(x0) * bolt_unit.a_x * (abs(x0) ** bolt_unit.b_x)
    
    if y0 == 0:
        delta_y_det = 0.0
    else:
        delta_y_det = np.sign(y0) * bolt_unit.a_y * (abs(y0) ** bolt_unit.b_y)
    
    # Position-dependent noise standard deviation (using absolute value for symmetry)
    sigma_x = max(0.0, bolt_unit.noise_base_x + bolt_unit.noise_prop_x * abs(x0))
    sigma_y = max(0.0, bolt_unit.noise_base_y + bolt_unit.noise_prop_y * abs(y0))
    
    # Add noise
    delta_x = delta_x_det + _sample_noise(rng, sigma_x)
    delta_y = delta_y_det + _sample_noise(rng, sigma_y)
    
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
