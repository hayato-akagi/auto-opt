# lstm-controller

LSTM を使ったシーケンス適応型 AI 制御器サービス。
ai-controller（MLP）と同じ API インターフェースを持ち、**試行内で隠れ状態を更新しながらボルト環境を動的に同定する**点が異なる。

- **Port**: 9012
- **技術スタック**: Python, FastAPI, PyTorch
- **依存サービス**: recipe-service, model-store
- **対応**: MLP との差し替え可能（同一 API）

---

## MLP との本質的な違い

### MLP（ai-controller）

```
Step N:  [step(N-3), step(N-2), step(N-1), current_pos]  ──→  MLP  ──→  bolt_shift
                  └─── 固定幅の入力ベクトル（平坦化） ───┘
```

- 各ステップを独立に予測する
- 「過去 N ステップ」を機械的に結合したベクトルを入力とする
- 環境を識別する能力は暗黙的・弱い

### LSTM（lstm-controller）

```
Step 1:  features_1  ──→  LSTM  ──→  h₁  ──→  bolt_shift_1
                              ↓ h₁ を引き継ぐ
Step 2:  features_2  ──→  LSTM  ──→  h₂  ──→  bolt_shift_2
                              ↓ h₂ を引き継ぐ
Step 3:  features_3  ──→  LSTM  ──→  h₃  ──→  bolt_shift_3
```

- 1 ステップずつ処理し、隠れ状態（h, c）が試行内で蓄積される
- 初期ステップ（h=0）は粗い補正、後続ステップは h に蓄積された環境情報を使って精密化
- 「どう観測すれば環境を識別できるか」を BPTT で学習する

---

## アーキテクチャ

### 入力（1ステップ分: 8次元）

| 要素 | 次元数 | 内容 |
|---|---|---|
| 前ステップの観測 | 6 | spot_before(x,y), delta(x,y), spot_after(x,y) |
| 現在のスポット位置 | 2 | current_x, current_y |
| **合計** | **8** | ※ MLP の 62 次元（ゼロパディング込み）より小さい |

### ネットワーク

```
features_t (8-dim)
    ↓
LSTM(input=8, hidden=hidden_dim, num_layers=2)
    ↓  h_t, c_t（次ステップに引き継ぐ）
Linear(hidden_dim → 2)
    ↓
bolt_shift_pred (delta_x, delta_y)
```

### 隠れ状態の管理

| タイミング | 操作 |
|---|---|
| 試行開始時 | h=0, c=0 に初期化 |
| 各ステップ実行後 | h_t, c_t を更新・保持 |
| 試行終了時 | 破棄（次試行は独立） |
| 試行間の引き継ぎ | なし（within-trial のみ） |

---

## 汎化の仕組み

学習フェーズで多様な bolt_distribution（x0_bias, a_x 等の幅を広く設定）の環境を大量に経験させることで、**推論時に未知の環境に対しても早期ステップから環境を識別して適応できる**ようになる。

```
学習時: 環境 A, B, C, D, ... (多様)  → LSTM が「観測→環境識別」のパターンを学習
推論時: 未知の環境 Z
    Step 1: h₁ に「このボルトは右ズレ傾向」が書き込まれる
    Step 2: h₁ を参照して補正量を精密化
    Step 3: ほぼ収束
```

これは Rapid Motor Adaptation（RMA）や In-context Learning と同じ原理。

---

## 学習方法（trainer 側の変更点）

| 項目 | MLP | LSTM |
|---|---|---|
| 学習単位 | **1 ステップ** = 1 サンプル | **1 試行** = 1 シーケンス |
| 損失 | MSE(pred, label) | 各ステップの MSE 平均（BPTT） |
| データローダー | TensorDataset（平坦） | 試行ごとにシーケンスをバッチ化 |
| モデル保存 | hidden_dim を記録 | hidden_dim, num_layers, input_dim を記録 |

---

## API

ai-controller と完全に同じインターフェース。`algorithm` フィールドに `"lstm-controller"` を指定する。

### POST /control/run

```jsonc
{
  "experiment_id": "exp_001",
  "algorithm": "lstm-controller",
  "config": {
    "model_type": "lstm",
    "model_version": null,
    "spot_to_coll_scale_x": 50.0,
    "spot_to_coll_scale_y": 50.0,
    "delta_clip_x": 0.05,
    "delta_clip_y": 0.05,
    "coll_x_min": -0.5,
    "coll_x_max": 0.5,
    "coll_y_min": -0.5,
    "coll_y_max": 0.5,
    "safety_threshold": 0.5,
    "safety_bias": 0.01,
    "release_perturbation": {"std_x": 0.01, "std_y": 0.01}
  },
  "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
  "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
  "max_steps": 10,
  "tolerance": 0.001,
  "random_seed": 42
}
```

### POST /model/reload
### GET /model/status
### GET /health

---

## ai-controller（MLP）との共存

両サービスを同時に起動し、パイプラインの Gen0 コントローラーや実験設定から切り替えて比較できる。

| 設定 | ai-controller | lstm-controller |
|---|---|---|
| Port | 9006 | 9012 |
| model_type | `mlp` | `lstm` |
| Gen N+ controller | `ai-controller` | `lstm-controller` |
| 試行単位の学習 | ✅ | ✅（trainer 拡張後）|

---

## ファイル構成

```
lstm-controller/
├── README.md
├── Dockerfile.cpu
├── requirements.txt
└── app/
    ├── __init__.py
    ├── clients.py     # recipe-service / model-store HTTP クライアント
    ├── config.py      # 環境変数設定
    ├── errors.py      # 例外クラス
    ├── logic.py       # 1ステップの推論計算（ステートレス）
    ├── main.py        # FastAPI アプリ定義
    ├── model.py       # LSTM モデル定義 + ModelManager（隠れ状態管理）
    ├── models.py      # Pydantic リクエスト/レスポンスモデル
    └── runner.py      # 試行ループ（h_t を step 間で引き継ぐ）
```

trainer 側には `BoltShiftLSTM` クラスと LSTM 用シーケンスデータローダーを追加する。

---

## 環境変数

| 変数 | デフォルト | 説明 |
|---|---|---|
| `RECIPE_SERVICE_URL` | `http://recipe-service:8002` | recipe-service の URL |
| `MODEL_STORE_URL` | `http://model-store:9009` | model-store の URL |

---

## 開発

```bash
cd services/lstm-controller
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 9012 --reload
```
