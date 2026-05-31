"""Smoke test for the full pipeline path."""
import json, time, urllib.request

def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                  headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req).read())

def get(url):
    return json.loads(urllib.request.urlopen(url).read())

exp = {
  "name": "ui-smoke", "engine_type": "Simple",
  "optical_system": {"wavelength":780.0,"ld_tilt":0.0,"ld_div_fast":30.0,"ld_div_slow":10.0,
    "ld_div_fast_err":0.0,"ld_div_slow_err":0.0,"ld_emit_w":2.0,"ld_emit_h":1.0,"num_rays":1000,
    "coll_r1":0.0,"coll_r2":-10.0,"coll_k1":1.0,"coll_k2":1.0,"coll_t":5.0,"coll_n":1.5,
    "dist_ld_coll":50.0,"obj_f":50.0,"dist_coll_obj":100.0,"sensor_pos":160.0},
  "camera":{"pixel_w":640,"pixel_h":480,"pixel_pitch_um":5.3,"gaussian_sigma_px":3.0},
  "bolt_model":{
    "upper":{"x0_bias_x":0.05,"x0_bias_y":0.0,"a_x":0.02,"b_x":1.0,"a_y":0.02,"b_y":1.0,
      "noise_ratio_min_x":0.01,"noise_ratio_max_x":0.05,
      "noise_ratio_min_y":0.01,"noise_ratio_max_y":0.05},
    "lower":{"x0_bias_x":0.0,"x0_bias_y":0.0,"a_x":0.0,"b_x":1.0,"a_y":0.0,"b_y":1.0,
      "noise_ratio_min_x":0.01,"noise_ratio_max_x":0.05,
      "noise_ratio_min_y":0.01,"noise_ratio_max_y":0.05}}}

print("Creating experiment...")
resp = post("http://localhost:9002/experiments", exp)
exp_id = resp["experiment_id"]
print("EXP:", exp_id)

pipe = {
  "experiment_id": exp_id,
  "config": {
    "n_parallel_envs": 2, "trials_per_env": 1, "n_generations": 3,
    "max_steps": 5, "tolerance": 0.05,
    "controller_config": {},
    "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
    "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
    "model_config_train": {"n_history": 2, "hidden_dim": 64, "epochs": 3,
                            "batch_size": 8, "learning_rate": 0.001, "only_converged": False,
                            "warm_start": True},
    "stopping": {"target_success_rate": 0.99, "early_stopping_patience": 99},
    "bolt_distribution": {
      "upper": {"x0_bias_x":[0.0,0.1],"x0_bias_y":[0.0,0.0],
                "a_x":[0.01,0.05],"b_x":[0.9,1.1],"a_y":[0.0,0.0],"b_y":[1.0,1.0],
                "noise_ratio_min_x":0.01,"noise_ratio_max_x":0.05,
                "noise_ratio_min_y":0.01,"noise_ratio_max_y":0.05},
      "lower": {"x0_bias_x":[0.0,0.0],"x0_bias_y":[0.0,0.0],
                "a_x":[0.0,0.0],"b_x":[1.0,1.0],"a_y":[0.0,0.0],"b_y":[1.0,1.0],
                "noise_ratio_min_x":0.01,"noise_ratio_max_x":0.05,
                "noise_ratio_min_y":0.01,"noise_ratio_max_y":0.05},
      "seed": 42
    },
    "poll_interval_sec": 1.0, "train_timeout_sec": 180.0
  }
}
print("Starting pipeline...")
resp = post("http://localhost:9007/experiments/pipeline", pipe)
pipeline_id = resp["pipeline_id"]
print("PIPELINE:", pipeline_id)

for i in range(60):
    s = get(f"http://localhost:9007/experiments/pipeline/{pipeline_id}")
    print(f"[{i:02d}] status={s['status']} gen={s.get('current_generation')}/{s.get('total_generations')} progress={s.get('progress'):.2f}")
    for g in s.get("generations", []):
        print(f"   gen{g['gen_id']} {g['status']} ctrl={g['controller']} sr={g.get('success_rate')} loss={g.get('final_train_loss')} err={g.get('error')}")
        steps = g.get("steps_per_trial") or []
        dists = g.get("final_distances") or []
        losses = g.get("epoch_losses") or []
        if steps or dists or losses:
            print(f"     metrics: steps={steps[:5]}... ({len(steps)}) dists_n={len(dists)} epoch_losses_n={len(losses)}")
    if s["status"] in ("completed", "failed"):
        print("DONE:", s.get("error") or "ok")
        break
    time.sleep(3)
