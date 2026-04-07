# データ保存形式

## ディレクトリ構成

```
data/
└── experiments/
    └── {experiment_id}/
        ├── experiment.json
        ├── {trial_id}/
        │   ├── trial_meta.json
        │   ├── step_000.json
        │   ├── step_001.json
        │   ├── ...
        │   └── summary.json
        └── {trial_id}/
            └── ...
```

## experiment.json

系の定義。全試行で不変。

```jsonc
{
  "experiment_id": "exp_001",
  "name": "baseline_780nm",
  "created_at": "2026-03-27T10:00:00Z",
  "optical_system": {
    "wavelength": 780, "ld_tilt": 0,
    "ld_div_fast": 25, "ld_div_slow": 8,
    "ld_div_fast_err": 0, "ld_div_slow_err": 0,
    "ld_emit_w": 3.0, "ld_emit_h": 1.0, "num_rays": 500,
    "coll_r1": -3.5, "coll_r2": -15.0,
    "coll_k1": -1.0, "coll_k2": 0,
    "coll_t": 2.0, "coll_n": 1.517, "dist_ld_coll": 4.0,
    "obj_f": 4.0, "dist_coll_obj": 50.0, "sensor_pos": 4.0
  },
  "bolt_model": {
    "upper": {
      "shift_x_per_nm": 0.001, "shift_y_per_nm": 0.003,
      "noise_std_x": 0.002, "noise_std_y": 0.005
    },
    "lower": {
      "shift_x_per_nm": -0.0005, "shift_y_per_nm": 0.002,
      "noise_std_x": 0.001, "noise_std_y": 0.003
    }
  }
}
```

## trial_meta.json

試行ごとの設定。

### manual モード

```jsonc
{
  "trial_id": "trial_001",
  "experiment_id": "exp_001",
  "started_at": "2026-03-27T10:05:00Z",
  "mode": "manual",
  "control": null
}
```

### control_loop モード

```jsonc
{
  "trial_id": "trial_002",
  "experiment_id": "exp_001",
  "started_at": "2026-03-27T11:00:00Z",
  "mode": "control_loop",
  "control": {
    "algorithm": "pid",
    "config": {
      "kp_x": 0.8, "ki_x": 0.1, "kd_x": 0.05,
      "kp_y": 0.8, "ki_y": 0.1, "kd_y": 0.05
    },
    "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
    "max_iterations": 20,
    "tolerance": 0.001
  }
}
```

## step_NNN.json

各ステップの全記録。

```jsonc
{
  "step_index": 0,
  "timestamp": "2026-03-27T10:05:01Z",

  "command": {
    "coll_x": 0.02,
    "coll_y": -0.05,
    "torque_upper": 0.5,
    "torque_lower": 0.5
  },

  "after_position": {
    "coll_x_shift": 0.02,
    "coll_y_shift": -0.05
  },
  "sim_after_position": {
    "spot_center_x": 0.005,
    "spot_center_y": -0.038,
    "spot_rms_radius": 0.006,
    "spot_geo_radius": 0.014,
    "spot_peak_x": 0.004,
    "spot_peak_y": -0.037,
    "num_rays_launched": 500,
    "num_rays_arrived": 487,
    "vignetting_ratio": 0.026,
    "ray_hits": null,
    "computation_time_ms": 115
  },

  "bolt_shift": {
    "delta_x": 0.003,
    "delta_y": 0.008,
    "used_seed": 1234567890,
    "detail": {
      "upper": {"delta_x": 0.0015, "delta_y": 0.0055},
      "lower": {"delta_x": 0.0015, "delta_y": 0.0025}
    }
  },
  "after_bolt": {
    "coll_x_shift": 0.023,
    "coll_y_shift": -0.042
  },
  "sim_after_bolt": {
    "spot_center_x": 0.012,
    "spot_center_y": -0.042,
    "spot_rms_radius": 0.005,
    "spot_geo_radius": 0.012,
    "spot_peak_x": 0.011,
    "spot_peak_y": -0.041,
    "num_rays_launched": 500,
    "num_rays_arrived": 487,
    "vignetting_ratio": 0.026,
    "ray_hits": null,
    "computation_time_ms": 118
  }
}
```

## summary.json

試行完了時に生成。

```jsonc
{
  "trial_id": "trial_001",
  "experiment_id": "exp_001",
  "mode": "manual",
  "total_steps": 5,
  "converged": null,
  "final_step": {
    "spot_center_x": 0.001,
    "spot_center_y": -0.002,
    "spot_rms_radius": 0.004
  },
  "finished_at": "2026-03-27T10:10:00Z"
}
```

## 設計方針

- **JSON のみ** で永続化（DBなし）
- 実験を変えたら別ディレクトリ（系の変更 = 別実験）
- 同一実験内で試行を繰り返す（制御器の調整、手動試行）
- `ray_hits` はオプション（保存サイズ節約）
- **画像（base64 PNG）はステップJSONに含めない**
  - Optics Sim API は要求時に画像を返すが、Recipe Service は保存時に除外する
  - Streamlit が画像を表示したい場合は、保存済みパラメータで Optics Sim を再呼出しして取得する
  - これにより保存データを軽量に保つ
