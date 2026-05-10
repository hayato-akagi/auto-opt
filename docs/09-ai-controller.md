# AI Controller 仕様

- **Port**: 9006
- **役割**: AI モデルを使った制御器。ベースライン（proportional）出力に対する **残差補正** を推論し、最終操作量を決定する。
- **依存**: recipe-service, model-store
- **初回実装モデル**: MLP（残差補正）、baseline-only（比較用フォールバック）

## 制御方式

### 残差補正の考え方

```
baseline_delta = (target_spot - current_spot) / spot_to_coll_scale

dnn_residual   = model.predict(features)   # bolt_shift予測の逆補正

final_delta    = baseline_delta + dnn_residual
```

最終操作量は常に baseline に対する **加算補正** であり、DNN が baseline を完全に置き換えることはない。

### 安全ガード

DNN 出力が大きすぎる場合は baseline のみを使用する。

```
if norm(dnn_residual) > safety_threshold * norm(baseline_delta) + safety_bias:
    final_delta = baseline_delta   # fallback
```

`safety_threshold` と `safety_bias` は config で設定可能。デフォルト: `threshold=0.5, bias=0.01`。

## モデル種別

| `model_type` | 内容 |
|---|---|
| `mlp` | PyTorch MLP。入力12次元→隠れ層2段(64units)→出力2次元。残差学習。 |
| `baseline_only` | DNN推論をスキップ。`baseline_delta` をそのまま返す。比較用。 |

`model_type` はリクエストの `config.model_type` で指定する。省略時は model-store の `current` モデルの設定に従う。

## 特徴量定義

1ステップの推論に使う入力特徴量（12次元）：

| 特徴量 | 説明 |
|--------|------|
| `coll_x` | 現在のコリメータX位置 (mm) |
| `coll_y` | 現在のコリメータY位置 (mm) |
| `x0_bias_x` | 実験設定: bolt upper x0_bias_x |
| `x0_bias_y` | 実験設定: bolt upper x0_bias_y |
| `a_x` | 実験設定: bolt upper a_x |
| `b_x` | 実験設定: bolt upper b_x |
| `a_y` | 実験設定: bolt upper a_y |
| `b_y` | 実験設定: bolt upper b_y |
| `noise_ratio_min_x` | 実験設定: bolt upper noise_ratio_min_x |
| `noise_ratio_max_x` | 実験設定: bolt upper noise_ratio_max_x |
| `noise_ratio_min_y` | 実験設定: bolt upper noise_ratio_min_y |
| `noise_ratio_max_y` | 実験設定: bolt upper noise_ratio_max_y |

**注**: lower bolt unit のパラメータは現時点では特徴量に含めない。将来的に必要なら拡張する。

## MLP アーキテクチャ

```
Input(12) → Linear(64) → ReLU → Linear(64) → ReLU → Linear(2)
```

出力は `[residual_x, residual_y]`（mm 単位、coll 空間）。

## デバイス選択

起動時に自動判定する。

```python
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
```

Dockerfile は CPU 用 (`Dockerfile.cpu`) と GPU 用 (`Dockerfile.gpu`) に分ける。

## API

### `POST /control/run`

simple-controller と同じインターフェース。`config.model_type` を追加。

#### Request Body

```jsonc
{
  "experiment_id": "exp_001",
  "algorithm": "ai-controller",
  "config": {
    "model_type": "mlp",               // "mlp" | "baseline_only"
    "model_version": "v3",             // 省略時は model-store の current を使用
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

#### Response (200)

simple-controller と同一。追加フィールドとして `model_version` を返す。

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

### `POST /model/reload`

model-store から current モデルを再ロードする。学習完了・昇格後に呼び出す。

#### Response (200)

```jsonc
{ "loaded_version": "v4", "model_type": "mlp" }
```

### `GET /model/status`

現在ロード中のモデル情報を返す。

#### Response (200)

```jsonc
{
  "loaded_version": "v3",
  "model_type": "mlp",
  "loaded_at": "2026-05-10T12:00:00Z",
  "device": "cpu"
}
```

## Dockerfile 構成

```
services/ai-controller/
  Dockerfile.cpu     # torch CPU wheel
  Dockerfile.gpu     # torch CUDA wheel
  requirements.txt
  app/
    __init__.py
    main.py          # FastAPI エントリポイント
    logic.py         # 制御ループ、baseline 計算、残差合成
    model.py         # モデルロード・推論インターフェース
    models.py        # Pydantic モデル
    clients.py       # recipe-service, model-store クライアント
```

docker-compose.yml はデフォルトで `Dockerfile.cpu` を使用。GPU 環境では `docker-compose.gpu.yml` をオーバーライドする。
