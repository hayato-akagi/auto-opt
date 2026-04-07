# controller（将来実装）

制御アルゴリズム（PID等）により、目標スポット位置への収束を自動制御するサービス。

- **Port**: 8003
- **技術スタック**: Python, FastAPI
- **依存サービス**: recipe-service（ステップ実行を委譲）

## API

### `POST /control/run`

制御ループ全体を実行。

#### Request

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

#### Request

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
    "history": []
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

```jsonc
{
  "algorithms": [
    {
      "name": "pid",
      "description": "PID制御",
      "config_schema": { /* JSON Schema */ }
    }
  ]
}
```

### `GET /health`

```jsonc
{"status": "ok", "service": "controller", "version": "0.1.0"}
```

## エラーレスポンス

| ステータス | 条件 | 内容 |
|-----------|------|------|
| 200 | 正常完了（収束・打ち切り両方含む） | 制御結果 |
| 404 | 実験ID未存在 | `{"detail": "experiment not found"}` |
| 422 | パラメータ不正 | FastAPI標準バリデーションエラー |
| 502 | Recipe Service 障害 | `{"detail": "recipe-service error: <内容>"}` |
| 504 | Recipe Service タイムアウト | `{"detail": "timeout calling recipe-service"}` |

## 設計方針

### 状態管理

- Controller は **リクエスト間で状態を永続化しない**
- `/control/run` の1回の呼び出し内ではPID積分項・history等をメモリに保持する（**1リクエスト内の状態保持はある**）
- 呼び出しが終わればメモリから破棄される（リクエストをまたいだ状態は残らない）
- サービス再起動しても何も失わない（結果は Recipe Service に保存済み）
- PIDパラメータは Recipe Service にレシピとして保存

### history の管理責務

| API | history の管理者 | 説明 |
|-----|-----------------|------|
| `/control/run` | **Controller 自身** | ループ内で各ステップの結果を蓄積 |
| `/control/step` | **呼び出し側**（Streamlit等） | `state.history` に過去データを含めて渡す |

### `history` フォーマット

```jsonc
[
  {
    "step_index": 0,
    "coll_x": 0.02, "coll_y": -0.05,
    "torque_upper": 0.5, "torque_lower": 0.5,
    "spot_center_x": 0.012, "spot_center_y": -0.042,
    "spot_rms_radius": 0.005
  }
]
```

PIDは直近のステップのみ使用、将来のアルゴリズム（ベイズ最適化等）は全履歴を活用可能。

### 収束判定

**`sim_after_bolt` の `spot_center_x/y`** を使って判定（ボルト締結後の最終スポット位置）:

```
√((x_current - x_target)² + (y_current - y_target)²) < tolerance
```

- 1回満たしたら収束と判定（連続回数の要件なし）
- `max_iterations` に達したら `converged: false` で返却
- 将来拡張: `convergence_count: N`（N回連続で tolerance を満たしたら収束と判定）

### `/control/run` 内部フロー

```
1. Recipe Service に試行開始を依頼 (mode=control_loop)
2. history = []
3. PID演算 → 次の coll_x, coll_y を決定
4. Recipe Service に step 実行を依頼
5. 結果を history に追加
6. 収束判定 → 満たさなければ 3 に戻る
7. Recipe Service に試行完了を依頼
```

## 環境変数

| 変数 | デフォルト | 内容 |
|------|----------|------|
| `PORT` | `8003` | リッスンポート |
| `RECIPE_SERVICE_URL` | - | Recipe Service のURL |

## 開発

```bash
cd services/controller
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```
