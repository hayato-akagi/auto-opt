#!/usr/bin/env python3
"""Local test script for trainer - independent of other services.

Usage:
    python test_local.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.data import collect_training_data, normalize_features
from app.train import TrainingConfig, train_model, save_model, load_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_mock_data() -> tuple[list[dict], callable]:
    """Create mock experiment data for testing.
    
    Returns:
        experiments: List of experiment dicts
        get_trial_steps: Function to get steps for a trial
    """
    # Mock data structure
    mock_steps = {
        ("exp_001", "trial_001"): [
            {
                "step_index": 0,
                "command": {"coll_x": 0.0, "coll_y": 0.0},
                "sim_after_position": {"spot_center_x": 0.05, "spot_center_y": 0.03},
                "sim_after_bolt": {"spot_center_x": 0.06, "spot_center_y": 0.04},
            },
            {
                "step_index": 1,
                "command": {"coll_x": -0.001, "coll_y": -0.0006},
                "sim_after_position": {"spot_center_x": 0.02, "spot_center_y": 0.015},
                "sim_after_bolt": {"spot_center_x": 0.025, "spot_center_y": 0.020},
            },
            {
                "step_index": 2,
                "command": {"coll_x": -0.0005, "coll_y": -0.0004},
                "sim_after_position": {"spot_center_x": 0.005, "spot_center_y": 0.003},
                "sim_after_bolt": {"spot_center_x": 0.008, "spot_center_y": 0.005},
            },
        ],
        ("exp_001", "trial_002"): [
            {
                "step_index": 0,
                "command": {"coll_x": 0.0, "coll_y": 0.0},
                "sim_after_position": {"spot_center_x": -0.04, "spot_center_y": -0.05},
                "sim_after_bolt": {"spot_center_x": -0.035, "spot_center_y": -0.045},
            },
            {
                "step_index": 1,
                "command": {"coll_x": 0.0008, "coll_y": 0.001},
                "sim_after_position": {"spot_center_x": -0.01, "spot_center_y": -0.015},
                "sim_after_bolt": {"spot_center_x": -0.008, "spot_center_y": -0.012},
            },
        ],
    }
    
    experiments = [
        {
            "experiment_id": "exp_001",
            "trials": [
                {"trial_id": "trial_001"},
                {"trial_id": "trial_002"},
            ],
        }
    ]
    
    def get_trial_steps(exp_id: str, trial_id: str) -> list[dict]:
        return mock_steps.get((exp_id, trial_id), [])
    
    return experiments, get_trial_steps


def test_data_collection():
    """Test data collection and feature extraction."""
    logger.info("=" * 60)
    logger.info("Test 1: Data Collection")
    logger.info("=" * 60)
    
    experiments, get_trial_steps = create_mock_data()
    
    features, labels = collect_training_data(experiments, get_trial_steps)
    
    logger.info(f"Features shape: {features.shape}")
    logger.info(f"Labels shape: {labels.shape}")
    logger.info(f"Feature sample:\n{features[0]}")
    logger.info(f"Label sample:\n{labels[0]}")
    
    assert features.shape[1] == 8, "Features should be 8-dimensional"
    assert labels.shape[1] == 2, "Labels should be 2-dimensional"
    assert len(features) == len(labels), "Features and labels should have same length"
    
    # Expected: 2 step pairs from trial_001 + 1 step pair from trial_002 = 3 samples
    assert len(features) == 3, f"Expected 3 samples, got {len(features)}"
    
    logger.info("✓ Data collection test passed\n")
    return features, labels


def test_normalization(features: np.ndarray):
    """Test feature normalization."""
    logger.info("=" * 60)
    logger.info("Test 2: Feature Normalization")
    logger.info("=" * 60)
    
    normalized, stats = normalize_features(features)
    
    logger.info(f"Original mean: {features.mean(axis=0)}")
    logger.info(f"Normalized mean: {normalized.mean(axis=0)}")
    logger.info(f"Stats mean: {stats['mean']}")
    logger.info(f"Stats std: {stats['std']}")
    
    assert normalized.shape == features.shape
    assert "mean" in stats and "std" in stats
    
    # Check that normalized features have ~zero mean
    assert np.allclose(normalized.mean(axis=0), 0.0, atol=1e-6)
    
    logger.info("✓ Normalization test passed\n")
    return normalized, stats


def test_training(features: np.ndarray, labels: np.ndarray):
    """Test model training."""
    logger.info("=" * 60)
    logger.info("Test 3: Model Training")
    logger.info("=" * 60)
    
    config = TrainingConfig(
        epochs=10,
        batch_size=2,
        learning_rate=1e-3,
        val_split=0.0,  # No validation with only 3 samples
        hidden_dim=16,
        device="cpu",
    )
    
    logger.info("Training MLP model...")
    model, metrics = train_model(features, labels, model_type="mlp", config=config)
    
    logger.info(f"Final train loss: {metrics['final_train_loss']:.6f}")
    logger.info(f"Epoch losses: {metrics['epoch_losses'][:3]}... (showing first 3)")
    
    assert model is not None
    assert len(metrics["epoch_losses"]) == config.epochs
    
    logger.info("✓ Training test passed\n")
    return model, metrics, config


def test_model_save_load(model, config: TrainingConfig, stats: dict):
    """Test model save and load."""
    logger.info("=" * 60)
    logger.info("Test 4: Model Save/Load")
    logger.info("=" * 60)
    
    save_path = Path("./test_model.pt")
    
    # Save
    save_model(
        model,
        save_path,
        model_type="mlp",
        config=config,
        feature_stats=stats,
        metadata={"test": True, "version": "0.1.0"},
    )
    
    logger.info(f"Model saved to {save_path}")
    
    # Load
    loaded_model, loaded_metadata = load_model(save_path, device="cpu")
    
    logger.info(f"Model type: {loaded_metadata['model_type']}")
    logger.info(f"Hidden dim: {loaded_metadata['hidden_dim']}")
    logger.info(f"Metadata: {loaded_metadata['metadata']}")
    
    assert loaded_model is not None
    assert loaded_metadata["model_type"] == "mlp"
    assert loaded_metadata["hidden_dim"] == config.hidden_dim
    
    # Test inference
    import torch
    test_input = torch.randn(1, 8)
    with torch.no_grad():
        orig_output = model(test_input)
        loaded_output = loaded_model(test_input)
    
    assert torch.allclose(orig_output, loaded_output, atol=1e-5)
    
    # Cleanup
    save_path.unlink()
    logger.info("✓ Save/Load test passed\n")


def main():
    """Run all tests."""
    try:
        # Test 1: Data collection
        features, labels = test_data_collection()
        
        # Test 2: Normalization
        normalized_features, stats = test_normalization(features)
        
        # Test 3: Training
        model, metrics, config = test_training(normalized_features, labels)
        
        # Test 4: Save/Load
        test_model_save_load(model, config, stats)
        
        logger.info("=" * 60)
        logger.info("All tests passed! ✓")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
