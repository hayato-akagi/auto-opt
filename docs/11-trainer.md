# Trainer 仕様

- **Port**: 9008
- **役割**: recipe-service から学習データを収集し、AI モデルを学習・評価し、合格時に model-store へ登録する。
- **依存**: recipe-service, model-store, simple-controller（ベンチ評価）, ai-controller（ベンチ評価）

## 学習タスクの概要

### 入力

- recipe-service に蓄積されたステップ記録（`bolt_shift`、`command`、実験条件）
- トレーニング設定（エポック数、学習率、最小サンプル数など）

### 出力

- 学習済みモデルファイル（`.pt`）
- 評価メトリクス
- model-store への登録（合格時のみ）

## 学習データの構築

### データ取得

1. recipe-service の `GET /experiments` で全実験を取得
2. 各実験の `GET /experiments/{eid}/trials` でトライアル一覧を取得
3. 各トライアルの `GET /experiments/{eid}/trials/{tid}/steps/{i}` でステップ詳細を取得  
   - `bolt_shift`（ラベル）
   - `command.coll_x/y`（入力の一部）
   - 実験の bolt_model パラメータ（入力の一部）

### 特徴量・ラベル

| 名称 | 取得元 | 備考 |
|------|--------|------|
| 特徴量 12 次元 | `command.coll_x/y` + 実験の bolt_model.upper params | [09-ai-controller.md](./09-ai-controller.md) の特徴量定義を参照 |
| ラベル | `bolt_shift.delta_x`, `bolt_shift.delta_y` | bolt shift 実測値 |

DNN は bolt shift を予測するモデルを学習する。推論時は予測値の **逆符号** を baseline に加算して補正する。

### データフィルタリング

- `bolt_shift` が `null` のステップは除外する
- `step_index == 0`（初期観測ステップ）はコマンドが意味を持たないため除外する

### 損失関数

$$
L = \frac{1}{N} \sum_{i=1}^{N} w_i \left( (\hat{\delta x}_i - \delta x_i)^2 + (\hat{\delta y}_i - \delta y_i)^2 \right)
$$

## API

### `POST /train`

新しい学習ジョブを開始。

#### Request Body

```jsonc
{
  "experiment_ids": ["exp_001", "exp_002"],  // 最低1つ必須。学習データ取得元
  "model_type": "mlp",                        // "mlp" | "baseline_only", デフォルト "mlp"
  "epochs": 50,                               // デフォルト 50, 範囲 [1, 500]
  "batch_size": 32                            // デフォルト 32, 範囲 [1, 256]
}
```

#### Response (200)

```jsonc
{
  "train_job_id": "train_job_000001",
  "status": "running",
  "message": "Training job train_job_000001 started"
}
```

### `GET /train`

全学習ジョブの一覧。

#### Response (200)

```jsonc
{
  "jobs": [
    {
      "train_job_id": "train_job_000001",
      "status": "completed",
      "data_stats": {
        "total_steps": 450,
        "train_samples": 400,
        "val_samples": 50
      },
      "train_metrics": {
        "epoch_losses": [0.5, 0.45, 0.4, 0.35, 0.3],
        "final_train_loss": 0.3,
        "epochs": 5
      },
      "benchmark_results": {
        "new_model": {
          "median_final_error_mm": 0.05,
          "p95_final_error_mm": 0.10,
          "converge_rate": 0.95,
          "trial_errors_mm": [0.02, 0.05, 0.08, 0.03, 0.07],
          "benchmark_trial_ids": ["trial_001", "trial_002", "trial_003", "trial_004", "trial_005"]
        },
        "current_model": {
          "median_final_error_mm": 0.08,
          "p95_final_error_mm": 0.15,
          "converge_rate": 0.90,
          "trial_errors_mm": [0.05, 0.08, 0.12, 0.06, 0.10],
          "benchmark_trial_ids": ["trial_001", "trial_002", "trial_003", "trial_004", "trial_005"]
        }
      },
      "promoted": true,
      "promoted_version": "v1.0.0",
      "error_message": null,
      "created_at": "2026-05-10T12:00:00Z"
    }
  ]
}
```

### `GET /train/{train_job_id}`

特定の学習ジョブステータスを取得。

#### Response (200)

`train_metrics`, `benchmark_results` の詳細を含む。

```jsonc
{
  "train_job_id": "train_job_000001",
  "status": "completed",
  "data_stats": { "..." },
  "train_metrics": { "..." },
  "benchmark_results": { "..." },
  "promoted": true,
  "promoted_version": "v1.0.0",
  "error_message": null
}
```

> **ステータスの遷移**: `running` → `completed` | `failed` | `skipped`
>
> - `running`: ジョブ実行中
> - `completed`: 学習と評価が成功
> - `failed`: エラーによる終了
> - `skipped`: 学習データが不足して実行スキップ
>
> `promoted` は `true` の場合のみ、`promoted_version` にモデルバージョンが格納される。

重み $w_i$: 最終ステップ（収束前の最後のステップ）は重みを 2.0 とし、それ以外は 1.0 とする。  
これにより終端性能を重視した学習になる。

## 評価（昇格判定）

### 評価ベンチ

固定の実験条件セット × 固定の seed セットで評価する。ベンチ設定はジョブリクエスト内で指定するか、環境変数で設定する。

### 昇格条件（デフォルト）

以下をすべて満たす場合のみ model-store へ current として登録する。

| 指標 | 昇格基準 |
|------|------|
| 最終誤差中央値 | 現行 current の 0.95 倍以下（5% 以上改善） |
| 最終誤差 95パーセンタイル | 現行 current の 1.05 倍以下（5% 以上の悪化を許容しない） |
| 収束失敗率 | 現行 current ± 0.05 以内 |

閾値はすべてジョブリクエストで上書き可能。

## API

### `POST /train`

学習ジョブを作成して開始する。レスポンスは即時返却し、学習は非同期で実行する。

#### Request Body

```jsonc
{
  "model_type": "mlp",                     // "mlp"（baseline_only は学習不要）
  "mlp_config": {                          // model_type=mlp のとき有効
    "hidden_sizes": [64, 64],
    "learning_rate": 1e-3,
    "epochs": 100,
    "batch_size": 256
  },
  "data_filter": {
    "experiment_ids": ["exp_001", "exp_002"],  // 省略時は全実験
    "min_steps": 200                           // この件数未満なら学習を中止
  },
  "benchmark": {
    "experiment_ids": ["exp_001", "exp_002"],
    "seeds": [101, 102, 103, 104, 105],
    "max_steps": 10,
    "tolerance": 0.05
  },
  "promotion": {
    "median_improvement": 0.05,
    "percentile95_tolerance": 0.05,
    "converge_rate_tolerance": 0.05
  }
}
```

#### Response (202)

```jsonc
{
  "train_job_id": "tjob_20260510_120000_0001",
  "status": "running",
  "created_at": "2026-05-10T12:00:00Z"
}
```

### `GET /train/{train_job_id}`

学習ジョブの状態・結果を返す。

#### Response (200)

```jsonc
{
  "train_job_id": "tjob_20260510_120000_0001",
  "status": "completed",         // "running" | "completed" | "failed" | "skipped"
  "data_stats": {
    "total_steps": 1250,
    "experiments_used": 5
  },
  "train_metrics": {
    "final_train_loss": 0.0032,
    "epochs": 100
  },
  "benchmark_results": {
    "new_model": {
      "median_final_error_mm": 0.018,
      "p95_final_error_mm": 0.045,
      "converge_rate": 0.92
    },
    "current_model": {
      "median_final_error_mm": 0.021,
      "p95_final_error_mm": 0.048,
      "converge_rate": 0.90
    }
  },
  "promoted": true,
  "promoted_version": "v4"
}
```

### `GET /train`

学習ジョブ一覧を返す。

## ファイル構成

```
services/trainer/
  Dockerfile.cpu
  Dockerfile.gpu
  requirements.txt
  app/
    __init__.py
    main.py         # FastAPI エントリポイント
    job_runner.py   # 学習ジョブ非同期実行エンジン
    data.py         # recipe-serviceからのデータ収集・前処理
    train.py        # PyTorchモデル定義・学習ループ
    evaluate.py     # ベンチ評価・昇格判定
    models.py       # Pydantic モデル
    clients.py      # recipe-service, model-store, 制御器 クライアント
    storage.py      # ジョブ状態保存
```
