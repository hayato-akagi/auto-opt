# simple-controller

相対操作量を返す最初の制御器サービス。Recipe Service を利用して自動反復を行い、目標スポット位置への収束を試みる。

- Port: 8003
- 技術スタック: Python, FastAPI
- 依存サービス: recipe-service
- 準拠仕様: ../../docs/05-controller.md
- 個別仕様: ../../docs/10-simple-controller.md

## API

### POST /control/run

単一エピソードの制御ループを実行する。

Request 例:

```jsonc
{
  "experiment_id": "exp_001",
  "algorithm": "simple-controller",
  "config": {
    "gain_x": 1.0,
    "gain_y": 1.0,
    "delta_clip_x": 0.05,
    "delta_clip_y": 0.05,
    "coll_x_min": -0.5,
    "coll_x_max": 0.5,
    "coll_y_min": -0.5,
    "coll_y_max": 0.5,
    "release_perturbation": {
      "std_x": 0.002,
      "std_y": 0.002
    }
  },
  "target": {
    "spot_center_x": 0.0,
    "spot_center_y": 0.0
  },
  "initial_coll": {
    "coll_x": 0.0,
    "coll_y": 0.0
  },
  "max_steps": 20,
  "tolerance": 0.005
}
```

Response 例:

```jsonc
{
  "trial_id": "trial_003",
  "algorithm": "simple-controller",
  "converged": true,
  "steps": 7,
  "final_spot_center_x": 0.0004,
  "final_spot_center_y": -0.0003,
  "final_spot_rms_radius": 0.004,
  "final_distance": 0.0005
}
```

### POST /control/step

1ステップ分の相対操作量だけを計算する（Recipe Service は呼ばない）。

Request 例:

```jsonc
{
  "algorithm": "simple-controller",
  "config": {
    "gain_x": 1.0,
    "gain_y": 1.0,
    "delta_clip_x": 0.05,
    "delta_clip_y": 0.05,
    "coll_x_min": -0.5,
    "coll_x_max": 0.5,
    "coll_y_min": -0.5,
    "coll_y_max": 0.5
  },
  "state": {
    "target_spot_center_x": 0.0,
    "target_spot_center_y": 0.0,
    "current_coll_x": 0.05,
    "current_coll_y": -0.02,
    "spot_pre_x": 0.012,
    "spot_pre_y": -0.008,
    "spot_post_x": 0.018,
    "spot_post_y": -0.014,
    "step_index": 3,
    "history": []
  }
}
```

Response 例:

```jsonc
{
  "delta_coll_x": 0.012,
  "delta_coll_y": 0.008,
  "next_coll_x": 0.062,
  "next_coll_y": -0.012,
  "converged": false,
  "info": {
    "error_x": 0.012,
    "error_y": 0.008,
    "distance_pre": 0.014,
    "distance_post": 0.023,
    "clipped_x": false,
    "clipped_y": false
  }
}
```

### GET /control/algorithms

利用可能アルゴリズム一覧を返す。

```jsonc
{
  "algorithms": [
    {
      "name": "simple-controller",
      "description": "相対操作量を返すシンプル制御器",
      "config_schema": {
        "type": "object"
      }
    }
  ]
}
```

### GET /health

```jsonc
{"status": "ok", "service": "simple-controller", "version": "0.1.0"}
```

## 実装方針

- /control/run は Step 0（初期観測）を先に実行する
- Step 0 は max_steps に含めない
- 収束判定は sim_after_bolt の spot_center_x/y を使う
- XY 調整前スポットは「前ステップ sim_after_position + 緩め時揺らぎ」を使用する
- /control/step はステートレスで、呼び出し側が state を完全に渡す

## 環境変数

| 変数 | デフォルト | 内容 |
|------|----------|------|
| PORT | 8003 | リッスンポート |
| RECIPE_SERVICE_URL | - | Recipe Service の URL |

## 開発

```bash
cd services/simple-controller
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```
