# ai-controller

AI モデル（MLP）を使った制御器サービス。ベースライン比例制御出力に対する残差補正を推論し、最終操作量を決定する。

- **Port**: 9006
- **技術スタック**: Python, FastAPI, PyTorch
- **依存サービス**: recipe-service
- **準拠仕様**: ../../docs/05-controller.md, ../../docs/09-ai-controller.md（仕様は一部更新中、実装が正）

## モデル種別

| model_type | 内容 |
|---|---|
| `mlp` | PyTorch MLP。過去 N ステップの履歴（各ステップ: 補正前spot位置・指令coll位置・補正後spot位置の6次元、ゼロ埋め最大10ステップ分）＋現在の観測spot位置2次元を入力し、bolt shift（残差）を推論 |
| `baseline_only` | DNN 推論をスキップ。ベースライン出力をそのまま返す |

## モデルのロード方法

model-store とは連携していない（`MODEL_STORE_URL` 設定は現状未使用）。モデルは以下のいずれかでロードされる。

- リクエストの `config.model_path` にローカルの `.pt` ファイルパスを指定する（リクエストごとに一時的な `ModelManager` を生成してロード）
- 指定しない場合は起動時に作成されるデフォルトの `ModelManager` を使う。ただし起動時は `DEFAULT_MODEL_TYPE`/`DEFAULT_MODEL_VERSION` のラベルが設定されるだけで、`model_path` を渡さない限り実際の重みはロードされない（`mlp` を指定しても未ロードなら残差はゼロを返す）

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
  "initial_observation": {
    "step_index": 0,
    "initial_coll_x": 0.0,
    "initial_coll_y": 0.0,
    "spot_pre_x": 0.01,
    "spot_pre_y": -0.02,
    "spot_post_x": 0.008,
    "spot_post_y": -0.018,
    "boot_correction_x": -0.0002,
    "boot_correction_y": 0.0004
  },
  "final_spot_center_x": 0.0003,
  "final_spot_center_y": -0.0002,
  "final_spot_rms_radius": 0.0012,
  "final_distance": 0.00036
}
```

### POST /model/reload

`DEFAULT_MODEL_TYPE`/`DEFAULT_MODEL_VERSION`（環境変数）のラベルにリセットする。
**注**: 現状は型・バージョンのラベルを更新するだけで、モデルの重みは再ロードしない
（重みをロードし直すには `/control/run` のリクエストで `config.model_path` を指定する）。

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
| `RECIPE_SERVICE_URL` | `http://recipe-service:8002` | recipe-service のベース URL |
| `MODEL_STORE_URL` | `http://model-store:9009` | 現状未使用（model-store 連携は未実装） |
| `DOWNSTREAM_TIMEOUT_SEC` | `10.0` | recipe-service 呼び出しのタイムアウト（秒） |
| `DEFAULT_MODEL_TYPE` | `baseline_only` | 起動時デフォルトの `model_type` |
| `DEFAULT_MODEL_VERSION` | `null` | 起動時デフォルトの `model_version`（ラベルのみ、重みロードには使われない） |

`safety_threshold` / `safety_bias` は環境変数ではなく、リクエストの `config.safety_threshold` / `config.safety_bias`（デフォルト `0.5` / `0.01`）で指定する。
