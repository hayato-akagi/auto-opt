# adaptive-controller

ボルト締めによるスポット位置ズレを**トライアル実行中に推定して補正**する適応制御器サービス。

- Port: 8010
- 技術スタック: Python, FastAPI
- 依存サービス: recipe-service
- API仕様: simple-controller と同じインターフェース（差し替え可能）

---

## 概要

### simple-controller との違い

| | simple-controller | adaptive-controller |
|---|---|---|
| 補正方式 | 比例制御のみ | 比例制御 + bolt_shiftオンライン推定 |
| bolt_shift対応 | なし（毎ステップ誤差に反応） | 1ステップ目の観測から推定し以降に適用 |
| 学習 | しない | しない（ルールベース） |
| 収束ステップ | 環境に依存（2〜5ステップ） | 理論上1〜2ステップ（線形ボルトなら完全補正） |

---

## アルゴリズム

### Step 0（初期観測）

simple-controller と同様に初期コリメータ位置でシミュレーションを走らせ、初期スポット位置を取得する。

### Step 1（第1ステップ）

比例制御のみ（simple-controller と同じ）でコリメータを動かし、**ボルト締め後のスポット位置**を観測する。

```
bolt_shift_x = spot_after_bolt_x - spot_after_position_x
bolt_shift_y = spot_after_bolt_y - spot_after_position_y
```

この `bolt_shift` が「ボルト締めによって生じる固有のズレ」の初期推定値となる。

### Step 2 以降（適応補正）

比例制御の出力に bolt_shift の逆補正を加算する。

```
baseline_x  = (target_x - spot_pre_x) / spot_to_coll_scale_x
adaptive_x  = -bolt_shift_x / spot_to_coll_scale_x
final_x     = baseline_x + adaptive_x
```

また各ステップ後に観測値で bolt_shift 推定を更新する（指数移動平均）。

```
bolt_shift_x = alpha * new_obs_x + (1 - alpha) * bolt_shift_x  # alpha=0.5
```

---

## API

simple-controller と同じエンドポイント構成。`algorithm` フィールドに `"adaptive-controller"` を指定する。

### POST /control/run

単一トライアルの制御ループを実行する。

Request 例:

```jsonc
{
  "experiment_id": "exp_001",
  "algorithm": "adaptive-controller",
  "config": {
    "spot_to_coll_scale_x": 50.0,
    "spot_to_coll_scale_y": 50.0,
    "delta_clip_x": 0.05,
    "delta_clip_y": 0.05,
    "coll_x_min": -0.5,
    "coll_x_max": 0.5,
    "coll_y_min": -0.5,
    "coll_y_max": 0.5,
    "alpha": 0.5,
    "release_perturbation": {
      "std_x": 0.002,
      "std_y": 0.002
    }
  },
  "target": {
    "spot_center_x": 0.0,
    "spot_center_y": 0.0
  },
  "initial_coll": {
    "coll_x": 0.0,
    "coll_y": 0.0
  },
  "max_steps": 20,
  "tolerance": 0.001
}
```

Response 例:

```jsonc
{
  "trial_id": "trial_007",
  "algorithm": "adaptive-controller",
  "converged": true,
  "steps": 2,
  "bolt_shift_estimate_x": 0.0182,
  "bolt_shift_estimate_y": -0.0094,
  "final_spot_center_x": 0.0003,
  "final_spot_center_y": -0.0002,
  "final_spot_rms_radius": 0.004,
  "final_distance": 0.00036
}
```

`bolt_shift_estimate_x/y` はトライアル終了時点での推定値（デバッグ・分析用）。

### POST /control/step

ステートレスな1ステップ計算。`state.bolt_shift_estimate_x/y` で現在の推定値を渡す。

### GET /control/algorithms

```jsonc
{
  "algorithms": [
    {
      "name": "adaptive-controller",
      "description": "bolt_shiftをオンライン推定して補正する適応制御器",
      "config_schema": {"type": "object"}
    }
  ]
}
```

### GET /health

```jsonc
{"status": "ok", "service": "adaptive-controller", "version": "0.1.0"}
```

---

## 設定パラメータ

| パラメータ | デフォルト | 説明 |
|---|---|---|
| `spot_to_coll_scale_x` | 50.0 | スポット→コリメータ 変換スケール (x) |
| `spot_to_coll_scale_y` | 50.0 | スポット→コリメータ 変換スケール (y) |
| `delta_clip_x` | 0.05 | 1ステップあたり最大移動量 (x, mm) |
| `delta_clip_y` | 0.05 | 1ステップあたり最大移動量 (y, mm) |
| `coll_x_min/max` | -0.5 / 0.5 | コリメータ可動範囲 (x, mm) |
| `coll_y_min/max` | -0.5 / 0.5 | コリメータ可動範囲 (y, mm) |
| `alpha` | 0.5 | bolt_shift推定の更新率（指数移動平均）。1.0 = 最新観測のみ使用 |
| `release_perturbation.std_x/y` | 0.01 | ボルト緩め時の揺らぎ標準偏差 (mm) |

---

## 実装方針

- Step 0 はコリメータを初期位置に移動させるだけで bolt_shift 推定は行わない
- Step 1 で初めて bolt_shift を観測・推定し、Step 2 以降の補正に使う
- `alpha=1.0` にすると「最新の1観測だけを使う」モードになる
- bolt_shift 推定値は各トライアル内でのみ保持し、トライアル間では引き継がない（各環境は独立）
- ボルトモデルが非線形・位置依存の場合は alpha を小さくして平均化する

---

## 環境変数

| 変数 | デフォルト | 内容 |
|------|----------|------|
| `PORT` | 8010 | リッスンポート |
| `RECIPE_SERVICE_URL` | `http://recipe-service:8002` | Recipe Service の URL |

---

## 開発

```bash
cd services/adaptive-controller
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

---

## ファイル構成

```
adaptive-controller/
├── README.md
├── Dockerfile
├── requirements.txt
└── app/
    ├── __init__.py
    ├── clients.py     # recipe-service HTTP クライアント
    ├── config.py      # 環境変数設定
    ├── errors.py      # 例外クラス
    ├── logic.py       # bolt_shift推定ロジック（ステートレス）
    ├── main.py        # FastAPI アプリ定義
    ├── models.py      # リクエスト/レスポンス Pydantic モデル
    └── runner.py      # トライアルループ（bolt_shift推定状態を保持）
```
