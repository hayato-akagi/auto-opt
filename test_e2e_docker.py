#!/usr/bin/env python3
"""E2E test in Docker environment: create experiments, collect data, train, and run AI controller.

Usage:
    python test_e2e_docker.py
"""

import json
import logging
import sys
import time
import urllib.request as u
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def http_post(url: str, data: dict[str, Any]) -> dict[str, Any]:
    """POST request helper."""
    req = u.Request(
        url,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with u.urlopen(req) as response:
        return json.loads(response.read())


def http_get(url: str) -> dict[str, Any]:
    """GET request helper."""
    with u.urlopen(url) as response:
        return json.loads(response.read())


def create_experiment() -> str:
    """Create a test experiment."""
    logger.info("Step 1: Creating experiment...")
    
    payload = {
        "name": "e2e_test_experiment",
        "engine_type": "Simple",
        "optical_system": {
            "wavelength": 780.0,
            "ld_tilt": 0.0,
            "ld_div_fast": 25.0,
            "ld_div_slow": 8.0,
            "ld_div_fast_err": 0.0,
            "ld_div_slow_err": 0.0,
            "ld_emit_w": 3.0,
            "ld_emit_h": 1.0,
            "num_rays": 5000,
            "coll_r1": -3.5,
            "coll_r2": -15.0,
            "coll_k1": -1.0,
            "coll_k2": 0.0,
            "coll_t": 2.0,
            "coll_n": 1.517,
            "dist_ld_coll": 4.0,
            "obj_f": 4.0,
            "dist_coll_obj": 50.0,
            "sensor_pos": 4.0,
        },
        "bolt_model": {
            "upper": {
                "x0_bias_x": 0.05,
                "x0_bias_y": 0.0,
                "a_x": 0.02,
                "b_x": 1.0,
                "a_y": 0.02,
                "b_y": 1.0,
                "noise_ratio_min_x": 0.01,
                "noise_ratio_max_x": 0.05,
                "noise_ratio_min_y": 0.01,
                "noise_ratio_max_y": 0.05,
            },
            "lower": {
                "x0_bias_x": 0.0,
                "x0_bias_y": 0.0,
                "a_x": 0.0,
                "b_x": 1.0,
                "a_y": 0.0,
                "b_y": 1.0,
                "noise_ratio_min_x": 0.01,
                "noise_ratio_max_x": 0.05,
                "noise_ratio_min_y": 0.01,
                "noise_ratio_max_y": 0.05,
            },
        },
    }
    
    result = http_post("http://localhost:9002/experiments", payload)
    experiment_id = result["experiment_id"]
    logger.info(f"  Created experiment: {experiment_id}")
    return experiment_id


def collect_training_data(experiment_id: str, n_trials: int = 3) -> None:
    """Run simple-controller to collect training data."""
    logger.info(f"Step 2: Collecting training data ({n_trials} trials)...")
    
    for i in range(n_trials):
        payload = {
            "experiment_id": experiment_id,
            "algorithm": "simple-controller",
            "config": {
                "spot_to_coll_scale_x": 50.0,
                "spot_to_coll_scale_y": 50.0,
                "delta_clip_x": 0.1,
                "delta_clip_y": 0.1,
                "coll_x_min": -0.5,
                "coll_x_max": 0.5,
                "coll_y_min": -0.5,
                "coll_y_max": 0.5,
                "release_perturbation": {"std_x": 0.0, "std_y": 0.0},
            },
            "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
            "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
            "max_steps": 5,
            "tolerance": 0.05,
            "random_seed": 100 + i,
        }
        
        result = http_post("http://localhost:9003/control/run", payload)
        logger.info(f"  Trial {i+1}: {result['trial_id']}, converged={result['converged']}, steps={result['steps']}")


def train_model(experiment_id: str) -> str:
    """Train model using trainer service."""
    logger.info("Step 3: Training model...")
    
    payload = {
        "experiment_ids": [experiment_id],
        "model_type": "mlp",
        "epochs": 20,
        "batch_size": 8,
    }
    
    result = http_post("http://localhost:9008/train", payload)
    train_job_id = result["train_job_id"]
    logger.info(f"  Training job started: {train_job_id}")
    
    # Poll for completion
    max_wait = 120  # 2 minutes
    start_time = time.time()
    while time.time() - start_time < max_wait:
        status = http_get(f"http://localhost:9008/train/{train_job_id}")
        
        if status["status"] == "completed":
            logger.info(f"  Training completed!")
            logger.info(f"    Samples: {status.get('data_stats', {}).get('total_samples', 'unknown')}")
            if status.get("train_metrics"):
                logger.info(f"    Final loss: {status['train_metrics']['final_train_loss']:.6f}")
            return train_job_id
        elif status["status"] == "failed":
            logger.error(f"  Training failed: {status.get('error_message')}")
            raise RuntimeError(f"Training failed: {status.get('error_message')}")
        
        logger.info(f"  Status: {status['status']}, progress: {status.get('progress_rate', 0)*100:.0f}%")
        time.sleep(3)
    
    raise TimeoutError("Training timeout")


def test_ai_controller(experiment_id: str, train_job_id: str) -> None:
    """Test AI controller with trained model."""
    logger.info("Step 4: Testing AI controller...")
    
    payload = {
        "experiment_id": experiment_id,
        "algorithm": "ai-controller",
        "config": {
            "model_type": "mlp",
            "model_path": f"/app/models/{train_job_id}.pt",
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.1,
            "delta_clip_y": 0.1,
            "coll_x_min": -0.5,
            "coll_x_max": 0.5,
            "coll_y_min": -0.5,
            "coll_y_max": 0.5,
            "safety_threshold": 2.0,
            "safety_bias": 0.05,
            "release_perturbation": {"std_x": 0.0, "std_y": 0.0},
        },
        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
        "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
        "max_steps": 5,
        "tolerance": 0.05,
        "random_seed": 999,
    }
    
    result = http_post("http://localhost:9006/control/run", payload)
    logger.info(f"  AI controller result:")
    logger.info(f"    Trial: {result['trial_id']}")
    logger.info(f"    Converged: {result['converged']}")
    logger.info(f"    Steps: {result['steps']}")
    logger.info(f"    Final distance: {result['final_distance']:.6f} mm")
    logger.info(f"    Model: {result.get('model_type')} / {result.get('model_version')}")


def main():
    """Run E2E test."""
    logger.info("=" * 70)
    logger.info("E2E Test: Docker Environment")
    logger.info("=" * 70)
    
    try:
        # Step 1: Create experiment
        experiment_id = create_experiment()
        
        # Step 2: Collect training data
        collect_training_data(experiment_id, n_trials=3)
        
        # Step 3: Train model
        train_job_id = train_model(experiment_id)
        
        # Step 4: Test AI controller
        test_ai_controller(experiment_id, train_job_id)
        
        logger.info("\n" + "=" * 70)
        logger.info("E2E Test PASSED! ✓")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"E2E Test FAILED: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
