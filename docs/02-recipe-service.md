# Recipe Service 仕様

- **Port**: 8002
- **役割**: オーケストレーター。実験・試行の管理、サービス間の呼び出し順序制御、データ保存。
- **依存**: optics-sim, position-service, bolt-service

## API

### `POST /experiments`

実験（系）を新規作成。

#### Request Body

```jsonc
{
  "name": "baseline_780nm",
  "engine_type": "KrakenOS",     // "KrakenOS" | "Simple", デフォルト "KrakenOS"
  "optical_system": {
    "wavelength": 780, "ld_tilt": 0, "ld_div_fast": 25, "ld_div_slow": 8,
    "ld_div_fast_err": 0, "ld_div_slow_err": 0,
    "ld_emit_w": 3.0, "ld_emit_h": 1.0, "num_rays": 500,
    "coll_r1": -3.5, "coll_r2": -15.0, "coll_k1": -1.0, "coll_k2": 0,
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
  },
  "camera": {                     // オプション、null の場合は各エンジンのデフォルト設定を使用
    "pixel_w": 640,
    "pixel_h": 480,
    "pixel_pitch_um": 5.3,        // KrakenOS版では未使用
    "gaussian_sigma_px": 3.0,     // KrakenOS版では未使用
    "fov_width_mm": 1.0,          // Simple版で使用
    "fov_height_mm": 1.0          // Simple版で使用
  }
}
```

#### Response (201)

```jsonc
{
  "experiment_id": "exp_001",
  "name": "baseline_780nm",
  "created_at": "2026-03-27T10:00:00Z"
}
```

> **ID採番**: 実験ID (`exp_001`, `exp_002`, ...) および試行ID (`trial_001`, `trial_002`, ...) は自動連番。ユーザー指定不可（衝突防止）。

### `GET /experiments`

実験一覧。

#### Response (200)

```jsonc
{
  "experiments": [
    {"experiment_id": "exp_001", "name": "baseline_780nm", "created_at": "2026-03-27T10:00:00Z"},
    {"experiment_id": "exp_002", "name": "high_na_lens", "created_at": "2026-03-27T14:00:00Z"}
  ]
}
```

### `GET /experiments/{experiment_id}`

実験詳細（experiment.json の内容）。

### `POST /experiments/{experiment_id}/trials`

試行を開始。

#### Request Body

```jsonc
{
  "mode": "manual",                   // "manual" | "control_loop"
  "control": null                      // control_loop時のみ設定
}
```

#### Response (201)

```jsonc
{
  "trial_id": "trial_001",
  "experiment_id": "exp_001",
  "mode": "manual",
  "started_at": "2026-03-27T10:05:00Z"
}
```

### `POST /experiments/{experiment_id}/trials/{trial_id}/steps`

1ステップを実行。Position → Sim → Bolt → Sim の全フローを実行し、結果を保存して返す。

> **Sim レスポンスの透過**: `sim_after_position` / `sim_after_bolt` は Optics Sim のレスポンスをそのまま含む（`spot_center_x/y`, `spot_rms_radius`, `spot_geo_radius`, `spot_peak_x/y`, `num_rays_launched`, `num_rays_arrived`, `vignetting_ratio`, `computation_time_ms`）。
> Recipe Service が独自にフィールドを加工・選択することはない。

> **命令値と実効値の区別**:
> - リクエストの `coll_x`, `coll_y` は **命令値**（ユーザーが指定した位置）
> - `after_position.coll_x_shift`, `coll_y_shift` は **実効値**（Position Service が返した実際のズレ）
> - 現時点ではパススルーのため同一値だが、将来 Position Service に非線形性が入ると乖離する

#### Request Body

```jsonc
{
  "coll_x": 0.02,              // mm, 命令レンズX位置
  "coll_y": -0.05,             // mm, 命令レンズY位置
  "torque_upper": 0.5,         // N·m, 上ボルトトルク
  "torque_lower": 0.5,         // N·m, 下ボルトトルク
  "options": {
    "return_ray_hits": false,   // オプション, デフォルト false
    "return_images": false      // オプション, デフォルト false
  }
}
```

> **options フィールド**: すべてオプション。未指定時は `false` 。
> - `return_ray_hits=true`: API レスポンスに `ray_hits` を含め、かつ step JSON にも保存する
> - `return_images=true`: API レスポンスに `ray_path_image`, `spot_diagram_image` を含める（step JSON には保存しない）
>
> **return_images の Optics Sim へのマッピング**:
> Recipe Service は `return_images: true` を Optics Sim の `return_ray_path_image: true` および `return_spot_diagram_image: true` の両方に変換する。
> 個別制御が必要な場合は将来 options を拡張予定。

> **Bolt Service への random_seed**: Recipe Service は Bolt Service を呼ぶ際、常に `random_seed: null` を渡す（毎回ランダム）。
> 返却された `used_seed` を step JSON の `bolt_shift.used_seed` に記録する。
> 再現実験用にシードを指定する手段は将来検討。

#### Response (200)

```jsonc
{
  "step_index": 0,

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
    "used_seed": 1234567890
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
  },

  "saved_to": "experiments/exp_001/trial_001/step_000.json"
}
```

### `GET /experiments/{experiment_id}/trials`

試行一覧。

#### Response (200)

```jsonc
{
  "trials": [
    {"trial_id": "trial_001", "mode": "manual", "started_at": "...", "total_steps": 5},
    {"trial_id": "trial_002", "mode": "control_loop", "started_at": "...", "total_steps": 12}
  ]
}
```

### `GET /experiments/{experiment_id}/trials/{trial_id}`

試行詳細（trial_meta.json + summary.json）。

### `GET /experiments/{experiment_id}/trials/{trial_id}/steps`

全ステップ一覧（サマリのみ）。

#### Response (200)

```jsonc
{
  "steps": [
    {
      "step_index": 0,
      "command": {"coll_x": 0.02, "coll_y": -0.05, "torque_upper": 0.5, "torque_lower": 0.5},
      "sim_after_position": {"spot_center_x": 0.005, "spot_center_y": -0.038, "spot_rms_radius": 0.006},
      "sim_after_bolt": {"spot_center_x": 0.012, "spot_center_y": -0.042, "spot_rms_radius": 0.005}
    }
  ]
}
```

### `GET /experiments/{experiment_id}/trials/{trial_id}/steps/{step_index}`

特定ステップの詳細データ。

### `POST /experiments/{experiment_id}/trials/{trial_id}/complete`

試行を完了し、summary.json を生成。リクエストボディは不要。

#### Request Body

なし（空の POST）

#### Response (200)

```jsonc
{
  "trial_id": "trial_001",
  "experiment_id": "exp_001",
  "mode": "manual",
  "total_steps": 5,
  "final_step": {
    "spot_center_x": 0.001,
    "spot_center_y": -0.002,
    "spot_rms_radius": 0.004
  },
  "finished_at": "2026-03-27T10:10:00Z"
}
```

#### Error (409)

既に complete 済みの試行に対して呼んだ場合:
```jsonc
{"detail": "trial already completed"}
```

### `POST /experiments/{experiment_id}/trials/{trial_id}/steps/{step_index}/images`

保存済みステップの画像を再取得。内部で同じパラメータ + `return_ray_path_image=true`, `return_spot_diagram_image=true` で Optics Sim を再呼出しする。

#### Request Body

```jsonc
{
  "phase": "after_position"    // "after_position" | "after_bolt" どちらのフェーズの画像か
}
```

#### Response (200)

```jsonc
{
  "ray_path_image": "<base64 PNG>",
  "spot_diagram_image": "<base64 PNG>"
}
```

> **注意**: 画像は保存されず毎回計算される。光線のランダム性により、元のシミュレーションと微小な差が出る可能性がある。

### `POST /recipes/sweep`

パラメータスイープ（単一パラメータを変化させて複数シミュレーション）。

> **試行ID管理**: sweep は自動的に新しい trial を作成する（`mode: "sweep"`）。
> 各スイープ値が 1 ステップとして記録される。
> sweep 完了時に内部で summary.json を直接書き込む（`/complete` API は呼ばない）。
> クライアント側で `/complete` を呼ぶ必要はない。

#### Request Body

```jsonc
{
  "experiment_id": "exp_001",
  "base_command": {
    "coll_x": 0.0, "coll_y": 0.0,
    "torque_upper": 0.5, "torque_lower": 0.5
  },
  "sweep": {
    "param_name": "coll_y",
    "values": [-0.1, -0.05, 0.0, 0.05, 0.1]
    // または "start": -0.1, "stop": 0.1, "step": 0.05
  }
}
```

#### Response (200)

```jsonc
{
  "trial_id": "trial_003",
  "mode": "sweep",
  "sweep_param": "coll_y",
  "results": [
    {
      "step_index": 0,
      "param_value": -0.1,
      "sim_after_position": {"spot_center_x": ..., "spot_center_y": ..., "spot_rms_radius": ...},
      "sim_after_bolt": {"spot_center_x": ..., "spot_center_y": ..., "spot_rms_radius": ...}
    }
  ]
}
```

### `GET /health`

```jsonc
{"status": "ok", "service": "recipe-service", "version": "0.1.0"}
```

## エラーレスポンス定義

| ステータス | 条件 | 内容 |
|-----------|------|------|
| 200 | 正常完了 | 結果データ |
| 201 | リソース作成成功 | 実験・試行の作成 |
| 404 | リソース未存在 | `{"detail": "experiment not found: exp_999"}` |
| 409 | 状態矛盾 | `{"detail": "trial already completed"}` |
| 422 | パラメータ不正 | FastAPI標準のバリデーションエラー |
| 502 | 下流サービスエラー | `{"detail": "optics-sim returned error: <内容>", "downstream": "optics-sim"}` |
| 504 | 下流サービスタイムアウト | `{"detail": "timeout calling bolt-service", "downstream": "bolt-service"}` |

### 下流サービス障害時の挙動

- タイムアウト: 環境変数 `DOWNSTREAM_TIMEOUT_SEC` で設定（デフォルト30秒）
- ステップ途中で失敗した場合、途中結果は保存しない（アトミック）

### アトミック性の詳細

ステップ実行は Position → Sim(1回目) → Bolt → Sim(2回目) の4工程からなる。

| 障害ポイント | 挙動 |
|----------------|------|
| Position 失敗 | step JSON 保存なし。502 を返却 |
| Sim(1回目) 失敗 | step JSON 保存なし。502 を返却 |
| Bolt 失敗 | **1回目の Sim 結果も破棄**。step JSON 保存なし。502 を返却 |
| Sim(2回目) 失敗 | **全体破棄**。step JSON 保存なし。502 を返却 |
| 全工程成功 | step JSON を保存。200 を返却 |

クライアントはリトライ可能。Bolt のノイズ以外は同じ結果になる。
- エラーレスポンスに `downstream` フィールドで障害元サービスを明示

## オーケストレーション・ロジック

### エンジン選択

Recipe Service は実験の `engine_type` に応じて異なる Optics Sim サービスを呼び出します：

- `engine_type: "KrakenOS"`: `OPTICS_SIM_KRAKEN_URL` で指定されたエンドポイント（デフォルト: `http://optics-sim-kraken:8000`）
- `engine_type: "Simple"`: `OPTICS_SIM_SIMPLE_URL` で指定されたエンドポイント（デフォルト: `http://optics-sim-simple:8000`）

両エンジンとも同じAPI仕様（`POST /simulate`）を持つため、Recipe Service はエンジンを透過的に切り替えられます。

### カメラ設定の転送

実験に `camera` 設定がある場合、Optics Sim へのリクエストに `camera` フィールドを含めます：

```python
def _build_simulation_payload(experiment, coll_x_shift, coll_y_shift, ...):
    payload = dict(experiment["optical_system"])
    payload["coll_x_shift"] = coll_x_shift
    payload["coll_y_shift"] = coll_y_shift
    payload["return_ray_hits"] = return_ray_hits
    payload["return_ray_path_image"] = return_images
    payload["return_spot_diagram_image"] = return_images
    
    # カメラ設定を転送
    if experiment.get("camera"):
        payload["camera"] = experiment["camera"]
    
    return payload
```

- **KrakenOS版**: `camera` フィールドを無視（`extra="ignore"` のため問題なし）
- **Simple版**: `camera.fov_width_mm` / `camera.fov_height_mm` を使用して画像生成

### 1ステップ実行時の内部処理

```
1. Position Service に coll_x, coll_y を送信 → coll_x_shift, coll_y_shift 取得
2. 光学パラメータ + camera 設定 + coll_x/y_shift で Optics Sim 呼び出し (engine_type に応じたURL) → 結果A
3. Bolt Service に torque_upper, torque_lower, bolt_model を送信 → delta_x, delta_y 取得
4. coll_x_shift += delta_x, coll_y_shift += delta_y で Optics Sim 再呼び出し → 結果B
5. step_NNN.json として結果A, 結果B を保存
```
