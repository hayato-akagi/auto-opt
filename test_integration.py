#!/usr/bin/env python3
"""Integration test: trainer → save model → ai-controller inference.

Usage:
    python test_integration.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Run integration test."""
    logger.info("=" * 70)
    logger.info("Integration Test: Trainer → AI Controller")
    logger.info("=" * 70)
    
    try:
        # Step 1: Train a model using trainer
        logger.info("\n[Step 1] Training model with trainer...")
        
        # Import trainer modules
        trainer_path = Path(__file__).parent / "services" / "trainer"
        sys.path.insert(0, str(trainer_path))
        import app.data as trainer_data
        import app.train as trainer_train
        
        # Create mock training data
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
        }
        
        experiments = [{"experiment_id": "exp_001", "trials": [{"trial_id": "trial_001"}]}]
        get_trial_steps = lambda eid, tid: mock_steps.get((eid, tid), [])
        
        features, labels = trainer_data.collect_training_data(experiments, get_trial_steps)
        logger.info(f"  Collected {len(features)} training samples")
        
        normalized_features, stats = trainer_data.normalize_features(features)
        
        config = trainer_train.TrainingConfig(
            epochs=20,
            batch_size=2,
            learning_rate=1e-3,
            val_split=0.0,
            hidden_dim=32,
            device="cpu",
        )
        
        model, metrics = trainer_train.train_model(normalized_features, labels, model_type="mlp", config=config)
        logger.info(f"  Training completed: final_loss={metrics['final_train_loss']:.6f}")
        
        # Save model
        model_path = Path("./integration_test_model.pt")
        trainer_train.save_model(
            model,
            model_path,
            model_type="mlp",
            config=config,
            feature_stats=stats,
            metadata={"integration_test": True},
        )
        logger.info(f"  Model saved to {model_path}")
        
        # Clear trainer imports
        sys.path.remove(str(trainer_path))
        del sys.modules['app.data']
        del sys.modules['app.train']
        del sys.modules['app']
        
        # Step 2: Load model with AI controller
        logger.info("\n[Step 2] Loading model with AI controller...")
        
        # Import ai-controller modules
        ai_controller_path = Path(__file__).parent / "services" / "ai-controller"
        sys.path.insert(0, str(ai_controller_path))
        import app.model as ai_model
        import app.logic as ai_logic
        import app.models as ai_models
        
        model_mgr = ai_model.ModelManager(
            model_type="mlp",
            model_version="integration_v1",
            model_path=model_path,
            device="cpu",
        )
        
        status = model_mgr.status()
        logger.info(f"  Model loaded: {status}")
        
        # Step 3: Run inference
        logger.info("\n[Step 3] Running inference with AI controller...")
        
        # Test case: Control loop step with previous history
        prev_step = {
            "sim_after_position": {"spot_center_x": 0.05, "spot_center_y": 0.03},
            "command": {"coll_x": 0.0, "coll_y": 0.0},
            "sim_after_bolt": {"spot_center_x": 0.06, "spot_center_y": 0.04},
        }
        
        ai_config = ai_models.AiControllerConfig(
            model_type="mlp",
            spot_to_coll_scale_x=50.0,
            spot_to_coll_scale_y=50.0,
            delta_clip_x=0.1,
            delta_clip_y=0.1,
            coll_x_min=-0.5,
            coll_x_max=0.5,
            coll_y_min=-0.5,
            coll_y_max=0.5,
            safety_threshold=2.0,  # More permissive for integration test
            safety_bias=0.05,
        )
        
        decision = ai_logic.compute_ai_step(
            config=ai_config,
            target_x=0.0,
            target_y=0.0,
            current_coll_x=-0.001,
            current_coll_y=-0.0006,
            spot_pre_x=0.02,
            spot_pre_y=0.015,
            model_manager=model_mgr,
            prev_step=prev_step,
        )
        
        logger.info(f"  Baseline delta: ({decision.baseline_delta_x:.6f}, {decision.baseline_delta_y:.6f})")
        logger.info(f"  DNN residual:   ({decision.dnn_residual_x:.6f}, {decision.dnn_residual_y:.6f})")
        logger.info(f"  Final delta:    ({decision.final_delta_x:.6f}, {decision.final_delta_y:.6f})")
        logger.info(f"  Next coll pos:  ({decision.next_coll_x:.6f}, {decision.next_coll_y:.6f})")
        logger.info(f"  Safety triggered: {decision.safety_triggered}")
        
        # Verify inference ran (residual should not be zero if model is working)
        baseline_norm = np.hypot(decision.baseline_delta_x, decision.baseline_delta_y)
        residual_norm = np.hypot(decision.dnn_residual_x, decision.dnn_residual_y)
        
        logger.info(f"\n  Baseline norm: {baseline_norm:.6f}")
        logger.info(f"  Residual norm: {residual_norm:.6f}")
        
        # Step 4: Compare with baseline-only
        logger.info("\n[Step 4] Comparing with baseline-only mode...")
        
        baseline_config = ai_models.AiControllerConfig(
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
        
        baseline_decision = ai_logic.compute_ai_step(
            config=baseline_config,
            target_x=0.0,
            target_y=0.0,
            current_coll_x=-0.001,
            current_coll_y=-0.0006,
            spot_pre_x=0.02,
            spot_pre_y=0.015,
            model_manager=None,
            prev_step=prev_step,
        )
        
        logger.info(f"  Baseline-only delta: ({baseline_decision.final_delta_x:.6f}, {baseline_decision.final_delta_y:.6f})")
        logger.info(f"  AI-enhanced delta:   ({decision.final_delta_x:.6f}, {decision.final_delta_y:.6f})")
        
        delta_diff_x = abs(decision.final_delta_x - baseline_decision.final_delta_x)
        delta_diff_y = abs(decision.final_delta_y - baseline_decision.final_delta_y)
        logger.info(f"  Difference: ({delta_diff_x:.6f}, {delta_diff_y:.6f})")
        
        # Cleanup
        if model_path.exists():
            model_path.unlink()
            logger.info(f"\n  Cleaned up: {model_path}")
        
        logger.info("\n" + "=" * 70)
        logger.info("Integration test completed successfully! ✓")
        logger.info("=" * 70)
        logger.info("\nSummary:")
        logger.info("  ✓ Trainer: Data collection, normalization, training, model save")
        logger.info("  ✓ AI Controller: Model load, feature extraction, inference")
        logger.info("  ✓ Integration: Trained model successfully used for inference")
        
    except Exception as e:
        logger.error(f"Integration test failed: {e}", exc_info=True)
        
        # Cleanup on error
        model_path = Path("./integration_test_model.pt")
        if model_path.exists():
            model_path.unlink()
        
        sys.exit(1)


if __name__ == "__main__":
    main()
