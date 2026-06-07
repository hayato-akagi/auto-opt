import pytest

from app.logic import compute_step, update_bolt_shift_estimate
from app.models import AdaptiveControllerConfig, ControlStepRequest, ControlStepState


def _make_request(
    *,
    target_x: float = 0.0,
    target_y: float = 0.0,
    current_coll_x: float = 0.0,
    current_coll_y: float = 0.0,
    spot_pre_x: float = 0.0,
    spot_pre_y: float = 0.0,
    spot_post_x: float = 0.0,
    spot_post_y: float = 0.0,
    bolt_shift_estimate_x: float = 0.0,
    bolt_shift_estimate_y: float = 0.0,
    scale_x: float = 50.0,
    scale_y: float = 50.0,
    alpha: float = 0.5,
) -> ControlStepRequest:
    return ControlStepRequest(
        algorithm="adaptive-controller",
        config=AdaptiveControllerConfig(
            spot_to_coll_scale_x=scale_x,
            spot_to_coll_scale_y=scale_y,
            delta_clip_x=0.05,
            delta_clip_y=0.05,
            coll_x_min=-0.5,
            coll_x_max=0.5,
            coll_y_min=-0.5,
            coll_y_max=0.5,
            alpha=alpha,
        ),
        state=ControlStepState(
            target_spot_center_x=target_x,
            target_spot_center_y=target_y,
            current_coll_x=current_coll_x,
            current_coll_y=current_coll_y,
            spot_pre_x=spot_pre_x,
            spot_pre_y=spot_pre_y,
            spot_post_x=spot_post_x,
            spot_post_y=spot_post_y,
            step_index=0,
            history=[],
            bolt_shift_estimate_x=bolt_shift_estimate_x,
            bolt_shift_estimate_y=bolt_shift_estimate_y,
        ),
    )


class TestComputeStep:
    def test_zero_estimate_matches_simple_controller(self) -> None:
        # With no bolt_shift estimate, adaptive should behave like simple-controller
        req = _make_request(
            spot_pre_x=0.02,
            spot_pre_y=-0.01,
            bolt_shift_estimate_x=0.0,
            bolt_shift_estimate_y=0.0,
        )
        result = compute_step(req)
        # baseline only: error = -0.02, -0.02/50 = -0.0004
        assert result.delta_coll_x == pytest.approx(-0.02 / 50.0)
        assert result.delta_coll_y == pytest.approx(0.01 / 50.0)
        assert result.info.adaptive_delta_x == pytest.approx(0.0)
        assert result.info.adaptive_delta_y == pytest.approx(0.0)

    def test_adaptive_correction_reduces_error(self) -> None:
        # bolt shifts spot right by 0.02 → estimate = 0.02
        # adaptive correction = -0.02 / 50 = -0.0004 (move coll left to pre-compensate)
        req = _make_request(
            spot_pre_x=0.0,
            spot_pre_y=0.0,
            bolt_shift_estimate_x=0.02,
            bolt_shift_estimate_y=0.0,
        )
        result = compute_step(req)
        assert result.info.baseline_delta_x == pytest.approx(0.0)
        assert result.info.adaptive_delta_x == pytest.approx(-0.02 / 50.0)
        assert result.delta_coll_x == pytest.approx(-0.02 / 50.0)

    def test_combined_baseline_and_adaptive(self) -> None:
        # spot is 0.1 right of target, bolt estimate = 0.05 right
        # baseline = -(0.1 / 50) = -0.002
        # adaptive = -(0.05 / 50) = -0.001
        # total = -0.003
        req = _make_request(
            target_x=0.0,
            spot_pre_x=0.1,
            bolt_shift_estimate_x=0.05,
        )
        result = compute_step(req)
        assert result.info.baseline_delta_x == pytest.approx(-0.1 / 50.0)
        assert result.info.adaptive_delta_x == pytest.approx(-0.05 / 50.0)
        assert result.delta_coll_x == pytest.approx(-0.003)

    def test_convergence_check(self) -> None:
        req = _make_request(
            target_x=0.0,
            target_y=0.0,
            spot_post_x=0.0005,
            spot_post_y=0.0003,
        )
        result = compute_step(req, tolerance=0.001)
        assert result.converged is True

    def test_no_convergence_when_above_tolerance(self) -> None:
        req = _make_request(
            target_x=0.0,
            target_y=0.0,
            spot_post_x=0.01,
            spot_post_y=0.0,
        )
        result = compute_step(req, tolerance=0.001)
        assert result.converged is False

    def test_delta_clipping(self) -> None:
        # Large error → delta would exceed delta_clip_x=0.05
        req = _make_request(spot_pre_x=5.0)  # error = -5.0 → raw_delta = -0.1 → clipped to -0.05
        result = compute_step(req)
        assert result.delta_coll_x == pytest.approx(-0.05)
        assert result.info.clipped_x is True

    def test_coll_range_clamping(self) -> None:
        # coll at 0.49, error sends it to 0.49 + 0.05 = 0.54 → clamped to 0.5
        req = _make_request(
            current_coll_x=0.49,
            spot_pre_x=-2.5,  # large negative error → large positive delta (clipped to 0.05)
        )
        result = compute_step(req)
        assert result.next_coll_x == pytest.approx(0.5)
        assert result.info.clipped_x is True

    def test_negative_bolt_shift_estimate(self) -> None:
        # bolt shifts spot left by 0.02 → estimate = -0.02
        # adaptive = -(-0.02) / 50 = +0.0004 (move coll right to pre-compensate)
        req = _make_request(
            spot_pre_x=0.0,
            bolt_shift_estimate_x=-0.02,
        )
        result = compute_step(req)
        assert result.info.adaptive_delta_x == pytest.approx(0.02 / 50.0)

    def test_info_fields_populated(self) -> None:
        req = _make_request(
            target_x=0.1,
            spot_pre_x=0.05,
            spot_post_x=0.08,
            bolt_shift_estimate_x=0.01,
            bolt_shift_estimate_y=0.02,
        )
        result = compute_step(req)
        assert result.info.error_x == pytest.approx(0.05)
        assert result.info.bolt_shift_estimate_x == pytest.approx(0.01)
        assert result.info.bolt_shift_estimate_y == pytest.approx(0.02)
        assert result.info.distance_pre == pytest.approx(0.05)


class TestUpdateBoltShiftEstimate:
    def test_alpha_1_uses_only_observation(self) -> None:
        new_x, new_y = update_bolt_shift_estimate(0.1, 0.2, 0.5, 0.6, alpha=1.0)
        assert new_x == pytest.approx(0.5)
        assert new_y == pytest.approx(0.6)

    def test_alpha_0_keeps_estimate(self) -> None:
        # alpha must be > 0 per model validation, but we test the math at alpha→0
        new_x, new_y = update_bolt_shift_estimate(0.1, 0.2, 0.9, 0.8, alpha=1e-9)
        assert new_x == pytest.approx(0.1, abs=1e-6)
        assert new_y == pytest.approx(0.2, abs=1e-6)

    def test_alpha_half_averages(self) -> None:
        new_x, new_y = update_bolt_shift_estimate(0.0, 0.0, 0.4, 0.6, alpha=0.5)
        assert new_x == pytest.approx(0.2)
        assert new_y == pytest.approx(0.3)

    def test_repeated_observations_converge(self) -> None:
        # After many steps with alpha=0.5, estimate converges to true value
        est_x, est_y = 0.0, 0.0
        true_x, true_y = 0.03, -0.02
        for _ in range(30):
            est_x, est_y = update_bolt_shift_estimate(est_x, est_y, true_x, true_y, alpha=0.5)
        assert est_x == pytest.approx(true_x, abs=1e-6)
        assert est_y == pytest.approx(true_y, abs=1e-6)
