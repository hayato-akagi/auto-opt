# アーキテクチャ概要

## システム構成図

### 制御系

```mermaid
flowchart TD
    UI["Streamlit :9501\n可視化・操作UI"]
    CTL["制御器サービス群\nsimple-controller :9003\nai-controller :9006"]
    RCP["Recipe Service :9002\n管理・オーケストレーション・保存"]
    POS["Position Service :9004\nレンズXY位置調整"]
    BOLT["Bolt Service :9005\nボルト締結→ずれ計算"]
    SIM["Optics Sim :9001\n光線追跡 KrakenOS or Simple"]

    UI -->|指示・データ参照| CTL
    CTL -->|trial実行委譲| RCP
    RCP --> POS
    RCP --> BOLT
    RCP --> SIM
```

### 学習・モデル管理系

```mermaid
flowchart TD
    CORD["collection-orchestrator :9007\nデータ収集ジョブ管理（並列対応）"]
    CTL["制御器サービス群\nsimple-controller / ai-controller"]
    RCP["recipe-service\n既存"]
    TRN["trainer :9008\n学習・評価"]
    MS["model-store :9009\nモデル管理"]
    AIC["ai-controller :9006"]

    CORD -->|control/run 並列呼び出し| CTL
    CTL --> RCP
    TRN -->|ステップデータ収集| RCP
    TRN -->|モデル登録| MS
    MS -->|current 取得| AIC
```

## 座標系定義

```
        Y (Fast axis)
        ↑
        │
        │
  Z ────┘──→ X (Slow axis)
  (光軸)

  光の進行方向: +Z

  LD → [コリメートレンズ] →→→ [対物レンズ] → 観測面
                          Z軸 (光軸)
```

| 軸 | 方向 | 対応 |
|----|------|------|
| X | 水平（紙面左右） | Slow axis, `coll_x_shift`, `ld_emit_w` |
| Y | 垂直（紙面上下） | Fast axis, `coll_y_shift`, `ld_emit_h` |
| Z | 光軸方向 | `dist_ld_coll`, `dist_coll_obj`, `sensor_pos` |

## サービス一覧

| # | サービス | Port | 技術スタック | 責務 |
|---|---------|------|------------|------|
| 1a | optics-sim (KrakenOS) | 9001 | Python, KrakenOS, FastAPI | 精密光線追跡計算 |
| 1b | optics-sim (Simple) | 9011 | Python, NumPy, FastAPI | 高速ガウシアンモデル計算 |
| 2 | recipe-service | 9002 | Python, FastAPI | オーケストレーション・データ保存 |
| 3 | simple-controller | 9003 | Python, FastAPI | 比例制御ベースライン |
| 4 | position-service | 9004 | Python, FastAPI | レンズXY位置設定 |
| 5 | bolt-service | 9005 | Python, FastAPI | 初期位置→位置ずれ変換 |
| 6 | ai-controller | 9006 | Python, PyTorch, FastAPI | AI制御（MLP残差補正） |
| 7 | collection-orchestrator | 9007 | Python, FastAPI | 並列データ収集ジョブ管理 |
| 8 | trainer | 9008 | Python, PyTorch, FastAPI | モデル学習・評価・昇格 |
| 9 | model-store | 9009 | Python, FastAPI | モデルバージョン管理 |
| 10 | streamlit-app | 9501 | Python, Streamlit | UI・可視化 |

**注**: optics-simは2つのエンジンが選択可能：
- **KrakenOS版**（1a）: 厳密な光線追跡、全パラメータ使用
- **Simple版**（1b）: ガウシアンモデル、高速・省パラメータ

実験作成時に `engine_type` で選択。Recipe Service が自動的に適切なエンドポイントを呼び出す。

## 疎結合の原則

- 全サービス間通信は HTTP JSON API のみ
- 各サービスは他サービスの内部実装を知らない
- Optics Sim はレンズ位置がどう決まったかを知らない
- Bolt Service は光学系パラメータを知らない
- Position Service はボルトの存在を知らない
- Recipe Service だけが実行順序を知るオーケストレーター

## 典型的な実行フロー

### 手動実行（1ステップ）

```mermaid
sequenceDiagram
    participant UI as Streamlit
    participant R as Recipe Service
    participant P as Position Service
    participant S as Optics Sim
    participant B as Bolt Service

    UI->>R: XY=(0.02, -0.05) で実行
    R->>P: XY位置指定
    P-->>R: actual_x/y（初期位置 x0, y0）
    R->>S: 位置調整後パラメータで光線追跡
    S-->>R: 結果A（sim_after_position）
    R->>B: 初期位置(x0, y0)指定
    B-->>R: Δx, Δy（bolt_shift）
    R->>S: ボルト締結後パラメータで光線追跡
    S-->>R: 結果B（sim_after_bolt）
    R-->>UI: 結果A, 結果B
```

### 制御ループ

```mermaid
sequenceDiagram
    participant UI as Streamlit
    participant C as 制御器サービス
    participant R as Recipe Service

    UI->>C: POST /control/run（実験ID, config, 目標スポット）
    C->>R: POST /trials（mode=control_loop）
    C->>R: Step 0 実行（初期観測）
    R-->>C: 初期スポット位置
    loop 収束 or max_steps に達するまで
        C->>C: delta_coll_x/y を決定
        C->>R: POST /trials/{id}/steps
        Note over R: Position → Sim → Bolt → Sim
        R-->>C: sim_after_bolt（スポット位置）
        C->>C: 収束判定・緩め揺らぎ反映
    end
    C->>R: POST /trials/{id}/complete
    C-->>UI: 全試行履歴
```

制御器共通仕様は [05-controller.md](./05-controller.md) を参照。
初回実装サービスは [10-simple-controller.md](./10-simple-controller.md) を参照。
