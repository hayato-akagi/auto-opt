from __future__ import annotations

from app.env_sampling import sample_envs
from app.models import BoltModelDistribution, BoltUnitRange


def _distribution(seed: int = 0) -> BoltModelDistribution:
    return BoltModelDistribution(
        upper=BoltUnitRange(x0_bias_x=(0.0, 0.2), a_x=(-0.1, 0.1), b_x=(0.8, 1.2)),
        lower=BoltUnitRange(),
        seed=seed,
    )


def test_sample_envs_is_deterministic() -> None:
    dist = _distribution(seed=42)
    first = sample_envs(dist, 5)
    second = sample_envs(dist, 5)
    assert first == second


def test_sample_envs_different_seed_differs() -> None:
    envs_a = sample_envs(_distribution(seed=1), 5)
    envs_b = sample_envs(_distribution(seed=2), 5)
    assert envs_a != envs_b


def test_sample_envs_fixed_range_yields_constant_value() -> None:
    dist = BoltModelDistribution(
        upper=BoltUnitRange(a_x=(0.25, 0.25)),
        lower=BoltUnitRange(),
        seed=0,
    )
    envs = sample_envs(dist, 3)
    assert all(env["upper"]["a_x"] == 0.25 for env in envs)


def test_sample_envs_respects_count_and_bounds() -> None:
    dist = _distribution(seed=7)
    envs = sample_envs(dist, 10)
    assert len(envs) == 10
    for env in envs:
        assert -0.1 <= env["upper"]["a_x"] <= 0.1
        assert 0.0 <= env["upper"]["x0_bias_x"] <= 0.2
