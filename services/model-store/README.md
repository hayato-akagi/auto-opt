# model-store

学習済みモデルのバージョン管理サービス。モデルファイル（`.pt`）と設定メタ情報を保存し、`current` / `candidate` / `archived` の状態を管理する。

- **Port**: 9009
- **技術スタック**: Python, FastAPI
- **依存サービス**: なし（他サービスから依存される）
- **仕様**: ../../docs/12-model-store.md

## API

### GET /health

ヘルスチェック。

### POST /models

新しいモデルを登録する（trainer が呼び出す）。

Request 例:

```jsonc
{
  "version": "v1",
  "model_type": "mlp",
  "status": "candidate",
  "benchmark_metrics": { "median_final_error_mm": 0.05, "..." },
  "benchmark_trial_ids": ["trial_001", "trial_002"],
  "benchmark_experiment_ids": ["exp_001"],
  "train_job_id": "train_job_000001",
  "created_at": "2026-05-10T12:00:00Z"
}
```

Response (200): リクエストと同じボディを返却（確認応答）。

### GET /models

全モデル一覧をメタ情報付きで返す。

Response 例 (200):

```jsonc
{
  "models": [
    { "version": "v1", "model_type": "mlp", "status": "archived", "..." },
    { "version": "v2", "model_type": "mlp", "status": "current", "..." }
  ],
  "current_version": "v2"
}
```

### GET /models/{version}

指定バージョンのメタ情報を返す。

Response 例 (200):

```jsonc
{
  "version": "v2",
  "model_type": "mlp",
  "status": "current",
  "benchmark_metrics": { "..." },
  "benchmark_trial_ids": ["trial_001", "trial_002"],
  "benchmark_experiment_ids": ["exp_001"],
  "train_job_id": "train_job_000001",
  "created_at": "2026-05-10T13:00:00Z",
  "promoted_at": "2026-05-10T13:05:00Z"
}
```

### POST /models/{version}/promote

モデルを `candidate` から `current` に昇格。前の `current` は `archived` になる。

Request:

```jsonc
{
  "version": "v2"
}
```

Response (200):

```jsonc
{
  "version": "v2",
  "new_status": "current",
  "promoted_at": "2026-05-10T13:05:00Z"
}
```

## モデル状態遷移

```
登録 → candidate → (昇格) → current → (次が昇格) → archived
```

初期バージョン `v0` は `model_type = baseline_only` として扱う（ファイルなし）。

## 実装状態

現在のバージョンはスタブ実装です。実装完了予定の機能：

🟦 **実装済み（テスト 8/8 Pass）**:
- `POST /models`: モデル登録
- `GET /models`: 全モデル一覧
- `GET /models/{version}`: 特定版取得
- `POST /models/{version}/promote`: モデル昇格
- メモリストレージでモデル管理

🟥 **将来実装**:
- Docker Volume への `.pt` ファイル永続化
- ファイルベースのメタデータ保存
- `GET /models/{version}/file`: バイナリ取得エンドポイント
- ai-controller 登場後に model reload 機能

## テスト実行

```bash
mkdir -p data
docker build -f Dockerfile.test -t model-store-test .
docker run --rm model-store-test
# Expected: 8 tests passed
```
  v2/model.pt, meta.json
  ...
```

## 環境変数

| 変数 | デフォルト | 説明 |
|------|------|------|
| `MODEL_DIR` | `/models` | モデルファイル保存先ディレクトリ |
