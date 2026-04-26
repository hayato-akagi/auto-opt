import pytest

from app.logic import compute_step
from app.models import ControlStepRequest, ControlStepState, SimpleControllerConfig


def test_compute_step_basic() -> None:
    payload = ControlStepRequest(
        algorithm="simple-controller",
        config=SimpleControllerConfig(
            spot_to_coll_scale_x=50.0,
            spot_to_coll_scale_y=50.0,
            delta_clip_x=0.05,
            delta_clip_y=0.05,
            coll_x_min=-0.5,
            coll_x_max=0.5,
            coll_y_min=-0.5,
            coll_y_max=0.5,
        ),
        state=ControlStepState(
            target_spot_center_x=0.0,
            target_spot_center_y=0.0,
            current_coll_x=0.1,
            current_coll_y=-0.1,
            spot_pre_x=0.02,
            spot_pre_y=-0.01,
            spot_post_x=0.03,
            spot_post_y=-0.02,
            step_index=0,
            history=[],
        ),
    )

    result = compute_step(payload, tolerance=0.05)

    assert result.delta_coll_x == pytest.approx(-0.0004)
    assert result.delta_coll_y == pytest.approx(0.0002)
    assert result.next_coll_x == pytest.approx(0.0996)
    assert result.next_coll_y == pytest.approx(-0.0998)
    assert result.converged is True
    assert result.info.error_x == pytest.approx(-0.02)
    assert result.info.error_y == pytest.approx(0.01)


def test_compute_step_clipping_and_clamping() -> None:
    payload = ControlStepRequest(
        algorithm="simple-controller",
        config=SimpleControllerConfig(
            spot_to_coll_scale_x=50.0,
            spot_to_coll_scale_y=50.0,
            delta_clip_x=0.05,
            delta_clip_y=0.05,
            coll_x_min=-0.1,
            coll_x_max=0.1,
            coll_y_min=-0.1,
            coll_y_max=0.1,
        ),
        state=ControlStepState(
            target_spot_center_x=0.0,
            target_spot_center_y=0.0,
            current_coll_x=0.09,
            current_coll_y=-0.09,
            spot_pre_x=-1.0,
            spot_pre_y=1.0,
            spot_post_x=0.0,
            spot_post_y=0.0,
            step_index=0,
            history=[],
        ),
    )

    result = compute_step(payload)

    assert result.delta_coll_x == pytest.approx(0.01)  # clamped by coll_x_max
    assert result.delta_coll_y == pytest.approx(-0.01)  # clamped by coll_y_min
    assert result.next_coll_x == pytest.approx(0.1)
    assert result.next_coll_y == pytest.approx(-0.1)
    assert result.info.clipped_x is True
    assert result.info.clipped_y is True
