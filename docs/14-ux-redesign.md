# Streamlit UI リニューアル仕様書

## プロジェクト概要

光学アライメント自動最適化システム（auto-opt）の Streamlit UI をリニューアルする。
目的は「さまざまな学習戦略を試して、どの戦略が最も良い AI 制御モデルを生むか」を比較できる UI を作ること。

### マイクロサービス構成

| サービス | ポート（コンテナ内） | 役割 |
|---|---|---|
| recipe-service | 8002 | 実験・トライアル・ステップのデータ保存・オーケストレーション |
| simple-controller | 8003 | ルールベース制御器 |
| optics-sim (simple) | 9011 | 高速ガウシアン光学シミュレーター |
| bolt-service | 9005 | ボルト締結→位置ずれ計算 |
| position-service | 9004 | レンズXY位置制御 |
| ai-controller | 9006 | AI制御器（学習済みMLPモデルを使用） |
| collection-orchestrator | 8007 | データ収集ジョブ管理（並列実行対応） |
| trainer | 9008 | モデル学習・評価・昇格判定 |
| model-store | 9009 | モデルバージョン管理 |
| streamlit-app | 9501 | UI（今回書き換える対象） |

---

## タスク概要

`services/streamlit-app/` 以下を書き換える。

### 変更するファイル

- `app/main.py` — ナビゲーションを 4 画面に書き換え
- `app/api_client.py` — メソッドを 1 つ追加（後述）
- `app/pages/` 以下の**全ファイルを削除**し、以下 4 ファイルを新規作成:
  - `app/pages/sim_validation.py`
  - `app/pages/benchmark.py`
  - `app/pages/learning_run.py`
  - `app/pages/comparison.py`

### 変更しないファイル

- `app/components/charts.py` — そのまま使う
- `app/components/inputs.py` — そのまま使う
- `Dockerfile`, `requirements.txt`, `docker-compose.yml` — 変更不要

---

## 設計決定事項（確定済み）

- **4 画面構成**: シミュレーター検証 / ベンチマーク設定 / 学習ラン / 結果比較
- **ベンチマーク** = ルールベース制御器（simple-controller）を難しい条件で実行した結果。全学習ランの「超えるべきバー」として固定される
- **学習ラン** = (bolt/noise の範囲指定 + モデル設定) を入力すると、データ収集→学習→評価を全世代自動で実行するパイプライン
- **データの再利用は不可**: Gen 1 以降のデータは各ランで使うモデルが異なるため、ランをまたいでデータを共有しない
- **並列実行**: 1 ラン内の収集は collection-orchestrator が並列実行する。複数のランは順番に実行（キュー方式）
- **世代進行は全自動**: ユーザーの手動操作なしに全世代を完走する
- **学習データは世代をまたいで累積**: Gen N のトレーニングは Gen 0〜N の全実験データを使う
- **光学エンジン**: `engine_type = "Simple"` を使う（大文字 S。API の Literal 定義に合わせる）

---

## 画面 1: 🔬 シミュレーター検証

事前確認用ユーティリティ。既存ページ（`manual.py`, `sweep.py`）の機能を 3 タブに統合する。

### タブ構成

**タブ1: 手動操作**
- 実験をセレクトボックスで選択（`GET /experiments`）
- `coll_x`, `coll_y` をスライダーで指定
- 「1ステップ実行」ボタン → `POST /experiments/{id}/trials` でトライアル作成 → `POST /experiments/{id}/trials/{tid}/steps` でステップ実行
- 結果（スポット座標、誤差）を表示

**タブ2: パラメータスイープ**
- 実験選択
- `coll_x` / `coll_y` の範囲・ステップ数を指定
- 「スイープ実行」ボタン → `POST /recipes/sweep` を呼ぶ
- 結果をヒートマップで表示

**タブ3: ボルト応答確認**
- bolt_model パラメータ（x0_bias_x, a_x, noise_ratio など）をスライダーで設定
- 実験作成 → 手動ステップ実行でボルト締結前後のスポット座標変化を可視化

---

## 画面 2: 🎯 ベンチマーク設定

一回だけ設定する。全学習ランの比較基準を定義する。

### レイアウト

```
┌─────────────────────────────────────────────┐
│ ベンチマーク設定（一回限り）                   │
│                                             │
│ 難しい条件の範囲を指定                        │
│   x0_bias 絶対値の最大: [0.15]              │
│   a_x 絶対値の最大:     [0.05]              │
│   noise_ratio 最小:     [0.05]              │
│   noise_ratio 最大:     [0.10]              │
│   生成ケース数:          [20]               │
│   seeds/環境:            [5]                │
│   乱数シード（固定）:    [42]               │
│                                             │
│   [ベンチ環境を生成してルールベース実行]       │
├─────────────────────────────────────────────┤
│ ✅ 設定済み                                  │
│                                             │
│   収束率:   43%                             │
│   中央誤差: 0.089 mm                        │
│   P95誤差:  0.142 mm                        │
│                                             │
│   ← 全学習ランで共通の「超えるべきバー」      │
│   [再設定する（全比較結果が無効になります）]  │
└─────────────────────────────────────────────┘
```

### 処理フロー

1. 指定した範囲から `num_cases` 個の実験を乱数生成（固定 seed）して `POST /experiments` で作成
2. `POST /jobs` (collection-orchestrator) で simple-controller を使って全実験を実行
3. ジョブ完了を `GET /jobs/{job_id}` でポーリング（`"completed"`, `"failed"`, `"partial"` のいずれかで完了判定）
4. 結果集計: 全 trial の最終ステップのスポット誤差を recipe-service から取得し、収束率・中央値・P95 を算出
5. 結果を `st.session_state["benchmark_result"]` に保存

### 乱数実験生成ロジック

```python
import random

ZERO_BOLT_UNIT = {
    "x0_bias_x": 0.0,
    "x0_bias_y": 0.0,
    "a_x": 0.0,
    "b_x": 1.0,
    "a_y": 0.0,
    "b_y": 1.0,
    "noise_ratio_min_x": 0.01,
    "noise_ratio_max_x": 0.05,
    "noise_ratio_min_y": 0.01,
    "noise_ratio_max_y": 0.05,
}


def generate_random_bolt_model(
    x0_bias_abs_max: float,
    a_abs_max: float,
    noise_min: float,
    noise_max: float,
    rng: random.Random,
) -> dict:
    """API の BoltModel 形式（upper/lower ネスト）で返す。
    upper にランダムパラメータ、lower はニュートラル固定。"""
    nr_min = rng.uniform(0.0, noise_min)
    nr_max = rng.uniform(noise_min, noise_max)
    upper = {
        "x0_bias_x": rng.uniform(-x0_bias_abs_max, x0_bias_abs_max),
        "x0_bias_y": rng.uniform(-x0_bias_abs_max, x0_bias_abs_max),
        "a_x": rng.uniform(-a_abs_max, a_abs_max),
        "b_x": 1.0,
        "a_y": rng.uniform(-a_abs_max, a_abs_max),
        "b_y": 1.0,
        "noise_ratio_min_x": nr_min,
        "noise_ratio_max_x": nr_max,
        "noise_ratio_min_y": nr_min,
        "noise_ratio_max_y": nr_max,
    }
    return {"upper": upper, "lower": ZERO_BOLT_UNIT}
```

### 実験作成ペイロード（optical_system ネスト形式）

```python
DEFAULT_OPTICAL_SYSTEM = {
    "wavelength": 780.0,
    "ld_tilt": 0.0,
    "ld_div_fast": 25.0,
    "ld_div_slow": 8.0,
    "ld_div_fast_err": 0.0,
    "ld_div_slow_err": 0.0,
    "ld_emit_w": 3.0,
    "ld_emit_h": 1.0,
    "num_rays": 5000,
    "coll_r1": -3.5,
    "coll_r2": -15.0,
    "coll_k1": -1.0,
    "coll_k2": 0.0,
    "coll_t": 2.0,
    "coll_n": 1.517,
    "dist_ld_coll": 4.0,
    "obj_f": 4.0,
    "dist_coll_obj": 50.0,
    "sensor_pos": 4.0,
}


def build_experiment_payload(name: str, bolt_model: dict) -> dict:
    """POST /experiments のペイロードを構築する。"""
    return {
        "name": name,
        "engine_type": "Simple",
        "optical_system": DEFAULT_OPTICAL_SYSTEM,
        "bolt_model": bolt_model,
    }
```

### ベンチマーク指標の集計ロジック

collection job 完了後、各 trial の最終スポット誤差を取得して集計する:

```python
import math


def compute_benchmark_metrics(
    task_results: list[dict],
    api_client: RecipeApiClient,
    target_x: float = 0.0,
    target_y: float = 0.0,
    tolerance: float = 0.05,
) -> dict:
    """task_results から各 trial の最終誤差を取得して指標を算出する。"""
    errors = []
    converged_count = 0
    total_count = 0

    for task in task_results:
        if task.get("error"):
            continue
        trial_id = task.get("trial_id")
        experiment_id = task.get("experiment_id")
        if not trial_id or not experiment_id:
            continue
        total_count += 1

        steps = api_client.list_steps(experiment_id, trial_id)
        if not steps:
            continue
        last_step = steps[-1]
        sim = last_step.get("sim_after_bolt", {})
        spot_x = sim.get("spot_center_x", 0.0)
        spot_y = sim.get("spot_center_y", 0.0)
        err = math.sqrt((spot_x - target_x) ** 2 + (spot_y - target_y) ** 2)
        errors.append(err)
        if err <= tolerance:
            converged_count += 1

    if not errors:
        return {"converge_rate": 0.0, "median_error_mm": 0.0, "p95_error_mm": 0.0}

    errors.sort()
    n = len(errors)
    median = errors[n // 2]
    p95_idx = min(int(n * 0.95), n - 1)
    p95 = errors[p95_idx]

    return {
        "converge_rate": converged_count / total_count if total_count > 0 else 0.0,
        "median_error_mm": median,
        "p95_error_mm": p95,
    }
```

### ベンチマーク結果の session_state 保存形式

```python
st.session_state["benchmark_result"] = {
    "converge_rate": 0.43,
    "median_error_mm": 0.089,
    "p95_error_mm": 0.142,
    "config": {
        "x0_bias_abs_max": 0.15,
        "a_abs_max": 0.05,
        "noise_min": 0.05,
        "noise_max": 0.10,
        "num_cases": 20,
        "seeds_per_experiment": 5,
        "seed": 42,
    },
    "experiment_ids": ["bench_exp_001", ...],
    "job_id": "cjob_...",
}
```

---

## 画面 3: 🚀 学習ラン（最重要）

学習戦略を定義して実行するメイン画面。

### レイアウト

```
┌─────────────────────────────────────────────┐
│ 新規ラン定義                                  │
│                                             │
│   ラン名: [run_wide_64x64       ]           │
│                                             │
│   モデル設定                                 │
│     model_type: [mlp]   （mlp / baseline）  │
│     epochs: [100]                           │
│                                             │
│   世代数: [3]                               │
│   ラン乱数シード: [42]                       │
│                                             │
│   世代 0（simple controller のみ）           │
│     x0_bias 絶対値の最大: [0.10]            │
│     a 絶対値の最大:       [0.03]            │
│     noise 最小:           [0.01]            │
│     noise 最大:           [0.05]            │
│     ランダム環境数: [10]   seeds/環境: [10] │
│                                             │
│   世代 1 以降（AI混合収集）                  │
│     x0_bias 絶対値の最大: [0.15]            │
│     a 絶対値の最大:       [0.05]            │
│     noise 最小:           [0.01]            │
│     noise 最大:           [0.08]            │
│     ランダム環境数: [8]    seeds/環境: [5]  │
│     AI / baseline 比率: [80] / [20] %       │
│                                             │
│              [▶ 実行開始]                   │
├─────────────────────────────────────────────┤
│ 実行中                                        │
│   run_wide_64x64  世代 1/3  学習中           │
│   ████████░░  epoch 72/100  loss: 0.0031    │
│                                             │
├─────────────────────────────────────────────┤
│ 完了済み                                      │
│   run_A  3世代  0.021mm  [詳細]             │
└─────────────────────────────────────────────┘
```

### 学習ランの session_state 管理

```python
st.session_state["learning_runs"] = [
    {
        "run_id": "run_wide_64x64",
        "config": {
            "model": {
                "model_type": "mlp",
                "epochs": 100,
            },
            "num_generations": 3,
            "seed_base": 42,
            "gen0": {
                "x0_bias_abs_max": 0.10,
                "a_abs_max": 0.03,
                "noise_min": 0.01,
                "noise_max": 0.05,
                "num_experiments": 10,
                "seeds_per_experiment": 10,
            },
            "gen_n": {
                "x0_bias_abs_max": 0.15,
                "a_abs_max": 0.05,
                "noise_min": 0.01,
                "noise_max": 0.08,
                "num_experiments": 8,
                "seeds_per_experiment": 5,
                "ai_ratio": 80,
            },
        },
        "status": "running",      # "pending" | "running" | "completed" | "failed"
        "current_gen": 1,
        "pipeline_state": "training",
        "current_job_ids": [],     # 複数の collection job を管理
        "current_train_job_id": None,
        "all_experiment_ids": ["exp_001", ...],
        "gen_results": [
            {
                "gen": 0,
                "experiment_ids": ["exp_001", ...],
                "collection_job_ids": ["cjob_001"],
                "train_job_id": "train_xyz",
                "benchmark_metrics": {
                    "converge_rate": 0.60,
                    "median_error_mm": 0.055,
                    "p95_error_mm": 0.110,
                },
                "promoted": True,
                "promoted_version": "v1",
            },
        ],
    }
]
```

### 自動パイプラインのステートマシン

`pipeline_state` の遷移:

```
"creating_experiments"
    → (N個の実験を POST /experiments で作成)
"collecting"
    → (POST /jobs → job_ids を保存 → GET /jobs/{id} でポーリング)
"training"
    → (POST /train → train_job_id を保存 → GET /train/{id} でポーリング)
"reloading_model"
    → (promoted == True の場合のみ: POST /model/reload)
"completed"
    → (最終世代が完了)
```

ステートマシンの実行ロジック（Streamlit の再レンダリングごとに呼ぶ）:

```python
def advance_pipeline(run: dict, api_client: RecipeApiClient) -> None:
    """現在の pipeline_state に応じて次のアクションを実行する。
    1回の呼び出しで1ステップだけ進める（ブロッキングしない）。
    """
    state = run["pipeline_state"]
    gen = run["current_gen"]
    config = run["config"]

    if state == "creating_experiments":
        gen_config = config["gen0"] if gen == 0 else config["gen_n"]
        rng = random.Random(config["seed_base"] + gen)
        exp_ids = []
        for i in range(gen_config["num_experiments"]):
            bolt_model = generate_random_bolt_model(
                gen_config["x0_bias_abs_max"],
                gen_config["a_abs_max"],
                gen_config["noise_min"],
                gen_config["noise_max"],
                rng,
            )
            payload = build_experiment_payload(
                name=f"{run['run_id']}_gen{gen}_{i:03d}",
                bolt_model=bolt_model,
            )
            result = api_client.create_experiment(payload)
            if result:
                exp_ids.append(result["experiment_id"])
        run["all_experiment_ids"] = run.get("all_experiment_ids", []) + exp_ids
        run["gen_results"].append({
            "gen": gen,
            "experiment_ids": exp_ids,
        })
        run["pipeline_state"] = "collecting"

    elif state == "collecting":
        if not run["current_job_ids"]:
            gen_config = config["gen0"] if gen == 0 else config["gen_n"]
            current_gen_exp_ids = run["gen_results"][gen]["experiment_ids"]
            seeds = list(range(gen_config["seeds_per_experiment"]))

            if gen == 0:
                tasks = [{"experiment_id": eid, "seeds": seeds} for eid in current_gen_exp_ids]
                job = api_client.start_collection_job({
                    "algorithm": "simple-controller",
                    "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
                    "max_steps": 10,
                    "tolerance": 0.05,
                    "tasks": tasks,
                    "max_workers": 4,
                })
                if job:
                    run["current_job_ids"] = [job["job_id"]]
            else:
                ai_ratio = config["gen_n"]["ai_ratio"] / 100.0
                n_total = len(current_gen_exp_ids)
                n_ai = max(1, round(n_total * ai_ratio))
                ai_exps = current_gen_exp_ids[:n_ai]
                bl_exps = current_gen_exp_ids[n_ai:]

                job_ids = []
                if ai_exps:
                    job = api_client.start_collection_job({
                        "algorithm": "ai-controller",
                        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
                        "max_steps": 10, "tolerance": 0.05,
                        "tasks": [{"experiment_id": eid, "seeds": seeds} for eid in ai_exps],
                        "max_workers": 4,
                    })
                    if job:
                        job_ids.append(job["job_id"])
                if bl_exps:
                    job = api_client.start_collection_job({
                        "algorithm": "simple-controller",
                        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
                        "max_steps": 10, "tolerance": 0.05,
                        "tasks": [{"experiment_id": eid, "seeds": seeds} for eid in bl_exps],
                        "max_workers": 4,
                    })
                    if job:
                        job_ids.append(job["job_id"])
                run["current_job_ids"] = job_ids
        else:
            all_done = True
            for jid in run["current_job_ids"]:
                status = api_client.get_collection_job_status(jid)
                if not status or status["status"] not in ("completed", "failed", "partial"):
                    all_done = False
                    break
            if all_done:
                run["gen_results"][gen]["collection_job_ids"] = list(run["current_job_ids"])
                run["current_job_ids"] = []
                run["pipeline_state"] = "training"

    elif state == "training":
        if not run.get("current_train_job_id"):
            job = api_client.start_training({
                "experiment_ids": run["all_experiment_ids"],
                "model_type": config["model"]["model_type"],
                "epochs": config["model"]["epochs"],
            })
            if job:
                run["current_train_job_id"] = job["train_job_id"]
        else:
            status = api_client.get_training_job_status(run["current_train_job_id"])
            if status and status["status"] in ("completed", "failed"):
                run["gen_results"][gen]["train_job_id"] = run["current_train_job_id"]
                run["gen_results"][gen]["promoted"] = status.get("promoted", False)
                run["gen_results"][gen]["promoted_version"] = status.get("promoted_version")
                if bm := status.get("benchmark_results"):
                    nm = bm.get("new_model", {})
                    run["gen_results"][gen]["benchmark_metrics"] = {
                        "converge_rate": nm.get("converge_rate"),
                        "median_error_mm": nm.get("median_final_error_mm"),
                        "p95_error_mm": nm.get("p95_final_error_mm"),
                    }
                run["current_train_job_id"] = None

                if gen >= config["num_generations"] - 1:
                    run["pipeline_state"] = "completed"
                    run["status"] = "completed"
                elif status.get("promoted"):
                    run["pipeline_state"] = "reloading_model"
                else:
                    run["current_gen"] = gen + 1
                    run["pipeline_state"] = "creating_experiments"

    elif state == "reloading_model":
        api_client.reload_ai_model()
        run["current_gen"] = gen + 1
        if run["current_gen"] >= config["num_generations"]:
            run["pipeline_state"] = "completed"
            run["status"] = "completed"
        else:
            run["pipeline_state"] = "creating_experiments"
```

### キュー方式の複数ラン管理

```python
def advance_all_runs(api_client: RecipeApiClient) -> bool:
    """全ランを管理する。戻り値: 実行中のランがあれば True。"""
    runs = st.session_state.get("learning_runs", [])
    has_running = False

    for run in runs:
        if run["status"] == "running":
            advance_pipeline(run, api_client)
            has_running = True
            break

    if not has_running:
        for run in runs:
            if run["status"] == "pending":
                run["status"] = "running"
                run["pipeline_state"] = "creating_experiments"
                has_running = True
                break

    return has_running
```

### ポーリング実装（Streamlit での非同期処理）

```python
import time

running_runs = [r for r in st.session_state.get("learning_runs", [])
                if r["status"] in ("running", "pending")]
if running_runs:
    has_active = advance_all_runs(api_client)
    if has_active:
        time.sleep(3)
        st.rerun()
```

---

## 画面 4: 📊 結果比較

### レイアウト

```
┌─────────────────────────────────────────────┐
│ 比較対象を選択:                              │
│ [✓ run_A] [✓ run_B] [□ run_C]             │
│                                             │
│ 収束率 (%)          中央誤差 (mm)           │
│  96│   ╭── run_A    0.089┄┄┄┄┄┄┄┄ ← 基準  │
│  75│╭──╯  run_B     0.05│╲               │
│  43┄┄┄┄ ← ルールベース 0.02│  ╲── run_A   │
│    0  1  2  3 世代       0  1  2  3 世代   │
│                                             │
│ 最終比較テーブル                             │
│  ラン    │収束率│中央値  │P95   │超えた世代  │
│  run_A   │ 96% │0.021mm │0.065 │ 世代1 ★  │
│  run_B   │ 75% │0.038mm │0.089 │ 超えず    │
│  ─────── ├─────┼────────┼──────┼───────── │
│  ルールベ│ 43% │0.089mm │0.142 │ ─ (基準) │
│                                             │
│  [run_A の最終モデルで AI 制御デモ →]       │
└─────────────────────────────────────────────┘
```

### 「ルールベースの壁を超えた世代」の判定

```python
def find_generation_beat_benchmark(gen_results: list, benchmark: dict) -> int | None:
    for g in gen_results:
        bm = g.get("benchmark_metrics", {})
        if (bm.get("converge_rate", 0) > benchmark["converge_rate"] and
                bm.get("median_error_mm", 999) < benchmark["median_error_mm"]):
            return g["gen"]
    return None
```

### グラフ実装

Plotly を使用。ルールベースの基準値は `shapes` で横の破線として表示:

```python
fig.add_hline(
    y=benchmark["converge_rate"] * 100,
    line_dash="dash",
    line_color="red",
    annotation_text="ルールベース基準",
)
```

---

## API リファレンス

### recipe-service (base_url = RECIPE_SERVICE_URL)

| メソッド | パス | 用途 |
|---|---|---|
| GET | /experiments | 実験一覧 |
| POST | /experiments | 実験作成（`optical_system` + `bolt_model` ネスト形式） |
| POST | /experiments/{id}/trials | トライアル作成 |
| POST | /experiments/{id}/trials/{tid}/steps | 1ステップ実行 |
| GET | /experiments/{id}/trials/{tid}/steps | ステップ一覧（指標集計に使用） |
| POST | /recipes/sweep | パラメータスイープ |

**POST /experiments ペイロード形式**:
```json
{
  "name": "...",
  "engine_type": "Simple",
  "optical_system": { "wavelength": 780.0, ... },
  "bolt_model": {
    "upper": { "x0_bias_x": 0.05, "a_x": 0.02, "b_x": 1.0, ... },
    "lower": { "x0_bias_x": 0.0, "a_x": 0.0, "b_x": 1.0, ... }
  }
}
```

### collection-orchestrator (COLLECTION_ORCHESTRATOR_SERVICE_URL)

**POST /jobs — ジョブ作成**
```json
{
  "algorithm": "simple-controller",
  "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
  "max_steps": 10,
  "tolerance": 0.05,
  "tasks": [
    {"experiment_id": "exp_001", "seeds": [0, 1, 2, 3, 4]}
  ],
  "max_workers": 4
}
```

レスポンス: `{"job_id": "cjob_...", "status": "running", "total_tasks": 5, "created_at": "..."}`

**GET /jobs/{job_id} — ジョブ状態確認**

レスポンス: `{"status": "running"|"completed"|"failed"|"partial", "completed_tasks": 3, "total_tasks": 5, "task_results": [...], ...}`

ステータス値:
- `"running"` — 実行中
- `"completed"` — 全タスク成功
- `"failed"` — 全タスク失敗
- `"partial"` — 一部タスクのみ失敗

### trainer (TRAINER_SERVICE_URL)

**POST /train — 学習開始**
```json
{
  "experiment_ids": ["exp_001", "exp_002"],
  "model_type": "mlp",
  "epochs": 100
}
```

※ `hidden_sizes` フィールドは trainer API に存在しない。trainer 側でモデル構造は固定（`[16, 8]`）。

レスポンス: `{"train_job_id": "train_job_000001", "status": "running", "message": "..."}`

**GET /train/{train_job_id} — 学習状態確認**

レスポンス:
```json
{
  "train_job_id": "train_job_000001",
  "status": "running",
  "current_epoch": 72,
  "total_epochs": 100,
  "progress_rate": 0.72,
  "last_loss": 0.0031,
  "promoted": true,
  "promoted_version": "vtrain_job_000001",
  "benchmark_results": {
    "new_model": {
      "median_final_error_mm": 0.021,
      "p95_final_error_mm": 0.065,
      "converge_rate": 0.96
    },
    "current_model": { ... }
  }
}
```

### ai-controller (AI_CONTROLLER_SERVICE_URL)

**POST /model/reload** — 昇格後にモデルをリロード

レスポンス: `{"loaded_version": "v3", "model_type": "mlp"}`

※ `api_client.py` にこのメソッドを追加すること:
```python
def reload_ai_model(self) -> dict[str, Any] | None:
    return self._request_external_service(
        "POST",
        self._ai_controller_url("/model/reload"),
        "AI Controller Service",
    )
```

### model-store (MODEL_STORE_SERVICE_URL)

| メソッド | パス | 用途 |
|---|---|---|
| GET | /models | モデル一覧（レスポンスに `current_version` フィールド含む） |

※ `GET /models/current` エンドポイントは存在しない。

---

## main.py の書き換え

```python
from __future__ import annotations
import os
from collections.abc import Callable
import streamlit as st
from app.api_client import RecipeApiClient
from app.pages import sim_validation, benchmark, learning_run, comparison

PageRenderer = Callable[[RecipeApiClient], None]

SCREENS: dict[str, PageRenderer] = {
    "🔬 シミュレーター検証": sim_validation.render,
    "🎯 ベンチマーク設定": benchmark.render,
    "🚀 学習ラン": learning_run.render,
    "📊 結果比較": comparison.render,
}

@st.cache_resource
def get_api_client() -> RecipeApiClient:
    return RecipeApiClient(
        base_url=os.getenv("RECIPE_SERVICE_URL", "http://recipe-service:8002")
    )

def main() -> None:
    st.set_page_config(page_title="auto-opt", layout="wide")
    api_client = get_api_client()
    st.sidebar.title("auto-opt")
    st.sidebar.markdown("---")
    screen_name = st.sidebar.radio("", options=list(SCREENS.keys()))
    SCREENS[screen_name](api_client)

if __name__ == "__main__":
    main()
```

---

## 実装上の注意事項

1. **session_state の永続化**: Streamlit はページ遷移でも session_state は保持される。ラン情報は `st.session_state["learning_runs"]` に格納して画面をまたいで参照する。

2. **自動リフレッシュ**: 実行中のランがある場合のみ `st.rerun()` を呼ぶ。`time.sleep(3)` のインターバルを入れてポーリング間隔を確保する。

3. **エラーハンドリング**: `api_client.py` の各メソッドは失敗時に `None` を返す。`None` チェックを必ず行い、パイプラインを止める（`run["status"] = "failed"`）。

4. **コレクションジョブの Gen 1+ 混合収集**: Gen 1+ は AI / baseline の 2 つの collection job を発行する。`current_job_ids: list[str]` で管理し、全ジョブが完了してから training に進む。ジョブのステータスには `"partial"` も含めて完了判定する。

5. **累積実験 ID**: `trainer` の `POST /train` の `experiment_ids` には、Gen 0 から現在世代までの全実験 ID を渡す。ラン内で `all_experiment_ids` リストに追記していく。

6. **既存コンポーネントの活用**: `app/components/charts.py` の `render_optical_schematic`, `render_bolt_response_graph`, `render_sim_metrics` などはシミュレーター検証タブで活用できる。`app/components/inputs.py` の `slider_number_input` もそのまま使える。

7. **ベンチマーク結果のリセット**: ベンチマーク設定を変更した場合は `st.session_state["benchmark_result"]` をクリアし、`st.session_state["learning_runs"]` のすべての `gen_results` の `benchmark_metrics` もクリアして比較グラフが混在しないようにする。ラン自体の構造（config, experiment_ids, promoted 等）は保持する。

8. **コードコメントは書かない**: WHY が非自明な場合のみ1行コメントを書く。何をしているかのコメントは不要。

---

## 削除するファイル

以下の既存ページファイルはすべて削除する（git 履歴には残る）:
- `app/pages/ai_control.py`
- `app/pages/collection.py`
- `app/pages/control.py`
- `app/pages/experiment.py`
- `app/pages/manual.py`
- `app/pages/manual_confirmation.py`
- `app/pages/model_creation.py`
- `app/pages/model_store.py`
- `app/pages/results.py`
- `app/pages/sweep.py`
- `app/pages/training.py`

また `app/pages/__init__.py` は空ファイルとして残す。
