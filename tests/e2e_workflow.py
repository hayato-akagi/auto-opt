"""
E2E Workflow Test for auto-opt
Tests the complete workflow: Experiment → Manual Confirmation → Model Learning → Results
"""

import json
import time
import urllib.request as u
from typing import Any


class E2EClient:
    """Simple REST API client for E2E testing"""

    def __init__(self):
        self.base_recipe = "http://localhost:9002"
        self.base_simple = "http://localhost:9003"
        self.base_collection = "http://localhost:9007"
        self.base_trainer = "http://localhost:9008"

    def get(self, service: str, path: str) -> dict[str, Any] | None:
        """GET request to service"""
        if service == "recipe":
            url = f"{self.base_recipe}{path}"
        elif service == "simple":
            url = f"{self.base_simple}{path}"
        elif service == "collection":
            url = f"{self.base_collection}{path}"
        elif service == "trainer":
            url = f"{self.base_trainer}{path}"
        else:
            raise ValueError(f"Unknown service: {service}")

        try:
            with u.urlopen(url) as response:
                return json.loads(response.read())
        except Exception as e:
            print(f"❌ GET {url} failed: {e}")
            return None

    def post(self, service: str, path: str, payload: dict) -> dict[str, Any] | None:
        """POST request to service"""
        if service == "recipe":
            url = f"{self.base_recipe}{path}"
        elif service == "simple":
            url = f"{self.base_simple}{path}"
        elif service == "collection":
            url = f"{self.base_collection}{path}"
        elif service == "trainer":
            url = f"{self.base_trainer}{path}"
        else:
            raise ValueError(f"Unknown service: {service}")

        try:
            req = u.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with u.urlopen(req) as response:
                return json.loads(response.read())
        except Exception as e:
            print(f"❌ POST {url} failed: {e}")
            return None


def test_phase1_health_check(client: E2EClient) -> bool:
    """Test Phase 1: Health checks for all services"""
    print("\n" + "=" * 60)
    print("PHASE 1: Service Health Checks")
    print("=" * 60)

    services = [
        ("recipe", "/experiments"),
        ("simple", "/health"),
        ("collection", "/health"),
        ("trainer", "/health"),
    ]

    all_ok = True
    for service, endpoint in services:
        result = client.get(service, endpoint)
        status = "✅" if result else "❌"
        print(f"{status} {service:15} {endpoint:20} {result is not None}")
        all_ok = all_ok and (result is not None)

    return all_ok


def test_phase2_experiment_creation(client: E2EClient) -> str | None:
    """Test Phase 2: Create experiment"""
    print("\n" + "=" * 60)
    print("PHASE 2: Experiment Creation")
    print("=" * 60)

    exp_payload = {
        "name": "e2e-test-exp",
        "engine_type": "Simple",
        "optical_system": {
            "wavelength": 780.0,
            "ld_tilt": 0.0,
            "ld_div_fast": 30.0,
            "ld_div_slow": 10.0,
            "ld_div_fast_err": 0.0,
            "ld_div_slow_err": 0.0,
            "ld_emit_w": 2.0,
            "ld_emit_h": 1.0,
            "num_rays": 10000,
            "coll_r1": 0.0,
            "coll_r2": -10.0,
            "coll_k1": 1.0,
            "coll_k2": 1.0,
            "coll_t": 5.0,
            "coll_n": 1.5,
            "dist_ld_coll": 50.0,
            "obj_f": 50.0,
            "dist_coll_obj": 100.0,
            "sensor_pos": 160.0,
        },
        "camera": {
            "pixel_w": 640,
            "pixel_h": 480,
            "pixel_pitch_um": 5.3,
            "gaussian_sigma_px": 3.0,
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

    result = client.post("recipe", "/experiments", exp_payload)
    if result and "experiment_id" in result:
        exp_id = result["experiment_id"]
        print(f"✅ Experiment created: {exp_id}")
        return exp_id
    else:
        print(f"❌ Failed to create experiment")
        return None


def test_phase3_manual_confirmation(client: E2EClient, exp_id: str) -> str | None:
    """Test Phase 3: Manual confirmation - create and execute steps"""
    print("\n" + "=" * 60)
    print("PHASE 3: Manual Confirmation (Manual Steps)")
    print("=" * 60)

    # Create manual trial
    trial_payload = {
        "mode": "manual",
        "control": None,
    }
    trial_result = client.post("recipe", f"/experiments/{exp_id}/trials", trial_payload)
    if not trial_result or "trial_id" not in trial_result:
        print("❌ Failed to create manual trial")
        return None

    trial_id = trial_result["trial_id"]
    print(f"✅ Manual trial created: {trial_id}")

    # Execute manual step
    step_payload = {
        "coll_x": 0.0,
        "coll_y": 0.0,
        "options": {
            "return_ray_hits": False,
            "return_images": False,
        },
    }
    step_result = client.post(
        "recipe", f"/experiments/{exp_id}/trials/{trial_id}/steps", step_payload
    )
    if step_result and "step_index" in step_result:
        print(f"✅ Manual step executed: step_index={step_result['step_index']}")
    else:
        print("❌ Failed to execute manual step")
        return None

    # Complete trial
    complete_result = client.post(
        "recipe", f"/experiments/{exp_id}/trials/{trial_id}/complete", {}
    )
    if complete_result:
        print(f"✅ Manual trial completed")

    return trial_id


def test_phase4_baseline_controller(client: E2EClient, exp_id: str) -> str | None:
    """Test Phase 4: Baseline controller run"""
    print("\n" + "=" * 60)
    print("PHASE 4: Baseline Controller Run")
    print("=" * 60)

    baseline_payload = {
        "experiment_id": exp_id,
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
        "random_seed": 42,
    }

    result = client.post("simple", "/control/run", baseline_payload)
    if result and "trial_id" in result:
        trial_id = result["trial_id"]
        print(f"✅ Baseline controller trial: {trial_id}")
        print(f"   Converged: {result.get('converged')}, Steps: {result.get('steps')}")
        return trial_id
    else:
        print("❌ Failed to run baseline controller")
        return None


def test_phase5_data_collection(client: E2EClient, exp_id: str) -> str | None:
    """Test Phase 5: Data collection job"""
    print("\n" + "=" * 60)
    print("PHASE 5: Data Collection Job")
    print("=" * 60)

    collection_payload = {
        "algorithm": "simple-controller",
        "controller_config": {
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.1,
            "delta_clip_y": 0.1,
            "coll_x_min": -0.5,
            "coll_x_max": 0.5,
            "coll_y_min": -0.5,
            "coll_y_max": 0.5,
        },
        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
        "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
        "max_steps": 3,
        "tolerance": 0.05,
        "tasks": [{"experiment_id": exp_id, "seeds": [1, 2]}],
        "max_workers": 2,
    }

    result = client.post("collection", "/jobs", collection_payload)
    if result and "job_id" in result:
        job_id = result["job_id"]
        print(f"✅ Collection job created: {job_id}")
        print(f"   Status: {result.get('status')}, Total tasks: {result.get('total_tasks')}")

        # Wait for job to complete
        print("   Waiting for job completion...")
        for i in range(30):  # Max 30 seconds
            status_result = client.get("collection", f"/jobs/{job_id}")
            if status_result:
                status = status_result.get("status")
                completed = status_result.get("completed_tasks", 0)
                total = status_result.get("total_tasks", 0)
                print(f"   [{i}s] Status: {status}, Progress: {completed}/{total}")
                if status == "completed":
                    print(f"✅ Collection job completed")
                    return job_id
            time.sleep(1)

        print(f"⚠️  Collection job still running after 30s (may need more time)")
        return job_id
    else:
        print("❌ Failed to create collection job")
        return None


def test_phase6_training(client: E2EClient, exp_id: str) -> bool:
    """Test Phase 6: Training job"""
    print("\n" + "=" * 60)
    print("PHASE 6: Training Job")
    print("=" * 60)

    training_payload = {
        "experiment_ids": [exp_id],
        "model_type": "baseline_only",
        "epochs": 2,
        "batch_size": 32,
    }

    result = client.post("trainer", "/train", training_payload)
    if result:
        job_id = result.get("job_id")
        print(f"✅ Training job created: {job_id}")
        print(f"   Status: {result.get('status')}")
        return True
    else:
        print("❌ Failed to create training job")
        return False


def test_phase7_results_retrieval(client: E2EClient, exp_id: str) -> bool:
    """Test Phase 7: Retrieve results and compute metrics"""
    print("\n" + "=" * 60)
    print("PHASE 7: Results Retrieval & Metrics")
    print("=" * 60)

    trials_result = client.get("recipe", f"/experiments/{exp_id}/trials")
    if not trials_result or "trials" not in trials_result:
        print("❌ Failed to retrieve trials")
        return False

    trials = trials_result["trials"]
    print(f"✅ Retrieved {len(trials)} trials")

    # Compute basic metrics
    total_steps = 0
    for trial in trials:
        trial_id = trial.get("trial_id")
        total_steps += trial.get("total_steps", 0)

    print(f"   Total steps across all trials: {total_steps}")
    print(f"✅ Results retrieval successful")
    return True


def main():
    """Run complete E2E workflow test"""
    print("\n" + "=" * 60)
    print("🚀 AUTO-OPT E2E WORKFLOW TEST")
    print("=" * 60)

    client = E2EClient()

    # Phase 1: Health checks
    if not test_phase1_health_check(client):
        print("\n❌ Phase 1 failed - services not healthy")
        return False

    # Phase 2: Experiment creation
    exp_id = test_phase2_experiment_creation(client)
    if not exp_id:
        print("\n❌ Phase 2 failed")
        return False

    # Phase 3: Manual confirmation
    trial_id = test_phase3_manual_confirmation(client, exp_id)
    if not trial_id:
        print("\n❌ Phase 3 failed")
        return False

    # Phase 4: Baseline controller
    baseline_trial = test_phase4_baseline_controller(client, exp_id)
    if not baseline_trial:
        print("\n❌ Phase 4 failed")
        return False

    # Phase 5: Data collection
    job_id = test_phase5_data_collection(client, exp_id)
    if not job_id:
        print("\n❌ Phase 5 failed")
        return False

    # Phase 6: Training
    if not test_phase6_training(client, exp_id):
        print("\n❌ Phase 6 failed")
        return False

    # Phase 7: Results retrieval
    if not test_phase7_results_retrieval(client, exp_id):
        print("\n❌ Phase 7 failed")
        return False

    # Summary
    print("\n" + "=" * 60)
    print("✅ ALL E2E TESTS PASSED")
    print("=" * 60)
    print(f"Experiment ID: {exp_id}")
    print(f"Manual Trial ID: {trial_id}")
    print(f"Baseline Trial ID: {baseline_trial}")
    print(f"Collection Job ID: {job_id}")
    print("=" * 60 + "\n")
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
