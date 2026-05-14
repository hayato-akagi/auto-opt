from __future__ import annotations

import math
from dataclasses import dataclass

from .models import AiControllerConfig


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


def compute_ai_step(
	*,
	config: AiControllerConfig,
	target_x: float,
	target_y: float,
	current_coll_x: float,
	current_coll_y: float,
	spot_pre_x: float,
	spot_pre_y: float,
) -> AiStepDecision:
	# Baseline proportional controller.
	error_x = target_x - spot_pre_x
	error_y = target_y - spot_pre_y
	baseline_x = error_x / config.spot_to_coll_scale_x
	baseline_y = error_y / config.spot_to_coll_scale_y

	# Residual model placeholder.
	if config.model_type == "baseline_only":
		residual_x = 0.0
		residual_y = 0.0
	else:
		residual_x = 0.0
		residual_y = 0.0

	baseline_norm = math.hypot(baseline_x, baseline_y)
	residual_norm = math.hypot(residual_x, residual_y)
	threshold = config.safety_threshold * baseline_norm + config.safety_bias
	safety_triggered = residual_norm > threshold

	if safety_triggered:
		final_x = baseline_x
		final_y = baseline_y
	else:
		final_x = baseline_x + residual_x
		final_y = baseline_y + residual_y

	final_x = _clip(final_x, -config.delta_clip_x, config.delta_clip_x)
	final_y = _clip(final_y, -config.delta_clip_y, config.delta_clip_y)

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
