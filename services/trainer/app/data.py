"""Data collection from recipe-service and feature engineering."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# Constants for history-based feature extraction
MAX_HISTORY_STEPS = 10  # Maximum history steps the model can handle
STEP_FEATURE_DIM = 6  # Per-step features: spot_before(x,y) + delta(x,y) + spot_after(x,y)
CURRENT_FEATURE_DIM = 2  # Current spot position (x, y)
MAX_INPUT_DIM = MAX_HISTORY_STEPS * STEP_FEATURE_DIM + CURRENT_FEATURE_DIM  # 62


def _extract_step_data(step: dict[str, Any]) -> dict[str, float] | None:
    """Extract step data (spot_before, delta, spot_after) from a recipe step.
    
    Returns dict with keys: spot_before_x, spot_before_y, delta_x, delta_y,
    spot_after_x, spot_after_y. Returns None if data is missing.
    """
    try:
        sim_before = step.get("sim_after_position", {})
        cmd = step.get("command", {})
        sim_after = step.get("sim_after_bolt", {})
        
        return {
            "spot_before_x": float(sim_before.get("spot_center_x", 0.0)),
            "spot_before_y": float(sim_before.get("spot_center_y", 0.0)),
            "delta_x": float(cmd.get("coll_x", 0.0)),
            "delta_y": float(cmd.get("coll_y", 0.0)),
            "spot_after_x": float(sim_after.get("spot_center_x", 0.0)),
            "spot_after_y": float(sim_after.get("spot_center_y", 0.0)),
        }
    except (KeyError, TypeError, ValueError) as e:
        logger.debug(f"Failed to extract step data: {e}")
        return None


def extract_features_with_history(
    steps: list[dict[str, Any]],
    target_step_index: int,
    n_history: int = 3,
    max_history: int = MAX_HISTORY_STEPS,
) -> np.ndarray | None:
    """Extract feature vector with variable history length.
    
    The output is always max_history*6+2 = 62 dimensions (with zero-padding for
    unused history slots). The actual data uses the latest n_history steps before
    target_step_index, plus the current spot position from target_step_index.
    
    Args:
        steps: All steps of the trial (in order)
        target_step_index: Index of the step we're predicting (0-based)
        n_history: Number of history steps to use (1-10)
        max_history: Model's max history (fixed at 10)
        
    Returns:
        Feature vector of shape (max_history*6+2,) or None if extraction failed
    """
    if n_history < 1 or n_history > max_history:
        raise ValueError(f"n_history must be in [1, {max_history}], got {n_history}")
    
    if target_step_index >= len(steps):
        return None
    
    # Get current spot (before adjustment) from target step
    target_step = steps[target_step_index]
    target_before = target_step.get("sim_after_position", {})
    try:
        current_x = float(target_before.get("spot_center_x", 0.0))
        current_y = float(target_before.get("spot_center_y", 0.0))
    except (TypeError, ValueError):
        return None
    
    # Collect previous step data (most recent n_history before target)
    history_data: list[dict[str, float]] = []
    start_idx = max(0, target_step_index - n_history)
    for i in range(start_idx, target_step_index):
        step_data = _extract_step_data(steps[i])
        if step_data is None:
            return None
        history_data.append(step_data)
    
    # Build feature vector: pad first, then history, then current
    features: list[float] = []
    
    # Zero-padding for unused history slots (always at the start)
    n_actual = len(history_data)
    n_padding = max_history - n_actual
    for _ in range(n_padding):
        features.extend([0.0] * STEP_FEATURE_DIM)
    
    # Actual history data
    for step_data in history_data:
        features.extend([
            step_data["spot_before_x"],
            step_data["spot_before_y"],
            step_data["delta_x"],
            step_data["delta_y"],
            step_data["spot_after_x"],
            step_data["spot_after_y"],
        ])
    
    # Current position
    features.append(current_x)
    features.append(current_y)
    
    return np.array(features, dtype=np.float32)


def collect_training_data(
    experiments: list[dict[str, Any]],
    get_trial_steps: callable,
    n_history: int = 1,
    only_converged: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Collect training data from experiments with variable history length.
    
    The feature vector is always MAX_INPUT_DIM (62) dimensions, with the latest
    n_history steps used as actual data and earlier slots zero-padded.
    
    Args:
        experiments: List of experiment dicts with experiment_id and trials
        get_trial_steps: Function(experiment_id, trial_id) -> list[dict]
        n_history: Number of past steps to use as features (1-10)
        only_converged: If True, only use trials that converged
        
    Returns:
        features (N, MAX_INPUT_DIM): Feature vectors
        labels (N, 2): [bolt_shift_x, bolt_shift_y] from spot difference
    """
    features_list: list[np.ndarray] = []
    labels_list: list[np.ndarray] = []
    
    for exp in experiments:
        exp_id = exp.get("experiment_id")
        if not exp_id:
            continue
        
        trials = exp.get("trials", [])
        for trial in trials:
            trial_id = trial.get("trial_id")
            if not trial_id:
                continue
            
            if only_converged and not trial.get("converged", False):
                continue
            
            steps = get_trial_steps(exp_id, trial_id)
            if not steps or len(steps) < 2:
                continue
            
            # For each step (starting from index 1), use prior steps as history
            for i in range(1, len(steps)):
                feature = extract_features_with_history(
                    steps, target_step_index=i, n_history=n_history,
                )
                if feature is None:
                    continue
                
                label = _extract_label(steps[i])
                if label is None:
                    continue
                
                features_list.append(feature)
                labels_list.append(label)
    
    if not features_list:
        logger.warning("No training samples collected")
        return (
            np.zeros((0, MAX_INPUT_DIM), dtype=np.float32),
            np.zeros((0, 2), dtype=np.float32),
        )
    
    features = np.array(features_list, dtype=np.float32)
    labels = np.array(labels_list, dtype=np.float32)
    
    logger.info(
        f"Collected {len(features)} training samples "
        f"(n_history={n_history}, input_dim={features.shape[1]}) "
        f"from {len(experiments)} experiments"
    )
    return features, labels


def _extract_label(curr_step: dict[str, Any]) -> np.ndarray | None:
    """Extract bolt_shift as label from current step.
    
    Returns:
        [bolt_shift_x, bolt_shift_y] in mm (spot space)
    """
    try:
        sim_before = curr_step.get("sim_after_position", {})
        sim_after = curr_step.get("sim_after_bolt", {})
        
        spot_x_before = float(sim_before.get("spot_center_x", 0.0))
        spot_y_before = float(sim_before.get("spot_center_y", 0.0))
        spot_x_after = float(sim_after.get("spot_center_x", 0.0))
        spot_y_after = float(sim_after.get("spot_center_y", 0.0))
        
        bolt_shift_x = spot_x_after - spot_x_before
        bolt_shift_y = spot_y_after - spot_y_before
        
        return np.array([bolt_shift_x, bolt_shift_y], dtype=np.float32)
    except (KeyError, TypeError, ValueError) as e:
        logger.debug(f"Failed to extract label: {e}")
        return None


def collect_training_sequences(
    experiments: list[dict[str, Any]],
    get_trial_steps: callable,
    only_converged: bool = False,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Collect per-trial step sequences for LSTM training.

    Each element in the returned list corresponds to one trial and contains:
      features_seq: (T, 8) float32 — one 8-dim vector per step
      labels_seq:   (T, 2) float32 — bolt_shift per step

    The 8-dim feature at step t is:
      [prev_spot_before_x, prev_spot_before_y,   (from step t-1: sim_after_position)
       prev_delta_x,       prev_delta_y,          (from step t-1: command.coll_x/y)
       prev_spot_after_x,  prev_spot_after_y,     (from step t-1: sim_after_bolt)
       current_x,          current_y]             (from step t:   sim_after_position)

    For t=1 (first real step), the "prev step" is step 0 (initial observation),
    which already reveals the bolt shift via (spot_after - spot_before).
    """
    sequences: list[tuple[np.ndarray, np.ndarray]] = []

    for exp in experiments:
        exp_id = exp.get("experiment_id")
        if not exp_id:
            continue

        for trial in exp.get("trials", []):
            trial_id = trial.get("trial_id")
            if not trial_id:
                continue
            if only_converged and not trial.get("converged", False):
                continue

            steps = get_trial_steps(exp_id, trial_id)
            if not steps or len(steps) < 2:
                continue

            features_seq: list[np.ndarray] = []
            labels_seq: list[np.ndarray] = []

            for i in range(1, len(steps)):
                prev_step = steps[i - 1]
                curr_step = steps[i]

                # Previous step features (6 dims)
                prev_before = prev_step.get("sim_after_position") or {}
                prev_cmd = prev_step.get("command") or {}
                prev_after = prev_step.get("sim_after_bolt") or {}

                # Current position (2 dims) from curr step's sim_after_position
                curr_before = curr_step.get("sim_after_position") or {}

                try:
                    feat = np.array([
                        float(prev_before.get("spot_center_x", 0.0)),
                        float(prev_before.get("spot_center_y", 0.0)),
                        float(prev_cmd.get("coll_x", 0.0)),
                        float(prev_cmd.get("coll_y", 0.0)),
                        float(prev_after.get("spot_center_x", 0.0)),
                        float(prev_after.get("spot_center_y", 0.0)),
                        float(curr_before.get("spot_center_x", 0.0)),
                        float(curr_before.get("spot_center_y", 0.0)),
                    ], dtype=np.float32)

                    # Label: bolt_shift at current step
                    curr_after = curr_step.get("sim_after_bolt") or {}
                    label = np.array([
                        float(curr_after.get("spot_center_x", 0.0))
                        - float(curr_before.get("spot_center_x", 0.0)),
                        float(curr_after.get("spot_center_y", 0.0))
                        - float(curr_before.get("spot_center_y", 0.0)),
                    ], dtype=np.float32)

                    features_seq.append(feat)
                    labels_seq.append(label)

                except (KeyError, TypeError, ValueError) as e:
                    logger.debug(f"Skipping step {i} in trial {trial_id}: {e}")
                    continue

            if len(features_seq) >= 1:
                sequences.append((
                    np.array(features_seq, dtype=np.float32),
                    np.array(labels_seq, dtype=np.float32),
                ))

    logger.info(f"Collected {len(sequences)} trial sequences for LSTM training")
    return sequences


def normalize_features(features: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Normalize features using mean and std.
    
    Note: Zero-padded slots will have low variance; normalization handles this
    via the +1e-8 epsilon.
    
    Args:
        features: (N, D) array
        
    Returns:
        normalized_features: (N, D) array
        stats: dict with 'mean' (D,) and 'std' (D,)
    """
    mean = features.mean(axis=0)
    std = features.std(axis=0) + 1e-8  # avoid division by zero
    
    normalized = (features - mean) / std
    
    return normalized, {"mean": mean, "std": std}

