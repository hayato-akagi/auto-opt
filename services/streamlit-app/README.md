# streamlit-app

光学系シミュレーションの操作・可視化を行う Streamlit フロントエンドです。
Recipe Service のみと通信し、他サービスへは直接アクセスしません。

- Port: 8501
- 技術スタック: Python 3.11+, Streamlit, requests, plotly
- 依存サービス: recipe-service

## 実装済み画面

### シミュレーション・制御系

1. **実験管理**
   - 実験一覧表示
   - 新規実験作成（光学系パラメータ + ボルトモデル + カメラ設定）
   - **エンジン種別選択**（KrakenOS / Simple）
     - KrakenOS: 精密な光線追跡（全パラメータ使用）
     - Simple: 高速ガウシアンモデル（必要最小限パラメータ）
   - 実験選択を session_state に保持

2. **手動操作**
   - 試行一覧表示・新規試行開始
   - ステップ実行（coll_x, coll_y）
   - 位置調整後 / ボルト締結後の比較表示
   - 試行完了

3. **スイープ**
   - ベースコマンド設定
   - 対象パラメータ・範囲指定
   - 結果テーブルとグラフ表示

4. **結果閲覧**
   - 実験 → 試行 → ステップのドリルダウン
   - ステップ一覧・詳細表示
   - 試行内の推移グラフ表示
   - 画像再取得 API の結果を base64 デコードして表示

### AI 学習・制御系（🚧 実装予定）

5. **AI 制御**（ai_control ページ）
   - ai-controller でのプロトタイプ実行（制御ループ）
   - モデルバージョン選択
   - ベースライン vs AI 制御の比較実行
   - 制御ログ表示（baseline_delta_x/y, dnn_residual_x/y, safety_triggered）

6. **データ収集**（collection ページ）
   - collection-orchestrator でのジョブ管理
   - 複数実験・複数 seed の並列実行設定
   - ジョブ進行状況表示（実行中 / 完了 / 失敗）
   - 収集統計表示（総ステップ数、成功率）

7. **モデル学習**（training ページ）
   - trainer でのジョブ管理
   - 学習パラメータ設定（epochs, batch_size, experiment_ids）
   - 学習進捗表示（epoch_losses のグラフ）
   - ベンチマーク結果表示（new_model vs current_model の誤差比較）
   - 自動昇格結果表示（promoted: true → promoted_version）

8. **モデル管理**（model_store ページ）
   - モデルバージョン一覧（current / candidate / archived）
   - 各バージョンのメタ情報・ベンチマーク結果表示
   - 手動昇格機能（candidate → current）
   - モデル削除（archived のみ）

## ファイル構成

```text
services/streamlit-app/
├── Dockerfile
├── requirements.txt
├── README.md
└── app/
    ├── __init__.py
    ├── main.py
    ├── api_client.py           # Recipe Service + Trainer + Model Store + AI Controller クライアント
    ├── components/
    │   ├── __init__.py
    │   ├── inputs.py           # フォーム入力コンポーネント
    │   └── charts.py           # グラフ描画（Plotly）
    └── pages/
        ├── __init__.py
        ├── experiment.py       # 実験管理（実装済み）
        ├── manual.py           # 手動操作（実装済み）
        ├── sweep.py            # パラメータスイープ（実装済み）
        ├── results.py          # 結果閲覧（実装済み）
        ├── ai_control.py       # AI制御（🚧 実装予定）
        ├── collection.py       # データ収集（🚧 実装予定）
        ├── training.py         # モデル学習（🚧 実装予定）
        └── model_store.py      # モデル管理（🚧 実装予定）
```

## API 通信

`api_client.py` は以下のバックエンドサービスと通信します：

### Recipe Service（実装済み）

```python
client.get_experiments()                     # 全実験取得
client.create_experiment(...)                # 新規実験作成
client.get_trials(experiment_id)             # 試行一覧
client.create_trial(experiment_id, mode)     # 新規試行開始
client.execute_step(...)                     # ステップ実行（+ ai_step_log 対応）
client.get_step_images(...)                  # 画像再取得
client.complete_trial(...)                   # 試行完了
client.sweep(...)                            # パラメータスイープ
```

### Trainer（🚧 実装予定）

```python
client.start_training(experiment_ids, ...)   # 学習ジョブ開始
client.get_training_jobs()                   # ジョブ一覧
client.get_training_job_status(job_id)       # ジョブ詳細（metrics + benchmark 含む）
```

### Model Store（🚧 実装予定）

```python
client.get_models()                          # モデル一覧
client.get_model(version)                    # モデルメタ取得
client.promote_model(version)                # モデル昇格
```

### AI Controller（🚧 実装予定）

```python
client.run_ai_control(...)                   # AI制御ループ実行
```

## 環境変数

| 変数 | デフォルト | 内容 |
|------|------------|------|
| `RECIPE_SERVICE_URL` | `http://recipe-service:8002` | Recipe Service の URL |
| `TRAINER_URL` | `http://trainer:9008` | Trainer サービスの URL（🚧） |
| `MODEL_STORE_URL` | `http://model-store:9009` | Model Store サービスの URL（🚧） |
| `AI_CONTROLLER_URL` | `http://ai-controller:9006` | AI Controller サービスの URL（🚧） |
| `COLLECTION_ORCHESTRATOR_URL` | `http://collection-orchestrator:9007` | Collection Orchestrator サービスの URL（🚧） |

## ローカル実行

```bash
cd services/streamlit-app
pip install -r requirements.txt
streamlit run app/main.py --server.port 8501
```

## Docker 実行

```bash
cd services/streamlit-app
docker build -t auto-opt-streamlit-app:test .
docker run --rm -p 18501:8501 \
  -e RECIPE_SERVICE_URL=http://host.docker.internal:18002 \
  auto-opt-streamlit-app:test
```

Recipe Service が未起動でも UI 自体は表示されます。
その場合、API 実行時に「Recipe Service に接続できません」を画面表示します。

## 実装状態

### ✅ 実装済み（recipe-service ベース）

- **実験管理**ページ: 実験作成・一覧表示、エンジン種別選択
- **手動操作**ページ: ステップ実行、位置調整・ボルト締結フロー
- **スイープ**ページ: パラメータスイープ実行、結果表示
- **結果閲覧**ページ: ドリルダウン、グラフ表示

### 🚧 実装予定（trainer/model-store/ai-controller/collection-orchestrator ベース）

- **AI制御**ページ: ai-controller 連携、DNN 補正制御の可視化
- **データ収集**ページ: collection-orchestrator でのジョブ管理
- **モデル学習**ページ: trainer での学習進捗・ベンチマーク結果表示
- **モデル管理**ページ: model-store でのバージョン管理・昇格
- `api_client.py`: Trainer/Model Store/AI Controller/Collection Orchestrator 統合

### 現在のメインページ（main.py）の構成

```
┌─ Streamlit アプリケーション ─────────────────────┐
│                                                   │
│  サイドバー:                                       │
│  ├─ 実験管理 -> pages/experiment.py               │
│  ├─ 手動操作 -> pages/manual.py                   │
│  ├─ スイープ -> pages/sweep.py                    │
│  ├─ 結果閲覧 -> pages/results.py                  │
│  ├─ AI制御  -> pages/ai_control.py（🚧）         │
│  ├─ データ収集 -> pages/collection.py（🚧）      │
│  ├─ モデル学習 -> pages/training.py（🚧）        │
│  └─ モデル管理 -> pages/model_store.py（🚧）     │
│                                                   │
│  メインエリア: 選択ページを表示                     │
└─────────────────────────────────────────────────┘
```

現時点で streamlit-app 専用の automated test は未実装です。
