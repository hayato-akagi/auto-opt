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
`n_parallel_envs` 個の環境がその範囲から一様分布でサンプリングされる（[generation_manager.py:_sample_envs](../services/collection-orchestrator/app/generation_manager.py)）。

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

1. **env は世代をまたいで固定**: `envs` はパイプライン開始時に一度だけ `_sample_envs` でサンプリングされ、全世代で使い回される
   （`run()` 内で `envs` はループの外で1回だけ生成）。つまり同一パイプライン内では「未知の環境」は登場せず、
   複数世代を回しても学習環境の多様性自体は増えない。多様性を増やすには `n_parallel_envs` を増やすか、
   分布の範囲を広げるしかない。
2. **held-out（学習に使わない検証用env）の仕組みがない**: 現在の生成パイプライン・collectionジョブのどちらも、
   「学習で使った分布」と「評価専用の分布」を分離する機能を持たない。本ドキュメントの実験は、
   これを2本立てのパイプライン（学習用パイプラインA + 評価用パイプラインB）で代替する運用回避策を使う
   （[5節](#5-held-out評価の実施方法運用回避策)）。
3. **target位置・光学エンジンは固定**: `target.spot_center_{x,y}` はパイプライン全体で1点固定。Kraken/Simpleエンジンの切り替えもパイプライン単位。
   これらの汎化は今回のスコープ外。

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

## 5. held-out評価の実施方法（運用回避策）

現状コードでは学習用と評価用のenv分布を1パイプライン内で分離できないため、次の2本立てで代替する。

```
パイプラインA（学習）: bolt_distribution = G1、n_generations=N、model_path を都度保存
パイプラインB（評価）: bolt_distribution = G2/G3（Aより広い）、n_generations=1、
                        gen0_controller に評価したいモデルを固定して1世代だけ回す
```

ただし `PipelineConfig.gen0_controller` は現状 `simple-controller` / `adaptive-controller` しか選べず、
訓練済み `ai-controller` / `lstm-controller` モデルをGen0として直接評価する経路がない。
これは[6節](#6-スコープ外未実装のためのメモ)の実装課題として扱い、当面は以下の簡易代替で近似する:

- パイプラインAの **最終世代の収集フェーズの `final_distances` / `success_rate`**（= G1分布上の性能）と、
- パイプラインAの成果物モデルを使い、**手動でG2/G3の `bolt_distribution` を設定した新規パイプライン**
  （`n_generations=1`、`gen0_controller` は使わず1世代目から `gen1plus_controller` を使わせたい場合は
  `n_generations` を2にして1世代目は捨てる、等の工夫が要る）

  を比較し、「学習分布での成功率」と「より広い分布での成功率」の差（**汎化ギャップ**）を見る。

> 正確な held-out 評価をしたいなら、CollectionJobCreateRequest に `bolt_model_override` / `bolt_distribution` を
> 追加し、既存モデルに対して任意の分布で評価専用ジョブを回せるようにするのが最短。実装は今回のスコープ外だが、
> 次の汎化実験に着手する前に着手することを推奨する。

---

## 6. スコープ外（未実装）のためのメモ

以下は今回のドキュメント化では扱わないが、汎化性を本格的に検証する上で近い将来に必要になる見込みのため記録しておく。

- **held-out評価専用API**: 上記の通り、plainなcollectionジョブに `bolt_model_override` 相当を渡せるようにする
- **target位置のランダム化**: `TargetSpot` をtrial/env単位でサンプリングできるようにする
- **世代ごとのenv再サンプリング**: `_sample_envs` を世代ごとに呼び直す（または新旧envを混在させる）オプション
- **光学エンジン間汎化**: Kraken/Simple両方でデータ収集・評価するパイプライン連携

---

## 7. 推奨実験順序

```
Step 1 ─ G1（標準）でベースラインパイプラインを回し、n_generations分の success_rate / final_distances を記録
              ↓
Step 2 ─ 同一設定のまま bolt_distribution だけ G2 に広げて再学習し、G1と比較
              ↓ 収束率が大きく落ちない
         G3へ進む
              ↓ 収束率が大きく落ちる
         そのレベルを「現行モデル容量・データ量での限界」として記録し、
         17-learning-plan.md の軸B（hidden_dim）・軸C（データ量）を先に検証してから戻る
Step 3 ─ 5節の運用回避策で、Step1/2で学習したモデルを「学習分布より広い分布」に晒し、
         成功率の落ち込み（汎化ギャップ）を記録
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
| 汎化ギャップ | 学習分布 success_rate − 評価分布 success_rate | 5節の運用回避策で算出。0に近いほど汎化できている |

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
