# recipe-service

オーケストレーター。実験・試行の管理、サービス間の呼び出し順序制御、データ保存を担う。

- **Port**: 8002
- **技術スタック**: Python, FastAPI
- **依存サービス**: optics-sim, position-service, bolt-service

## API 一覧

| メソッド | パス | 内容 |
|---------|------|------|
| `POST` | `/experiments` | 実験（系）を新規作成 |
| `GET` | `/experiments` | 実験一覧 |
| `GET` | `/experiments/{id}` | 実験詳細 |
| `POST` | `/experiments/{id}/trials` | 試行を開始 |
| `GET` | `/experiments/{id}/trials` | 試行一覧 |
| `GET` | `/experiments/{id}/trials/{id}` | 試行詳細 |
| `POST` | `/experiments/{id}/trials/{id}/steps` | 1ステップ実行 |
| `GET` | `/experiments/{id}/trials/{id}/steps` | 全ステップ一覧（サマリ） |
| `GET` | `/experiments/{id}/trials/{id}/steps/{idx}` | ステップ詳細 |
| `POST` | `/experiments/{id}/trials/{id}/steps/{idx}/images` | 画像再取得 |
| `POST` | `/experiments/{id}/trials/{id}/complete` | 試行完了 |
| `POST` | `/recipes/sweep` | パラメータスイープ |
| `GET` | `/health` | ヘルスチェック |

## ID採番

実験ID (`exp_001`, `exp_002`, ...) および試行ID (`trial_001`, `trial_002`, ...) は自動連番。ユーザー指定不可（衝突防止）。

## `POST /experiments`

#### Request

```jsonc
{
  "name": "baseline_780nm",
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

## `POST /experiments/{id}/trials`

#### Request

```jsonc
{
  "mode": "manual",       // "manual" | "control_loop"
  "control": null          // control_loop時のみ設定
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

## `POST /experiments/{id}/trials/{id}/steps`

1ステップを実行。Position → Sim → Bolt → Sim の全フローを実行し、結果を保存して返す。

### Sim レスポンスの透過

`sim_after_position` / `sim_after_bolt` は Optics Sim のレスポンスをそのまま含む（`spot_center_x/y`, `spot_rms_radius`, `spot_geo_radius`, `spot_peak_x/y`, `num_rays_launched`, `num_rays_arrived`, `vignetting_ratio`, `computation_time_ms`）。Recipe Service が独自にフィールドを加工・選択することはない。

### 命令値と実効値の区別

- リクエストの `coll_x`, `coll_y` は **命令値**（ユーザーが指定した位置）
- `after_position.coll_x_shift`, `coll_y_shift` は **実効値**（Position Service が返した実際のズレ）
- 現時点ではパススルーのため同一値だが、将来 Position Service に非線形性が入ると乖離する

#### Request

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

**options フィールド**: すべてオプション。未指定時は `false`。
- `return_ray_hits=true`: API レスポンスに `ray_hits` を含め、かつ step JSON にも保存する
- `return_images=true`: API レスポンスに `ray_path_image`, `spot_diagram_image` を含める（step JSON には保存しない）

**return_images の Optics Sim へのマッピング**:
`return_images: true` → Optics Sim の `return_ray_path_image: true` および `return_spot_diagram_image: true` の両方に変換。個別制御は将来拡張予定。

**Bolt Service への random_seed**: 常に `random_seed: null` を渡す（毎回ランダム）。返却された `used_seed` を step JSON の `bolt_shift.used_seed` に記録する。

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

## `POST /experiments/{id}/trials/{id}/complete`

試行を完了し summary.json を生成。リクエストボディ不要（空の POST）。

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

既に complete 済みの試行: `{"detail": "trial already completed"}`

## `POST /experiments/{id}/trials/{id}/steps/{idx}/images`

保存済みステップの画像を再取得。内部で同じパラメータ + `return_*_image=true` で Optics Sim を再呼出し。

#### Request

```jsonc
{
  "phase": "after_position"    // "after_position" | "after_bolt"
}
```

#### Response (200)

```jsonc
{
  "ray_path_image": "<base64 PNG>",
  "spot_diagram_image": "<base64 PNG>"
}
```

> 画像は保存されず毎回計算される。光線のランダム性により元のシミュレーションと微小な差が出る可能性がある。

## `POST /recipes/sweep`

パラメータスイープ。自動的に新しい trial を作成する（`mode: "sweep"`）。各スイープ値が 1 ステップとして記録される。sweep 完了時に内部で summary.json を直接書き込む（`/complete` API は呼ばない）。

#### Request

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

## エラーレスポンス

| ステータス | 条件 | 内容 |
|-----------|------|------|
| 200 | 正常完了 | 結果データ |
| 201 | リソース作成成功 | 実験・試行の作成 |
| 404 | リソース未存在 | `{"detail": "experiment not found: exp_999"}` |
| 409 | 状態矛盾 | `{"detail": "trial already completed"}` |
| 422 | パラメータ不正 | FastAPI標準バリデーションエラー |
| 502 | 下流サービスエラー | `{"detail": "optics-sim returned error: <内容>", "downstream": "optics-sim"}` |
| 504 | 下流タイムアウト | `{"detail": "timeout calling bolt-service", "downstream": "bolt-service"}` |

## アトミック性

ステップ実行は Position → Sim(1回目) → Bolt → Sim(2回目) の4工程からなる。

| 障害ポイント | 挙動 |
|-------------|------|
| Position 失敗 | step JSON 保存なし。502 返却 |
| Sim(1回目) 失敗 | step JSON 保存なし。502 返却 |
| Bolt 失敗 | **1回目の Sim 結果も破棄**。502 返却 |
| Sim(2回目) 失敗 | **全体破棄**。502 返却 |
| 全工程成功 | step JSON を保存。200 返却 |

クライアントはリトライ可能。Bolt のノイズ以外は同じ結果になる。

## オーケストレーション・ロジック

```
1. Position Service に coll_x, coll_y を送信 → coll_x_shift, coll_y_shift 取得
2. 光学パラメータに coll_x/y_shift を適用して Optics Sim 呼び出し (return_*_image=false) → 結果A
3. Bolt Service に torque_upper, torque_lower, bolt_model, random_seed=null を送信 → delta_x, delta_y, used_seed 取得
4. coll_x_shift += delta_x, coll_y_shift += delta_y で Optics Sim 再呼び出し → 結果B
5. step_NNN.json として結果A, 結果B を保存（画像は除外、ray_hits はオプション）
```

## データ保存形式

```
data/experiments/
└── {experiment_id}/
    ├── experiment.json          # 系の定義（不変）
    ├── {trial_id}/
    │   ├── trial_meta.json      # 試行メタ情報
    │   ├── step_000.json        # 各ステップの全記録
    │   ├── step_001.json
    │   └── summary.json         # 試行完了時に生成
    └── ...
```

詳細は docs/07-data-format.md を参照。

## 環境変数

| 変数 | デフォルト | 内容 |
|------|----------|------|
| `PORT` | `8002` | リッスンポート |
| `OPTICS_SIM_URL` | - | Optics Sim のURL |
| `POSITION_SERVICE_URL` | - | Position Service のURL |
| `BOLT_SERVICE_URL` | - | Bolt Service のURL |
| `DOWNSTREAM_TIMEOUT_SEC` | `30` | 下流サービスタイムアウト（秒） |

## 開発

```bash
cd services/recipe-service
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```
