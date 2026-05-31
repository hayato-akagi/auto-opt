"""AI controller logic with model inference."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from .models import AiControllerConfig

if TYPE_CHECKING:
    from .model import ModelManager

logger = logging.getLogger(__name__)


# Must match trainer's architecture constants
MAX_HISTORY_STEPS = 10
STEP_FEATURE_DIM = 6
CURRENT_FEATURE_DIM = 2
MAX_INPUT_DIM = MAX_HISTORY_STEPS * STEP_FEATURE_DIM + CURRENT_FEATURE_DIM  # 62


@dataclass
class AiStepDecision:
    baseline_delta_x: float
    baseline_delta_y: float
    dnn_residual_x: float
    dnn_residual_y: float
    final_delta_x: float
    final_delta_y: float
    next_coll_x: float
    next_coll_y: float
    safety_triggered: bool


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _extract_step_features(step: dict) -> list[float]:
    """Extract the 6 per-step features from a completed step dict."""
    sim_before = step.get("sim_after_position", {}) or {}
    cmd = step.get("command", {}) or {}
    sim_after = step.get("sim_after_bolt", {}) or {}
    return [
        float(sim_before.get("spot_center_x", 0.0)),
        float(sim_before.get("spot_center_y", 0.0)),
        float(cmd.get("coll_x", 0.0)),
        float(cmd.get("coll_y", 0.0)),
        float(sim_after.get("spot_center_x", 0.0)),
        float(sim_after.get("spot_center_y", 0.0)),
    ]


def extract_features_for_inference(
    *,
    prev_steps: list[dict] | None,
    current_spot_x: float,
    current_spot_y: float,
    n_history: int,
    max_history: int = MAX_HISTORY_STEPS,
) -> np.ndarray:
    """Build a fixed (max_history*6+2,) feature vector with zero-padding.
    
    The most recent n_history steps from prev_steps are used; older / unused
    slots are zero-padded at the BEGINNING of the vector. Current spot position
    is appended at the end.
    """
    if n_history < 1 or n_history > max_history:
        raise ValueError(f"n_history must be in [1, {max_history}], got {n_history}")
    
    prev_steps = prev_steps or []
    # Take last n_history steps
    history = prev_steps[-n_history:] if n_history > 0 else []
    
    features: list[float] = []
    n_actual = len(history)
    n_padding = max_history - n_actual
    
    # Zero-padding at start
    for _ in range(n_padding):
        features.extend([0.0] * STEP_FEATURE_DIM)
    
    # Actual history
    for step in history:
        features.extend(_extract_step_features(step))
    
    # Current spot
    features.append(float(current_spot_x))
    features.append(float(current_spot_y))
    
    return np.array(features, dtype=np.float32)


def compute_ai_step(
    *,
    config: AiControllerConfig,
    target_x: float,
    target_y: float,
    current_coll_x: float,
    current_coll_y: float,
    spot_pre_x: float,
    spot_pre_y: float,
    model_manager: ModelManager | None = None,
    prev_steps: list[dict] | None = None,
) -> AiStepDecision:
    """Compute AI controller step with model inference.
    
    Args:
        config: AI controller configuration
        target_x: Target spot position (x) in mm
        target_y: Target spot position (y) in mm
        current_coll_x: Current collimator position (x) in mm
        current_coll_y: Current collimator position (y) in mm
        spot_pre_x: Current spot position before adjustment (x) in mm
        spot_pre_y: Current spot position before adjustment (y) in mm
        model_manager: Model manager for inference (optional)
        prev_step: Previous step data for feature extraction (optional)
    
    Returns:
        AiStepDecision with baseline, residual, and final control outputs
    """
    # Baseline proportional controller
    error_x = target_x - spot_pre_x
    error_y = target_y - spot_pre_y
    baseline_x = error_x / config.spot_to_coll_scale_x
    baseline_y = error_y / config.spot_to_coll_scale_y
    
    # Model inference for residual
    residual_x = 0.0
    residual_y = 0.0
    
    if config.model_type != "baseline_only" and model_manager is not None:
        try:
            # Determine n_history: config overrides model, else use model's saved value
            n_history = config.n_history
            if n_history is None:
                n_history = getattr(model_manager, "n_history", 1) or 1
            
            # Extract features (62-dim with zero padding)
            features = extract_features_for_inference(
                prev_steps=prev_steps,
                current_spot_x=spot_pre_x,
                current_spot_y=spot_pre_y,
                n_history=n_history,
                max_history=getattr(model_manager, "max_history_steps", MAX_HISTORY_STEPS),
            )
            
            # Run inference
            features_batch = features.reshape(1, -1)
            prediction = model_manager.predict(features_batch)  # (1, 2)
            
            # Model predicts bolt_shift in spot space; negate and scale to coll space
            # bolt_shift > 0 means spot moved right → pre-compensate with coll left
            residual_x = -float(prediction[0, 0]) / config.spot_to_coll_scale_x
            residual_y = -float(prediction[0, 1]) / config.spot_to_coll_scale_y

            logger.debug(
                f"Model prediction: bolt_shift=({prediction[0,0]:.6f}, {prediction[0,1]:.6f}), "
                f"residual=({residual_x:.6f}, {residual_y:.6f})"
            )
            
        except Exception as e:
            logger.warning(f"Model inference failed: {e}, using baseline only")
            residual_x = 0.0
            residual_y = 0.0
    
    # Safety check: if residual is too large, ignore it
    baseline_norm = math.hypot(baseline_x, baseline_y)
    residual_norm = math.hypot(residual_x, residual_y)
    threshold = config.safety_threshold * baseline_norm + config.safety_bias
    safety_triggered = residual_norm > threshold
    
    if safety_triggered:
        logger.warning(f"Safety triggered: residual_norm={residual_norm:.6f} > threshold={threshold:.6f}")
        final_x = baseline_x
        final_y = baseline_y
    else:
        final_x = baseline_x + residual_x
        final_y = baseline_y + residual_y
    
    # Clip delta
    final_x = _clip(final_x, -config.delta_clip_x, config.delta_clip_x)
    final_y = _clip(final_y, -config.delta_clip_y, config.delta_clip_y)
    
    # Compute next collimator position
    unclamped_next_x = current_coll_x + final_x
    unclamped_next_y = current_coll_y + final_y
    next_coll_x = _clip(unclamped_next_x, config.coll_x_min, config.coll_x_max)
    next_coll_y = _clip(unclamped_next_y, config.coll_y_min, config.coll_y_max)
    
    return AiStepDecision(
        baseline_delta_x=baseline_x,
        baseline_delta_y=baseline_y,
        dnn_residual_x=residual_x,
        dnn_residual_y=residual_y,
        final_delta_x=next_coll_x - current_coll_x,
        final_delta_y=next_coll_y - current_coll_y,
        next_coll_x=next_coll_x,
        next_coll_y=next_coll_y,
        safety_triggered=safety_triggered,
    )

