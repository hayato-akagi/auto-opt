# auto-opt

レーザーダイオード（LD）、コリメートレンズ、対物レンズで構成される光学系の位置調整・ボルト締結シミュレーション。マイクロサービスアーキテクチャで構成。

## システム構成図

```
┌──────────────┐
│  Streamlit   │  :8501  可視化・操作UI
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Recipe     │  :8002  管理・オーケストレーション・保存
│   Service    │
└──┬──┬────┬───┘
   │  │    │
   │  │    ▼
   │  │ ┌──────────┐
   │  │ │ Position │  :8004  レンズ位置調整
   │  │ └──────────┘
   │  ▼
   │ ┌──────────┐
   │ │  Bolt    │  :8005  ボルト締結→ずれ計算
   │ └──────────┘
   ▼
┌──────────────┐
│  Optics Sim  │  :8001  光線追跡 (KrakenOS)
└──────────────┘
```

Controller (:8003) は将来追加。

## サービス一覧

| サービス | Port | 責務 |
|---------|------|------|
| optics-sim | 8001 | KrakenOS 光線追跡計算 |
| recipe-service | 8002 | オーケストレーション・データ保存 |
| position-service | 8004 | レンズXY位置設定 |
| bolt-service | 8005 | トルク→位置ずれ変換 |
| streamlit-app | 8501 | UI・可視化 |
| controller (将来) | 8003 | PID制御等 |

## クイックスタート

```bash
docker-compose up -d
```

Streamlit UI: http://localhost:8501

## ディレクトリ構成

```
auto-opt/
├── docker-compose.yml
├── README.md
├── docs/                    # 設計ドキュメント
└── services/
    ├── optics-sim/          # 光線追跡サービス
    ├── recipe-service/      # 管理サービス
    ├── position-service/    # 位置調整サービス
    ├── bolt-service/        # ボルト締結サービス
    ├── controller/          # 制御器（将来）
    └── streamlit-app/       # 可視化UI
```

## ドキュメント

| ファイル | 内容 |
|---------|------|
| docs/00-architecture.md | 全体構成・座標系・実行フロー |
| docs/01-optics-sim.md | 光学シミュレーション API |
| docs/02-recipe-service.md | 管理サービス API |
| docs/03-position-service.md | 位置調整サービス API |
| docs/04-bolt-service.md | ボルト締結サービス API |
| docs/05-controller.md | 制御器 API（将来） |
| docs/06-streamlit-app.md | 可視化 UI 仕様 |
| docs/07-data-format.md | データ保存形式 |
| docs/08-docker-compose.md | Docker 構成 |
