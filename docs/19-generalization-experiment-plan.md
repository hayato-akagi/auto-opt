# 汎化性実験計画（bolt_model 分布の拡張）

[17-learning-plan.md](17-learning-plan.md) の軸D（環境多様性）・軸G（複数パイプラインのデータ合算）を掘り下げ、
「学習に使っていない環境でもモデルが機能するか」を計測するための実験計画をまとめる。

対象コントローラ: `ai-controller`（MLP）/ `lstm-controller`（LSTM）
対象パラメータ: `PipelineConfig.bolt_distribution`（[collection-orchestrator/app/models.py](../services/collection-orchestrator/app/models.py)）

---

## 1. 汎化性とは何を指すか

このプロジェクトの「汎化」は、学習時に見た `bolt_model`（上下ボルトユニットの力学特性）のばらつきの範囲を、
未知のばらつきに対してどこまで越えて機能するか、という意味で使う。target位置や光学エンジンの汎化は今回のスコープ外（[将来課題](#6-スコープ外未実装のためのメモ)に記載）。

学習データは以下のパワー則モデルでボルト締結時のスポットずれを生成している（[04-bolt-service.md](04-bolt-service.md) 参照）:

```
x_eff = x0 + x0_bias_x
Δ_det_x = sign(x_eff) × a_x × |x_eff|^b_x
Δx = Δ_det_x × (1 + r_x),  r_x ~ Uniform(±[noise_ratio_min_x, noise_ratio_max_x])
```

モデルが学習で見ていない `(x0_bias, a, b, noise_ratio)` の組み合わせに対しても収束できるかどうかが「汎化性」の実体。

---

## 2. 現在利用できるパラメータ

`PipelineConfig.bolt_distribution`（`BoltModelDistribution`）で upper/lower 各ユニットごとに範囲(min, max)を指定すると、
`n_parallel_envs` 個の環境がその範囲から一様分布でサンプリングされる（[env_sampling.py:sample_envs](../services/collection-orchestrator/app/env_sampling.py)）。

| パラメータ | 意味 | bolt-service 側の物理制約 |
|---|---|---|
| `x0_bias_x` / `x0_bias_y` | 評価点シフト（mm） | 制約なし。ただし大きすぎると `coll_x_min/max`（既定 ±0.5mm）超過で収集失敗しうる |
| `a_x` / `a_y` | 係数（無次元） | `-0.5 ≤ a ≤ 0.5` |
| `b_x` / `b_y` | べき指数（無次元） | `0.0 < b ≤ 2.0` |
| `noise_ratio_min/max_x/y` | 乗法ノイズ比率 | `0.0 ≤ ratio ≤ 1.0` |

現在のStreamlit UI（[2_🧬_Generation_Pipeline.py](../services/streamlit-app/app/pages/2_🧬_Generation_Pipeline.py)）のデフォルトスライダー範囲:

- `x0_bias_x`: -0.2 〜 0.2（既定 0.0〜0.1）
- `a_x`: -0.1 〜 0.1（既定 0.01〜0.05）
- `b_x`: 0.5 〜 2.0（既定 0.9〜1.1）

これを「G1: 標準」として、以下でレベルを広げていく。

その他の汎化に関わるパラメータ:

- `initial_coll_range_x/y`: 各trialの初期コル位置を `base ± range` でランダム化（0=固定）
- `extra_experiment_ids`: 過去パイプラインの experiment_id を追加し、複数の分布で集めたデータを合算して学習

---

## 3. 現状の制約（既知の限界）

実験を組む前に踏まえておくべき制約:

1. **env は世代をまたいで固定**: 各世代のenvサンプリングは `bolt_distribution.seed` と `n_parallel_envs` のみで決まる
   決定的な関数（[env_sampling.py](../services/collection-orchestrator/app/env_sampling.py)）なので、同一パイプライン内では
   毎世代同じenv集合が使われる。多様性を増やすには `n_parallel_envs` を増やすか、分布の範囲を広げるしかない。
2. ~~held-out（学習に使わない検証用env）の仕組みがない~~ → **実装済み**。[5節](#5-held-out評価とスイープ自動化実装済み)を参照。
3. **target位置・光学エンジンは固定**: `target.spot_center_{x,y}` はパイプライン全体で1点固定。Kraken/Simpleエンジンの切り替えもパイプライン単位。
   これらの汎化は引き続きスコープ外（[6節](#6-スコープ外未実装のためのメモ)）。

---

## 4. 汎化レベル定義（G0〜G4）

`upper` ユニットを主軸としてばらつきを広げる。`lower` は既定では無効（0固定）のままでよい
（両方揺らす場合は upper と同じ倍率で広げる）。

| レベル | 位置づけ | x0_bias_x | a_x | b_x | noise_ratio (x/y) |
|---|---|---|---|---|---|
| G0 | 最小・単一環境に近い | (0.0, 0.0) | (0.03, 0.03) | (1.0, 1.0) | 0.01〜0.02 |
| **G1** | **標準（現行UI既定相当）** | **(0.0, 0.1)** | **(0.01, 0.05)** | **(0.9, 1.1)** | **0.01〜0.05** |
| G2 | やや広い | (-0.1, 0.2) | (-0.05, 0.08) | (0.7, 1.3) | 0.02〜0.08 |
| G3 | 広い | (-0.2, 0.3) | (-0.15, 0.15) | (0.6, 1.6) | 0.03〜0.10 |
| G4 | 極端（物理上限近傍） | (-0.3, 0.4) | (-0.35, 0.35) | (0.5, 1.8) | 0.05〜0.15 |

備考:
- `a_x`/`b_x` の物理上限は `a∈[-0.5, 0.5]`, `b∈(0, 2.0]`。G4はここに安全マージンを残した値。
- `x0_bias_x` を広げすぎると `coll_x_min/max`（既定 ±0.5mm）や `delta_clip_x`（既定 0.05〜0.1mm）を超え、
  収集自体が失敗（`converged=False` の多発、あるいは前回問題になった通信エラーのような形での全滅）しうる。
  レベルを上げるごとに `converged_trials` / `total_trials` を必ず確認すること。

---

## 5. held-out評価とスイープ自動化（実装済み）

上記の運用回避策は不要になった。学習と評価を自動化する **Generalization Sweep** 機能を実装済み。

### バックエンド

- [env_sampling.py](../services/collection-orchestrator/app/env_sampling.py): `bolt_distribution` からのenvサンプリングを
  共通化（決定的: 同じ `seed`/`n_envs` なら常に同じenv集合）
- [eval_runner.py](../services/collection-orchestrator/app/eval_runner.py): 「envサンプリング→並列trial実行→集計」を
  `run_trial_batch()` として共通化。学習パイプラインの収集フェーズ（`generation_manager.py`）と、
  held-out評価の両方がこの関数を通る
- [sweep_manager.py](../services/collection-orchestrator/app/sweep_manager.py): `SweepOrchestrator` が
  複数の `GeneralizationLevel`（名前 + `bolt_distribution`）を受け取り、
  1. レベルごとに逐次で学習パイプラインを実行（既存の `GenerationOrchestrator` をそのまま利用。
     各レベルの学習過程は通常のパイプラインとして `/experiments/pipeline/{pipeline_id}` でも参照できる）
  2. 学習済みモデルができたレベル同士・全レベルの `bolt_distribution` で総当たり評価し、
     学習×評価の成功率マトリクスを構築（同時実行数は `max_concurrent_eval_cells` で制限）
- API: `POST /sweeps`（開始）、`GET /sweeps/{sweep_id}`（進捗・マトリクス取得）、`GET /sweeps`（一覧）

### フロントエンド

新規ページ [pages/5_🧭_Generalization_Sweep.py](../services/streamlit-app/app/pages/5_🧭_Generalization_Sweep.py):

- G0〜G4をプリセットとしたレベル選択・範囲調整UI
- スイープ実行 → レベルごとの学習進捗（学習中のレベルは既存パイプラインダッシュボードをそのまま埋め込み表示）
- マトリクスが埋まるにつれて: 学習×評価の成功率ヒートマップ、汎化ギャップ棒グラフ、
  学習レベル別の最終距離分布（評価レベル間の重ね合わせ）を表示

### 使い方

サイドバーで実験・コントローラー・学習規模を設定 → 含めるレベル（G0〜G4）を選択・必要なら範囲調整 →
「▶️ スイープ開始」。`n_generations` は各レベルで最低2必要（held-out評価用のモデルを作るため、
学習フェーズが最終世代の1つ前までしか走らないことに起因）。

---

## 6. スコープ外（未実装）のためのメモ

以下は今回のスイープ機能実装では扱わなかったが、汎化性を本格的に検証する上で近い将来に必要になる見込みのため記録しておく。

- **target位置のランダム化**: `TargetSpot` をtrial/env単位でサンプリングできるようにする
- **光学エンジン間汎化**: Kraken/Simple両方でデータ収集・評価するパイプライン連携
- **レベル間の学習並列化**: `SweepOrchestrator` は現状レベルを逐次学習する（trainer/controller負荷を抑えるため）。
  同時実行できるようにする場合はリソース競合の検証が要る

---

## 7. 推奨実験順序

G0〜G4を選んで1回スイープを実行すれば、Step1〜3は自動的にマトリクスとして得られる。
手動で段階を追って確認したい場合は次の順序でも良い:

```
Step 1 ─ G1（標準）でベースラインパイプラインを回し、n_generations分の success_rate / final_distances を記録
              ↓
Step 2 ─ 同一設定のまま bolt_distribution だけ G2 に広げて再学習し、G1と比較
              ↓ 収束率が大きく落ちない
         G3へ進む
              ↓ 収束率が大きく落ちる
         そのレベルを「現行モデル容量・データ量での限界」として記録し、
         17-learning-plan.md の軸B（hidden_dim）・軸C（データ量）を先に検証してから戻る
Step 3 ─ Generalization Sweep（5節）で、Step1/2で学習したモデルを「学習分布より広い分布」に晒し、
         成功率の落ち込み（汎化ギャップ）をヒートマップ・棒グラフで確認
Step 4 ─ extra_experiment_ids で G1とG2のデータを合算学習し、単一分布学習との比較
         （分布の"多様性"そのものが効くのか、"データ量"が効くのかを切り分ける）
```

---

## 8. 記録すべき指標

各レベル・各世代で以下を `GenerationResult` から取得して記録する:

| 指標 | 取得元 | 見るポイント |
|---|---|---|
| `success_rate` | `converged_trials / total_trials` | レベルを上げたときの収束率の落ち方 |
| `final_distances` の分布 | ヒストグラム（Generation Pipelineページ） | 分布の裾が伸びていないか（一部envで発散していないか） |
| `final_train_loss` (RMSE) | 学習ロス曲線 | 分布を広げてもロスが下がりきるか（モデル容量不足の兆候） |
| 汎化ギャップ | 学習分布 success_rate − 他分布での平均 success_rate | Generalization Sweepページが自動算出・表示。0に近いほど汎化できている |

---

## 9. 実験テンプレート（コピー用 bolt_distribution ペイロード）

```json
{
  "bolt_distribution": {
    "upper": {
      "x0_bias_x": [-0.1, 0.2],
      "x0_bias_y": [0.0, 0.0],
      "a_x": [-0.05, 0.08],
      "b_x": [0.7, 1.3],
      "noise_ratio_min_x": 0.02,
      "noise_ratio_max_x": 0.08,
      "noise_ratio_min_y": 0.02,
      "noise_ratio_max_y": 0.08
    },
    "lower": {
      "a_x": [0.0, 0.0],
      "b_x": [1.0, 1.0]
    },
    "seed": 0
  }
}
```

上記はG2の例。G0〜G4の数値は[4節](#4-汎化レベル定義g0g4)の表を参照して差し替える。
`seed` を変えると同一レベル内でも異なる具体的な環境集合になる（レベル内でのばらつき確認に使える）。
