import os

import numpy as np

from .models import BoltAxisDelta, BoltDetail, BoltModel, BoltResult, BoltUnitModel


def _sample_noise(rng: np.random.Generator, std_dev: float) -> float:
    if std_dev == 0.0:
        return 0.0
    return float(rng.normal(0.0, std_dev))


def _compute_single_bolt_delta(
    torque: float,
    bolt_unit: BoltUnitModel,
    rng: np.random.Generator,
) -> BoltAxisDelta:
    delta_x = (torque * bolt_unit.shift_x_per_nm) + _sample_noise(rng, bolt_unit.noise_std_x)
    delta_y = (torque * bolt_unit.shift_y_per_nm) + _sample_noise(rng, bolt_unit.noise_std_y)
    return BoltAxisDelta(delta_x=delta_x, delta_y=delta_y)


def apply_bolt(
    torque_upper: float,
    torque_lower: float,
    bolt_model: BoltModel,
    random_seed: int | None,
) -> BoltResult:
    used_seed = random_seed
    if used_seed is None:
        used_seed = int.from_bytes(os.urandom(4), "big")

    rng = np.random.default_rng(used_seed)

    upper_delta = _compute_single_bolt_delta(torque_upper, bolt_model.upper, rng)
    lower_delta = _compute_single_bolt_delta(torque_lower, bolt_model.lower, rng)

    delta_x = upper_delta.delta_x + lower_delta.delta_x
    delta_y = upper_delta.delta_y + lower_delta.delta_y

    return BoltResult(
        delta_x=delta_x,
        delta_y=delta_y,
        used_seed=used_seed,
        detail=BoltDetail(upper=upper_delta, lower=lower_delta),
    )
