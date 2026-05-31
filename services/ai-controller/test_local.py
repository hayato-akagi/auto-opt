#!/usr/bin/env python3
"""Local test script for ai-controller - independent of other services.

Usage:
    python test_local.py [path_to_model.pt]
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.model import ModelManager
from app.logic import compute_ai_step, extract_features_for_inference
from app.models import AiControllerConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_dummy_model() -> Path:
    """Create a dummy trained model for testing."""
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        logger.error("PyTorch not available")
        sys.exit(1)
    
    # Create simple MLP
    class DummyMLP(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(8, 16),
                nn.ReLU(),
                nn.Linear(16, 16),
                nn.ReLU(),
                nn.Linear(16, 2),
            )
        
        def forward(self, x):
            return self.net(x)
    
    model = DummyMLP()
    
    # Save model
    save_path = Path("./test_ai_model.pt")
    torch.save({
        "model_state_dict": model.state_dict(),
        "model_type": "mlp",
        "hidden_dim": 16,
        "feature_mean": np.zeros(8, dtype=np.float32),
        "feature_std": np.ones(8, dtype=np.float32),
        "metadata": {"test": True},
    }, save_path)
    
    logger.info(f"Dummy model created at {save_path}")
    return save_path


def test_model_loading(model_path: Path):
    """Test model loading."""
    logger.info("=" * 60)
    logger.info("Test 1: Model Loading")
    logger.info("=" * 60)
    
    model_mgr = ModelManager(
        model_type="mlp",
        model_version="test_v1",
        model_path=model_path,
        device="cpu",
    )
    
    status = model_mgr.status()
    logger.info(f"Status: {status}")
    
    assert status["model_loaded"] is True
    assert status["model_type"] == "mlp"
    
    logger.info("✓ Model loading test passed\n")
    return model_mgr


def test_feature_extraction():
    """Test feature extraction."""
    logger.info("=" * 60)
    logger.info("Test 2: Feature Extraction")
    logger.info("=" * 60)
    
    # Test with no previous step (step_index=0)
    features_no_prev = extract_features_for_inference(
        prev_step=None,
        current_spot_x=0.05,
        current_spot_y=0.03,
    )
    
    logger.info(f"Features (no prev): shape={features_no_prev.shape}")
    logger.info(f"  Values: {features_no_prev}")
    
    assert features_no_prev.shape == (8,)
    assert features_no_prev[6] == 0.05  # current_spot_x
    assert features_no_prev[7] == 0.03  # current_spot_y
    
    # Test with previous step
    prev_step = {
        "sim_after_position": {"spot_center_x": 0.06, "spot_center_y": 0.04},
        "command": {"coll_x": -0.001, "coll_y": -0.0008},
        "sim_after_bolt": {"spot_center_x": 0.065, "spot_center_y": 0.045},
    }
    
    features_with_prev = extract_features_for_inference(
        prev_step=prev_step,
        current_spot_x=0.02,
        current_spot_y=0.015,
    )
    
    logger.info(f"Features (with prev): shape={features_with_prev.shape}")
    logger.info(f"  Values: {features_with_prev}")
    
    assert features_with_prev.shape == (8,)
    assert features_with_prev[0] == 0.06  # prev_spot_x_before
    assert features_with_prev[2] == -0.001  # prev_coll_x
    assert features_with_prev[6] == 0.02  # current_spot_x
    
    logger.info("✓ Feature extraction test passed\n")


def test_model_inference(model_mgr: ModelManager):
    """Test model inference."""
    logger.info("=" * 60)
    logger.info("Test 3: Model Inference")
    logger.info("=" * 60)
    
    # Create test features
    features = np.array([
        [0.05, 0.03, 0.0, 0.0, 0.06, 0.04, 0.02, 0.015],
        [0.02, 0.015, -0.001, -0.0008, 0.025, 0.018, 0.005, 0.003],
    ], dtype=np.float32)
    
    predictions = model_mgr.predict(features)
    
    logger.info(f"Predictions shape: {predictions.shape}")
    logger.info(f"Predictions:\n{predictions}")
    
    assert predictions.shape == (2, 2)
    
    logger.info("✓ Model inference test passed\n")


def test_ai_step_computation(model_mgr: ModelManager):
    """Test AI step computation with baseline + model."""
    logger.info("=" * 60)
    logger.info("Test 4: AI Step Computation")
    logger.info("=" * 60)
    
    config = AiControllerConfig(
        model_type="mlp",
        spot_to_coll_scale_x=50.0,
        spot_to_coll_scale_y=50.0,
        delta_clip_x=0.1,
        delta_clip_y=0.1,
        coll_x_min=-0.5,
        coll_x_max=0.5,
        coll_y_min=-0.5,
        coll_y_max=0.5,
        safety_threshold=0.5,
        safety_bias=0.01,
    )
    
    # Test case 1: No previous step
    decision1 = compute_ai_step(
        config=config,
        target_x=0.0,
        target_y=0.0,
        current_coll_x=0.0,
        current_coll_y=0.0,
        spot_pre_x=0.05,
        spot_pre_y=0.03,
        model_manager=model_mgr,
        prev_step=None,
    )
    
    logger.info("Decision 1 (no prev step):")
    logger.info(f"  Baseline: ({decision1.baseline_delta_x:.6f}, {decision1.baseline_delta_y:.6f})")
    logger.info(f"  Residual: ({decision1.dnn_residual_x:.6f}, {decision1.dnn_residual_y:.6f})")
    logger.info(f"  Final: ({decision1.final_delta_x:.6f}, {decision1.final_delta_y:.6f})")
    logger.info(f"  Next coll: ({decision1.next_coll_x:.6f}, {decision1.next_coll_y:.6f})")
    logger.info(f"  Safety triggered: {decision1.safety_triggered}")
    
    # Test case 2: With previous step
    prev_step = {
        "sim_after_position": {"spot_center_x": 0.08, "spot_center_y": 0.06},
        "command": {"coll_x": 0.0, "coll_y": 0.0},
        "sim_after_bolt": {"spot_center_x": 0.09, "spot_center_y": 0.065},
    }
    
    decision2 = compute_ai_step(
        config=config,
        target_x=0.0,
        target_y=0.0,
        current_coll_x=-0.0016,
        current_coll_y=-0.0012,
        spot_pre_x=0.05,
        spot_pre_y=0.03,
        model_manager=model_mgr,
        prev_step=prev_step,
    )
    
    logger.info("\nDecision 2 (with prev step):")
    logger.info(f"  Baseline: ({decision2.baseline_delta_x:.6f}, {decision2.baseline_delta_y:.6f})")
    logger.info(f"  Residual: ({decision2.dnn_residual_x:.6f}, {decision2.dnn_residual_y:.6f})")
    logger.info(f"  Final: ({decision2.final_delta_x:.6f}, {decision2.final_delta_y:.6f})")
    logger.info(f"  Next coll: ({decision2.next_coll_x:.6f}, {decision2.next_coll_y:.6f})")
    logger.info(f"  Safety triggered: {decision2.safety_triggered}")
    
    # Test case 3: Baseline-only mode
    config_baseline = AiControllerConfig(
        model_type="baseline_only",
        spot_to_coll_scale_x=50.0,
        spot_to_coll_scale_y=50.0,
        delta_clip_x=0.1,
        delta_clip_y=0.1,
        coll_x_min=-0.5,
        coll_x_max=0.5,
        coll_y_min=-0.5,
        coll_y_max=0.5,
    )
    
    decision3 = compute_ai_step(
        config=config_baseline,
        target_x=0.0,
        target_y=0.0,
        current_coll_x=0.0,
        current_coll_y=0.0,
        spot_pre_x=0.05,
        spot_pre_y=0.03,
        model_manager=model_mgr,
        prev_step=None,
    )
    
    logger.info("\nDecision 3 (baseline-only):")
    logger.info(f"  Baseline: ({decision3.baseline_delta_x:.6f}, {decision3.baseline_delta_y:.6f})")
    logger.info(f"  Residual: ({decision3.dnn_residual_x:.6f}, {decision3.dnn_residual_y:.6f})")
    logger.info(f"  Final: ({decision3.final_delta_x:.6f}, {decision3.final_delta_y:.6f})")
    
    assert decision3.dnn_residual_x == 0.0
    assert decision3.dnn_residual_y == 0.0
    
    logger.info("✓ AI step computation test passed\n")


def main():
    """Run all tests."""
    try:
        # Check if model path provided
        if len(sys.argv) > 1:
            model_path = Path(sys.argv[1])
            if not model_path.exists():
                logger.error(f"Model file not found: {model_path}")
                sys.exit(1)
        else:
            # Create dummy model
            model_path = create_dummy_model()
        
        # Test 1: Model loading
        model_mgr = test_model_loading(model_path)
        
        # Test 2: Feature extraction
        test_feature_extraction()
        
        # Test 3: Model inference
        test_model_inference(model_mgr)
        
        # Test 4: AI step computation
        test_ai_step_computation(model_mgr)
        
        # Cleanup if we created a dummy model
        if len(sys.argv) <= 1 and model_path.exists():
            model_path.unlink()
            logger.info(f"Cleaned up dummy model: {model_path}")
        
        logger.info("=" * 60)
        logger.info("All tests passed! ✓")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
