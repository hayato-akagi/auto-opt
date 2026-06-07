"""LSTM controller step logic.

Each step:
  1. Build 8-dim feature vector from the previous step's result + current position
  2. Run LSTM.step() to get bolt_shift prediction and updated hidden state
  3. Convert bolt_shift → coll-space residual correction (negate + scale)
  4. Add to baseline proportional correction
  5. Apply safety clip and coll range clamp
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from .model import ModelManager

logger = logging.getLogger(__name__)


@dataclass
class LstmStepDecision:
    baseline_delta_x: float
    baseline_delta_y: float
    lstm_residual_x: float
    lstm_residual_y: float
    final_delta_x: float
    final_delta_y: float
    next_coll_x: float
    next_coll_y: float
    safety_triggered: bool


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def make_lstm_features(
    prev_step: dict[str, Any] | None,
    current_spot_x: float,
    current_spot_y: float,
) -> np.ndarray:
    """Build the 8-dim input vector for the LSTM at the current step.

    Args:
        prev_step: The step result dict from the previous simulation step,
                   or None if this is the very first step (after step 0).
        current_spot_x: Current spot x position (sim_after_position from last step + noise)
        current_spot_y: Current spot y position

    Returns:
        (8,) float32 array: [spot_before_x, spot_before_y, delta_x, delta_y,
                             spot_after_x, spot_after_y, current_x, current_y]
    """
    if prev_step is None:
        return np.array(
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, current_spot_x, current_spot_y],
            dtype=np.float32,
        )

    sim_before = prev_step.get("sim_after_position") or {}
    cmd = prev_step.get("command") or {}
    sim_after = prev_step.get("sim_after_bolt") or {}

    return np.array(
        [
            float(sim_before.get("spot_center_x", 0.0)),
            float(sim_before.get("spot_center_y", 0.0)),
            float(cmd.get("coll_x", 0.0)),
            float(cmd.get("coll_y", 0.0)),
            float(sim_after.get("spot_center_x", 0.0)),
            float(sim_after.get("spot_center_y", 0.0)),
            current_spot_x,
            current_spot_y,
        ],
        dtype=np.float32,
    )


def compute_lstm_step(
    *,
    config: Any,
    target_x: float,
    target_y: float,
    current_coll_x: float,
    current_coll_y: float,
    spot_pre_x: float,
    spot_pre_y: float,
    lstm_features: np.ndarray,
    lstm_hidden_state: tuple | None,
    model_manager: ModelManager | None,
) -> tuple[LstmStepDecision, tuple | None]:
    """Compute next collimator position using LSTM residual correction.

    Returns:
        (LstmStepDecision, new_lstm_hidden_state)
        The new hidden state must be passed back on the next call.
    """
    # Baseline proportional correction
    error_x = target_x - spot_pre_x
    error_y = target_y - spot_pre_y
    baseline_x = error_x / config.spot_to_coll_scale_x
    baseline_y = error_y / config.spot_to_coll_scale_y

    # LSTM inference
    residual_x = 0.0
    residual_y = 0.0
    new_hidden = lstm_hidden_state

    if config.model_type == "lstm" and model_manager is not None:
        try:
            bolt_shift, new_hidden = model_manager.step(lstm_features, lstm_hidden_state)
            # bolt_shift is in spot space; convert to coll-space pre-compensation
            # bolt shifts spot by +Δ → move coll by -Δ/scale to pre-compensate
            residual_x = -float(bolt_shift[0]) / config.spot_to_coll_scale_x
            residual_y = -float(bolt_shift[1]) / config.spot_to_coll_scale_y
            logger.debug(
                f"LSTM: bolt_shift=({bolt_shift[0]:.6f}, {bolt_shift[1]:.6f}), "
                f"residual=({residual_x:.6f}, {residual_y:.6f})"
            )
        except Exception as exc:
            logger.warning(f"LSTM inference failed: {exc}, using baseline only")
            residual_x = 0.0
            residual_y = 0.0
            new_hidden = lstm_hidden_state

    # Safety: if residual is too large relative to baseline, ignore it
    baseline_norm = math.hypot(baseline_x, baseline_y)
    residual_norm = math.hypot(residual_x, residual_y)
    threshold = config.safety_threshold * baseline_norm + config.safety_bias
    safety_triggered = residual_norm > threshold

    if safety_triggered:
        logger.warning(
            f"Safety triggered: residual_norm={residual_norm:.4f} > threshold={threshold:.4f}"
        )
        final_x = baseline_x
        final_y = baseline_y
    else:
        final_x = baseline_x + residual_x
        final_y = baseline_y + residual_y

    # Clip delta
    final_x = _clip(final_x, -config.delta_clip_x, config.delta_clip_x)
    final_y = _clip(final_y, -config.delta_clip_y, config.delta_clip_y)

    # Clamp to coll range
    next_coll_x = _clip(current_coll_x + final_x, config.coll_x_min, config.coll_x_max)
    next_coll_y = _clip(current_coll_y + final_y, config.coll_y_min, config.coll_y_max)

    decision = LstmStepDecision(
        baseline_delta_x=baseline_x,
        baseline_delta_y=baseline_y,
        lstm_residual_x=residual_x,
        lstm_residual_y=residual_y,
        final_delta_x=next_coll_x - current_coll_x,
        final_delta_y=next_coll_y - current_coll_y,
        next_coll_x=next_coll_x,
        next_coll_y=next_coll_y,
        safety_triggered=safety_triggered,
    )
    return decision, new_hidden
