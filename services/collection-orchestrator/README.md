# collection-orchestrator

DNN 学習用データ収集ジョブを管理するサービス。複数の実験条件・seed に対して制御ループを並列実行し、recipe-service にステップデータを蓄積する。

- **Port**: 9007
- **技術スタック**: Python, FastAPI
- **依存サービス**: recipe-service, simple-controller, ai-controller
- **仕様**: ../../docs/10-collection-orchestrator.md

⚠️ **実装状態**: 現在スタブ実装（ヘルスチェックのみ）。
並列データ収集ジョブの管理と実行は将来実装予定。

## API

### POST /jobs

コレクションジョブを作成し即時実行する。

Request 例:

```jsonc
{
  "algorithm": "simple-controller",
  "controller_config": {
    "spot_to_coll_scale_x": 50.0,
    "spot_to_coll_scale_y": 50.0,
    "delta_clip_x": 0.1,
    "delta_clip_y": 0.1,
    "coll_x_min": -0.5,
    "coll_x_max": 0.5,
    "coll_y_min": -0.5,
    "coll_y_max": 0.5
  },
  "target": { "spot_center_x": 0.0, "spot_center_y": 0.0 },
  "initial_coll": { "coll_x": 0.0, "coll_y": 0.0 },
  "max_steps": 10,
  "tolerance": 0.05,
  "tasks": [
    { "experiment_id": "exp_001", "seeds": [1, 2, 3, 4, 5] },
    { "experiment_id": "exp_002", "seeds": [1, 2, 3, 4, 5] }
  ],
  "max_workers": 4
}
```

Response 例:

```jsonc
{
  "job_id": "cjob_20260510_120000_0001",
  "status": "running",
  "total_tasks": 10,
  "created_at": "2026-05-10T12:00:00Z"
}
```

### GET /jobs/{job_id}

ジョブの進捗・結果を返す。

### GET /jobs

ジョブ一覧を返す。`?status=completed` でフィルタ可能。

### POST /jobs/from-sweep

bolt model パラメータにグリッドを指定し、実験作成からジョブ投入まで一括実行する。

## 環境変数

| 変数 | デフォルト | 説明 |
|------|------|------|
| `RECIPE_SERVICE_URL` | `http://recipe-service:9002` | recipe-service のベース URL |
| `SIMPLE_CONTROLLER_URL` | `http://simple-controller:9003` | simple-controller のベース URL |
| `AI_CONTROLLER_URL` | `http://ai-controller:9006` | ai-controller のベース URL |
| `MAX_WORKERS` | `4` | デフォルトの同時実行タスク数 |
