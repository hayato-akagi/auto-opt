# ai-controller

AI モデル（MLP）を使った制御器サービス。ベースライン比例制御出力に対する残差補正を推論し、最終操作量を決定する。

- **Port**: 9006
- **技術スタック**: Python, FastAPI, PyTorch
- **依存サービス**: recipe-service, model-store
- **準拠仕様**: ../../docs/05-controller.md, ../../docs/09-ai-controller.md

⚠️ **実装状態**: 現在スタブ実装（ヘルスチェックのみ）。
PyTorch MLP 推論ロジックと model-store 連携は将来実装予定。

## モデル種別

| model_type | 内容 |
|---|---|
| `mlp` | PyTorch MLP。残差補正を推論。model-store から重みをロード |
| `baseline_only` | DNN 推論をスキップ。ベースライン出力をそのまま返す |

## API

### POST /control/run

単一エピソードの制御ループを実行する。

Request 例:

```jsonc
{
  "experiment_id": "exp_001",
  "algorithm": "ai-controller",
  "config": {
    "model_type": "mlp",
    "model_version": null,
    "spot_to_coll_scale_x": 50.0,
    "spot_to_coll_scale_y": 50.0,
    "delta_clip_x": 0.1,
    "delta_clip_y": 0.1,
    "coll_x_min": -0.5,
    "coll_x_max": 0.5,
    "coll_y_min": -0.5,
    "coll_y_max": 0.5,
    "safety_threshold": 0.5,
    "safety_bias": 0.01,
    "release_perturbation": { "std_x": 0.0, "std_y": 0.0 }
  },
  "target": { "spot_center_x": 0.0, "spot_center_y": 0.0 },
  "initial_coll": { "coll_x": 0.0, "coll_y": 0.0 },
  "max_steps": 20,
  "tolerance": 0.05,
  "random_seed": 42
}
```

Response 例:

```jsonc
{
  "trial_id": "trial_010",
  "algorithm": "ai-controller",
  "model_version": "v3",
  "model_type": "mlp",
  "converged": true,
  "steps": 5,
  "final_spot_center_x": 0.0003,
  "final_spot_center_y": -0.0002,
  "final_distance": 0.00036
}
```

### POST /model/reload

model-store から current モデルを再ロードする。

### GET /model/status

現在ロード中のモデル情報を返す。

### GET /health

ヘルスチェック。

## Dockerfile

- `Dockerfile.cpu`: PyTorch CPU wheel（デフォルト）
- `Dockerfile.gpu`: PyTorch CUDA wheel（GPU 環境向け）

docker-compose.gpu.yml でオーバーライドする。

## 環境変数

| 変数 | デフォルト | 説明 |
|------|------|------|
| `RECIPE_SERVICE_URL` | `http://recipe-service:9002` | recipe-service のベース URL |
| `MODEL_STORE_URL` | `http://model-store:9009` | model-store のベース URL |
| `MODEL_SAFETY_THRESHOLD` | `0.5` | DNN 残差の安全閾値 |
| `MODEL_SAFETY_BIAS` | `0.01` | DNN 残差の安全バイアス |
