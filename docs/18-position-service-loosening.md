# 将来タスク: ボルト緩め動作の position-service への追加

## 背景

現在の `position-service` は完全なパススルー実装になっている。

```python
# services/position-service/app/core.py
def apply_position(coll_x, coll_y):
    return coll_x, coll_y  # 指令値をそのまま返す
```

物理的には、制御ループの各ステップは以下の順序で実行される：

```
[n ステップ]
  コリメータを coll_x/y に移動
  → actual_x/y（位置決め後、ボルト締め前）= sim_after_position
  → ボルト締め → delta_x/y のずれ発生
  → final_x/y = sim_after_bolt

[n+1 ステップへの移行]
  ボルト緩め
  → レンズは approximately (actual_x/y + 緩め後ノイズ) に戻る  ← 現在未モデル化
  → コントローラーが新しい coll_x/y を指令
  → 再び位置決め
```

現在のシミュレーションは「ボルト緩め後にレンズが締め前位置に戻る」効果を無視しており、
制御器は常にゼロ誤差で任意の位置に移動できると仮定している。

## 実装方針

### 追加するモデル

ボルト緩め後の位置を以下でモデル化する：

```
released_x = actual_x + N(0, σ_release_x)
released_y = actual_y + N(0, σ_release_y)
```

`σ_release` はボルト締め時のずれ量に比例するのが物理的に自然：

```python
sigma_x = release_ratio * abs(bolt_delta_x)
sigma_y = release_ratio * abs(bolt_delta_y)
```

デフォルト値の目安: `release_ratio = 0.1`（締め時ずれの10%）

### 変更が必要なファイル

| ファイル | 変更内容 |
|---|---|
| `services/position-service/app/models.py` | `ReleaseModel` 追加（`release_ratio: float`）|
| `services/position-service/app/core.py` | `apply_position` に `prev_bolt_delta` と `release_model` 引数追加 |
| `services/position-service/app/main.py` | リクエストスキーマ更新 |
| `services/recipe-service/app/orchestrator.py` | `apply_position` 呼び出し時に前ステップの `bolt_delta` を渡す |
| `services/recipe-service/app/models.py` | `StepRecord` に `released_position` フィールド追加 |

### 変更後のステップデータ構造

```json
{
  "step_index": 1,
  "command": {"coll_x": 0.02, "coll_y": -0.01},
  "released_position": {        ← 新規（前ステップのボルト緩め後位置）
    "released_x": 0.009,
    "released_y": -0.003
  },
  "after_position": {
    "actual_x": 0.02,
    "actual_y": -0.01
  },
  "sim_after_position": {...},
  "bolt_shift": {...},
  "after_bolt": {...},
  "sim_after_bolt": {...}
}
```

### 軌跡ビューアへの影響

`released_position` が追加されると、軌跡ビューアのステップ間遷移が：

```
現在: final[n] ─(点線)─→ pre[n+1]

変更後: final[n] ─(実線)─→ released[n+1] ─(矢印)─→ pre[n+1]
        ↑ボルト緩め直後              ↑コントローラー補正
```

これにより「ボルト緩め後に戻る位置のばらつき」と「制御器がそれをどう補正するか」が
分離して可視化できるようになる。

## 優先度

- **低〜中**: 現在のシミュレーションでも AI 制御の学習・評価は十分可能
- ボルト緩めノイズが大きい実機を想定した場合に重要度が上がる
- 実機との Sim-to-Real ギャップを埋めるフェーズで取り組む

## 関連ファイル

- [position-service/app/core.py](../services/position-service/app/core.py)
- [recipe-service/app/orchestrator.py](../services/recipe-service/app/orchestrator.py)
- [軌跡ビューア実装](../services/streamlit-app/app/pages/2_🧬_Generation_Pipeline.py)
