"""Adaptive controller step logic.

Each step applies proportional baseline correction PLUS a pre-compensation
for the estimated bolt shift.  The estimate is maintained externally (runner)
and passed in via state.bolt_shift_estimate_x/y.
"""

from __future__ import annotations

import math

from .models import ControlStepInfo, ControlStepRequest, ControlStepResponse


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_step(req: ControlStepRequest, tolerance: float | None = None) -> ControlStepResponse:
    """Compute next collimator position using baseline + adaptive correction.

    The adaptive correction pre-compensates the bolt shift so the spot lands
    closer to the target than the baseline-only controller would achieve.

    correction = baseline(proportional) + adaptive(-estimate/scale)
    """
    state = req.state
    config = req.config

    error_x = state.target_spot_center_x - state.spot_pre_x
    error_y = state.target_spot_center_y - state.spot_pre_y

    # Proportional baseline (same as simple-controller)
    baseline_x = error_x / config.spot_to_coll_scale_x
    baseline_y = error_y / config.spot_to_coll_scale_y

    # Pre-compensate estimated bolt shift: bolt shifts spot by +Δ, so move coll by -Δ/scale
    adaptive_x = -state.bolt_shift_estimate_x / config.spot_to_coll_scale_x
    adaptive_y = -state.bolt_shift_estimate_y / config.spot_to_coll_scale_y

    raw_delta_x = baseline_x + adaptive_x
    raw_delta_y = baseline_y + adaptive_y

    clipped_delta_x = _clip(raw_delta_x, -config.delta_clip_x, config.delta_clip_x)
    clipped_delta_y = _clip(raw_delta_y, -config.delta_clip_y, config.delta_clip_y)

    unclamped_next_x = state.current_coll_x + clipped_delta_x
    unclamped_next_y = state.current_coll_y + clipped_delta_y

    next_coll_x = _clip(unclamped_next_x, config.coll_x_min, config.coll_x_max)
    next_coll_y = _clip(unclamped_next_y, config.coll_y_min, config.coll_y_max)

    delta_coll_x = next_coll_x - state.current_coll_x
    delta_coll_y = next_coll_y - state.current_coll_y

    distance_pre = math.hypot(error_x, error_y)
    distance_post = math.hypot(
        state.target_spot_center_x - state.spot_post_x,
        state.target_spot_center_y - state.spot_post_y,
    )

    clipped_x = (raw_delta_x != clipped_delta_x) or (unclamped_next_x != next_coll_x)
    clipped_y = (raw_delta_y != clipped_delta_y) or (unclamped_next_y != next_coll_y)

    info = ControlStepInfo(
        error_x=error_x,
        error_y=error_y,
        distance_pre=distance_pre,
        distance_post=distance_post,
        bolt_offset_x=state.spot_post_x - state.spot_pre_x,
        bolt_offset_y=state.spot_post_y - state.spot_pre_y,
        baseline_delta_x=baseline_x,
        baseline_delta_y=baseline_y,
        adaptive_delta_x=adaptive_x,
        adaptive_delta_y=adaptive_y,
        bolt_shift_estimate_x=state.bolt_shift_estimate_x,
        bolt_shift_estimate_y=state.bolt_shift_estimate_y,
        clipped_x=clipped_x,
        clipped_y=clipped_y,
    )

    converged = False
    if tolerance is not None:
        converged = distance_post < tolerance

    return ControlStepResponse(
        delta_coll_x=delta_coll_x,
        delta_coll_y=delta_coll_y,
        next_coll_x=next_coll_x,
        next_coll_y=next_coll_y,
        converged=converged,
        info=info,
    )


def update_bolt_shift_estimate(
    estimate_x: float,
    estimate_y: float,
    observed_x: float,
    observed_y: float,
    alpha: float,
) -> tuple[float, float]:
    """Update EMA estimate with a new observation.

    alpha=1.0 means discard history and use only the latest observation.
    alpha=0.5 gives equal weight to old estimate and new observation.
    """
    new_x = alpha * observed_x + (1.0 - alpha) * estimate_x
    new_y = alpha * observed_y + (1.0 - alpha) * estimate_y
    return new_x, new_y
