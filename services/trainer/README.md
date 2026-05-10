# trainer

recipe-service から学習データを収集し、AI モデル（MLP）を学習・評価して model-store に登録するサービス。

- **Port**: 9008
- **技術スタック**: Python, FastAPI, PyTorch
- **依存サービス**: recipe-service, model-store, simple-controller, ai-controller
- **仕様**: ../../docs/11-trainer.md

## API

### POST /train

新しい学習ジョブを作成して非同期実行する。

Request 例:

```jsonc
{
  "experiment_ids": ["exp_001", "exp_002"],  // 最低1つ必須。学習データ取得元
  "model_type": "mlp",                        // "mlp" | "baseline_only", デフォルト "mlp"
  "epochs": 50,                               // デフォルト 50, 範囲 [1, 500]
  "batch_size": 32                            // デフォルト 32, 範囲 [1, 256]
}
```

Response 例 (200):

```jsonc
{
  "train_job_id": "train_job_000001",
  "status": "running",
  "message": "Training job train_job_000001 started"
}
```

### GET /train

全学習ジョブの一覧と大まかなステータスを返す。

Response 例 (200):

```jsonc
{
  "jobs": [
    {
      "train_job_id": "train_job_000001",
      "status": "completed",
      "data_stats": { "total_steps": 450 },
      "train_metrics": {
        "epoch_losses": [0.5, 0.45, ..., 0.3],
        "final_train_loss": 0.3,
        "epochs": 50
      },
      "benchmark_results": {
        "new_model": { "median_final_error_mm": 0.05, "..." },
        "current_model": { "median_final_error_mm": 0.08, "..." }
      },
      "promoted": true,
      "promoted_version": "v1.0.0"
    }
  ]
}
```

### GET /train/{train_job_id}

特定のジョブの詳細ステータスを返す（metrics, benchmark 含む）。

Response 例 (200): train_job_status スキーマをフル返却

## Dockerfile

- `Dockerfile.cpu`: PyTorch CPU wheel（デフォルト）
- `Dockerfile.gpu`: PyTorch CUDA wheel（GPU 環境向け）

## 実装状態

現在のバージョンはスタブ実装です。実装完了予定の機能：

🟦 **実装済み（テスト 5/5 Pass）**:
- `/train` エンドポイント: ジョブ作成・実行
- `/train` エンドポイント: ジョブ一覧
- `/train/{job_id}` エンドポイント: ジョブステータス詳細
- `TrainMetrics` モデル: epoch_losses, trial_errors_mm, benchmark_trial_ids
- `BenchmarkResultDetail` モデル: new_model vs current_model の比較

🟥 **将来実装**:
- 実際の PyTorch MLP 学習ロジック
- recipe-service からのデータ取得・前処理
- model-store への自動昇格ロジック

## テスト実行

```bash
mkdir -p data
docker build -f Dockerfile.test -t trainer-test .
docker run --rm trainer-test
# Expected: 5 tests passed
```

## 環境変数

| 変数 | デフォルト | 説明 |
|------|------|------|
| `RECIPE_SERVICE_URL` | `http://recipe-service:9002` | recipe-service のベース URL |
| `MODEL_STORE_URL` | `http://model-store:9009` | model-store のベース URL |
| `AI_CONTROLLER_URL` | `http://ai-controller:9006` | ベンチ評価用 ai-controller の URL |
| `SIMPLE_CONTROLLER_URL` | `http://simple-controller:9003` | ベンチ評価用 simple-controller の URL |
