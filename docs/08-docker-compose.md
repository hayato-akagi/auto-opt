# Docker Compose 構成

## docker-compose.yml

```yaml
version: "3.9"

services:
  optics-sim:
    build: ./services/optics-sim
    ports:
      - "8001:8001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  recipe-service:
    build: ./services/recipe-service
    ports:
      - "8002:8002"
    volumes:
      - results-data:/app/data
    environment:
      - OPTICS_SIM_URL=http://optics-sim:8001
      - POSITION_SERVICE_URL=http://position-service:8004
      - BOLT_SERVICE_URL=http://bolt-service:8005
    depends_on:
      optics-sim:
        condition: service_healthy
      position-service:
        condition: service_healthy
      bolt-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  position-service:
    build: ./services/position-service
    ports:
      - "8004:8004"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8004/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  bolt-service:
    build: ./services/bolt-service
    ports:
      - "8005:8005"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8005/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  streamlit-app:
    build: ./services/streamlit-app
    ports:
      - "8501:8501"
    environment:
      - RECIPE_SERVICE_URL=http://recipe-service:8002
    depends_on:
      recipe-service:
        condition: service_healthy
    volumes:
      - results-data:/app/data:ro

  # simple-controller:             # 将来追加
  #   build: ./services/simple-controller
  #   ports:
  #     - "8003:8003"
  #   environment:
  #     - RECIPE_SERVICE_URL=http://recipe-service:8002
  #   depends_on:
  #     recipe-service:
  #       condition: service_healthy

volumes:
  results-data:
```

## ディレクトリ構成

```
auto-opt/
├── docker-compose.yml
├── docs/
│   ├── 00-architecture.md
│   ├── 01-optics-sim.md
│   ├── 02-recipe-service.md
│   ├── 03-position-service.md
│   ├── 04-bolt-service.md
│   ├── 05-controller.md
│   ├── 06-streamlit-app.md
│   ├── 07-data-format.md
│   └── 08-docker-compose.md
└── services/
    ├── optics-sim/
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── app/
    │       └── main.py
    ├── recipe-service/
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── app/
    │       └── main.py
    ├── position-service/
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── app/
    │       └── main.py
    ├── bolt-service/
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── app/
    │       └── main.py
    └── streamlit-app/
        ├── Dockerfile
        ├── requirements.txt
        └── app/
            └── main.py
```

## サービス間通信

| 呼び出し元 | 呼び出し先 | URL (docker内部) |
|-----------|-----------|-----------------|
| streamlit-app | recipe-service | http://recipe-service:8002 |
| recipe-service | optics-sim | http://optics-sim:8001 |
| recipe-service | position-service | http://position-service:8004 |
| recipe-service | bolt-service | http://bolt-service:8005 |
| simple-controller (将来) | recipe-service | http://recipe-service:8002 |

## 新しいサービス（AI学習パイプライン）

`docker-compose.yml` では以下の新しいサービスが追加される予定です：

### trainer (ポート 9008)

```yaml
trainer:
  build: ./services/trainer
  ports:
    - "9008:8000"
  environment:
    - RECIPE_SERVICE_URL=http://recipe-service:8002
    - MODEL_STORE_URL=http://model-store:9009
  depends_on:
    - recipe-service
    - model-store
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
```

### model-store (ポート 9009)

```yaml
model-store:
  build: ./services/model-store
  ports:
    - "9009:8000"
  volumes:
    - models-data:/app/data
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
```

### ai-controller (ポート 9006)

CPU版（学習GPU編集フェーズ）または GPU版（推論フェーズ）を選択：

```yaml
ai-controller:
  build:
    context: ./services/ai-controller
    dockerfile: Dockerfile.cpu  # または Dockerfile.gpu
  ports:
    - "9006:8000"
  environment:
    - MODEL_STORE_URL=http://model-store:9009
  depends_on:
    - model-store
```

### collection-orchestrator (ポート 9007)

```yaml
collection-orchestrator:
  build: ./services/collection-orchestrator
  ports:
    - "9007:8000"
  environment:
    - RECIPE_SERVICE_URL=http://recipe-service:8002
    - SIMPLE_CONTROLLER_URL=http://simple-controller:9003
  depends_on:
    - recipe-service
```

### ボリューム追加

```yaml
volumes:
  results-data:
  models-data:       # モデルストアの永続化
```

```bash
# 全サービス起動
docker-compose up -d

# ログ確認
docker-compose logs -f

# 特定サービスのみ再ビルド
docker-compose build optics-sim
docker-compose up -d optics-sim

# 全サービス停止
docker-compose down

# データも含めて完全削除
docker-compose down -v
```

## ポート一覧

| Port | サービス | 用途 |
|------|---------|------|
| 8001 | optics-sim | 光線追跡 API |
| 8002 | recipe-service | 実験・試行管理 API |
| 8003 | simple-controller | シンプル制御器 API |
| 8004 | position-service | 位置調整 API |
| 8005 | bolt-service | ボルト締結 API |
| 9003 | simple-controller（ポートB） | 制御ループ実行 API |
| 9006 | ai-controller | AI制御器 API |
| 9007 | collection-orchestrator | データ収集 API |
| 9008 | trainer | モデル学習 API |
| 9009 | model-store | モデル管理 API |
| 8501 | streamlit-app | Web UI |
