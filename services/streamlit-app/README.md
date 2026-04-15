# streamlit-app

光学系シミュレーションの操作・可視化を行う Streamlit フロントエンドです。
Recipe Service のみと通信し、他サービスへは直接アクセスしません。

- Port: 8501
- 技術スタック: Python 3.11+, Streamlit, requests, plotly
- 依存サービス: recipe-service

## 実装済み画面

1. **実験管理**
- 実験一覧表示
- 新規実験作成（光学系パラメータ + ボルトモデル + カメラ設定）
- **エンジン種別選択**（KrakenOS / Simple）
  - KrakenOS: 精密な光線追跡（全パラメータ使用）
  - Simple: 高速ガウシアンモデル（必要最小限パラメータ）
- 実験選択を session_state に保持

2. **手動操作**
- 試行一覧表示・新規試行開始
- ステップ実行（coll_x, coll_y, torque_upper, torque_lower）
- 位置調整後 / ボルト締結後の比較表示
- 試行完了

3. **スイープ**
- ベースコマンド設定
- 対象パラメータ・範囲指定
- 結果テーブルとグラフ表示（中心座標、RMS、vignetting はレスポンスに含まれる場合表示）

4. **結果閲覧**
- 実験 -> 試行 -> ステップのドリルダウン
- ステップ一覧・詳細表示
- 試行内の推移グラフ表示
- 画像再取得 API の結果を base64 デコードして表示
- **警告表示**（Simple版で視野外スポット等の警告がある場合）

5. **制御ループ**
- Coming Soon（スタブ）

## ファイル構成

```text
services/streamlit-app/
├── Dockerfile
├── requirements.txt
├── README.md
└── app/
    ├── __init__.py
    ├── main.py
    ├── api_client.py
    ├── components/
    │   ├── __init__.py
    │   ├── inputs.py
    │   └── charts.py
    └── pages/
        ├── __init__.py
        ├── experiment.py
        ├── manual.py
        ├── sweep.py
        ├── results.py
        └── control.py
```

## 環境変数

| 変数 | デフォルト | 内容 |
|------|------------|------|
| RECIPE_SERVICE_URL | http://recipe-service:8002 | Recipe Service の URL |

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

## 動作確認（Docker コンテナのみ）

```bash
cd services/streamlit-app
docker build -t auto-opt-streamlit-app:test .
docker run -d --name auto-opt-streamlit-app-run -p 18501:8501 auto-opt-streamlit-app:test
curl -I http://localhost:18501
docker rm -f auto-opt-streamlit-app-run
```

現時点で streamlit-app 専用の automated test は未実装です。
