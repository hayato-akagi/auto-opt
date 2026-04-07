# Controller サービス仕様（将来実装）

- **Port**: 8003
- **役割**: 制御アルゴリズム（PID等）により、目標スポット位置への収束を自動制御。
- **依存**: recipe-service（ステップ実行を委譲）

## API

### `POST /control/run`

制御ループ全体を実行。

#### Request Body

```jsonc
{
  "experiment_id": "exp_001",
  "algorithm": "pid",
  "config": {
    "kp_x": 0.8, "ki_x": 0.1, "kd_x": 0.05,
    "kp_y": 0.8, "ki_y": 0.1, "kd_y": 0.05,
    "default_torque_upper": 0.5,
    "default_torque_lower": 0.5
  },
  "target": {
    "spot_center_x": 0.0,
    "spot_center_y": 0.0
  },
  "max_iterations": 20,
  "tolerance": 0.001              // mm, ユークリッド距離で判定
}
```

#### Response (200)

```jsonc
{
  "trial_id": "trial_003",
  "converged": true,
  "iterations": 7,
  "final_spot_center_x": 0.0003,
  "final_spot_center_y": -0.0005,
  "final_spot_rms_radius": 0.004
}
```

### `POST /control/step`

1ステップの制御指令のみ計算（実行はしない）。

#### Request Body

```jsonc
{
  "algorithm": "pid",
  "config": {
    "kp_x": 0.8, "ki_x": 0.1, "kd_x": 0.05,
    "kp_y": 0.8, "ki_y": 0.1, "kd_y": 0.05
  },
  "state": {
    "target_spot_center_x": 0.0,
    "target_spot_center_y": 0.0,
    "current_spot_center_x": 0.05,
    "current_spot_center_y": 0.12,
    "current_coll_x": 0.0,
    "current_coll_y": 0.0,
    "trial_index": 0,
    "history": []                   // 過去の施行データ（アルゴリズムによっては使用）
  }
}
```

#### Response (200)

```jsonc
{
  "coll_x": 0.04,
  "coll_y": -0.096,
  "torque_upper": 0.5,
  "torque_lower": 0.5,
  "converged": false,
  "info": {"error_x": -0.05, "error_y": -0.12}
}
```

### `GET /control/algorithms`

利用可能アルゴリズム一覧。

#### Response (200)

```jsonc
{
  "algorithms": [
    {
      "name": "pid",
      "description": "PID制御",
      "config_schema": {
        "type": "object",
        "properties": {
          "kp_x": {"type": "number"}, "ki_x": {"type": "number"}, "kd_x": {"type": "number"},
          "kp_y": {"type": "number"}, "ki_y": {"type": "number"}, "kd_y": {"type": "number"},
          "default_torque_upper": {"type": "number"},
          "default_torque_lower": {"type": "number"}
        }
      }
    }
  ]
}
```

### `GET /health`

```jsonc
{"status": "ok", "service": "controller", "version": "0.1.0"}
```

## エラーレスポンス定義

| ステータス | 条件 | 内容 |
|-----------|------|------|
| 200 | 正常完了（収束・打ち切り両方含む） | 制御結果 |
| 404 | 実験ID未存在 | `{"detail": "experiment not found"}` |
| 422 | パラメータ不正 | FastAPI標準のバリデーションエラー |
| 502 | Recipe Service 障害 | `{"detail": "recipe-service error: <内容>"}` |
| 504 | Recipe Service タイムアウト | `{"detail": "timeout calling recipe-service"}` |

## 設計方針

- Controller は **リクエスト間で状態を永続化しない**
  - `/control/run` の1回の呼び出し内ではPID積分項・ history 等をメモリに保持する（**1リクエスト内の状態保持はある**）
  - 呼び出しが終わればメモリから破棄される（リクエストをまたいだ状態は残らない）
  - サービス再起動しても何も失わない（結果は Recipe Service に保存済み）
- `/control/step` は完全にステートレス。呼び出し側が `history` で過去情報を渡す
- PIDパラメータは Recipe Service にレシピとして保存
- 将来のアルゴリズム追加（ベイズ最適化、LQR等）は `algorithm` フィールドで切り替え
- 過去の施行データを入力に含められるように `history` フィールドを用意

### history の管理責務

| API | history の管理者 | 説明 |
|-----|-----------------|------|
| `/control/run` | **Controller 自身** | ループ内で各ステップの結果を蓄積。外部からの history 渡しは不要 |
| `/control/step` | **呼び出し側**（Streamlit等） | リクエストの `state.history` に過去データを含めて渡す |

`/control/run` の内部フロー:
```
1. Recipe Service に試行開始を依頼
2. history = []
3. PID演算 → 次の指令を決定
4. Recipe Service に step 実行を依頼
5. 結果を history に追加
6. 収束判定 (後述) → 満たさなければ 3 に戻る
7. Recipe Service に試行完了を依頼
```

### 収束しない場合の挙動

- `max_iterations` に達したらループを終了し、`converged: false` で返却
- 発振検出は将来追加予定（現時点では `max_iterations` のみで脱出）

### 収束判定の詳細

**`sim_after_bolt` の `spot_center_x/y`** を使って収束判定する（ボルト締結後の最終スポット位置）:

$$\sqrt{(x_{\text{current}} - x_{\text{target}})^2 + (y_{\text{current}} - y_{\text{target}})^2} < \text{tolerance}$$

- 1回満たしたら収束と判定（連続回数の要件なし）
- 将来拡張: `convergence_count: N`（N回連続で tolerance を満たしたら収束と判定）オプションを追加予定

### `history` フィールドのフォーマット

`/control/step` の `state.history` は以下の形式。全ステップ分を含む（`max_iterations` で上限があるため件数制限なし）:

```jsonc
"history": [
  {
    "step_index": 0,
    "coll_x": 0.02, "coll_y": -0.05,
    "torque_upper": 0.5, "torque_lower": 0.5,
    "spot_center_x": 0.012, "spot_center_y": -0.042,
    "spot_rms_radius": 0.005
  },
  {
    "step_index": 1,
    "coll_x": 0.01, "coll_y": -0.03,
    "torque_upper": 0.5, "torque_lower": 0.5,
    "spot_center_x": 0.005, "spot_center_y": -0.015,
    "spot_rms_radius": 0.004
  }
]
```

PIDは直近のステップのみ使用、将来のアルゴリズム（ベイズ最適化等）は全履歴を活用可能。

## 制御ループの流れ

```
1. Controller が Recipe Service に試行開始を依頼
2. PID 演算で次の coll_x, coll_y を決定
3. Recipe Service に step 実行を依頼（Position → Sim → Bolt → Sim）
4. ボルト締結後のスポット位置を取得
5. 誤差が tolerance 以内 or max_iterations に達したら終了
6. そうでなければ 2 に戻る
```
