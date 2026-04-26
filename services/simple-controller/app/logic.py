from __future__ import annotations

import math
from dataclasses import dataclass

from .models import ControlStepInfo, ControlStepRequest, ControlStepResponse


@dataclass
class StepComputation:
    delta_coll_x: float
    delta_coll_y: float
    next_coll_x: float
    next_coll_y: float
    info: ControlStepInfo


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_step(req: ControlStepRequest, tolerance: float | None = None) -> ControlStepResponse:
    state = req.state
    config = req.config

    error_x = state.target_spot_center_x - state.spot_pre_x
    error_y = state.target_spot_center_y - state.spot_pre_y

    # Convert spot error [mm] to coll movement [mm] with fixed scale.
    raw_delta_x = error_x / config.spot_to_coll_scale_x
    raw_delta_y = error_y / config.spot_to_coll_scale_y

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

    info = ControlStepInfo(
        error_x=error_x,
        error_y=error_y,
        distance_pre=distance_pre,
        distance_post=distance_post,
        bolt_offset_x=state.spot_post_x - state.spot_pre_x,
        bolt_offset_y=state.spot_post_y - state.spot_pre_y,
        clipped_x=(raw_delta_x != clipped_delta_x) or (unclamped_next_x != next_coll_x),
        clipped_y=(raw_delta_y != clipped_delta_y) or (unclamped_next_y != next_coll_y),
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
