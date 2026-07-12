"""Deterministic bolt_model env sampling, shared by training and evaluation paths."""

from __future__ import annotations

import random
from typing import Any

from .models import BoltModelDistribution


def sample_range(rng: random.Random, lo_hi: tuple[float, float]) -> float:
    lo, hi = lo_hi
    if lo == hi:
        return float(lo)
    return rng.uniform(float(lo), float(hi))


def sample_bolt_unit(rng: random.Random, unit) -> dict[str, float]:
    return {
        "x0_bias_x": sample_range(rng, unit.x0_bias_x),
        "x0_bias_y": sample_range(rng, unit.x0_bias_y),
        "a_x": sample_range(rng, unit.a_x),
        "b_x": sample_range(rng, unit.b_x),
        "a_y": sample_range(rng, unit.a_y),
        "b_y": sample_range(rng, unit.b_y),
        "noise_ratio_min_x": unit.noise_ratio_min_x,
        "noise_ratio_max_x": unit.noise_ratio_max_x,
        "noise_ratio_min_y": unit.noise_ratio_min_y,
        "noise_ratio_max_y": unit.noise_ratio_max_y,
    }


def sample_envs(
    distribution: BoltModelDistribution,
    n_envs: int,
) -> list[dict[str, Any]]:
    """Deterministically sample n_envs bolt_model dicts from the distribution."""
    rng = random.Random(distribution.seed)
    envs: list[dict[str, Any]] = []
    for _ in range(n_envs):
        envs.append({
            "upper": sample_bolt_unit(rng, distribution.upper),
            "lower": sample_bolt_unit(rng, distribution.lower),
        })
    return envs
