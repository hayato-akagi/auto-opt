# simple-controller サービス仕様

- **サービス名**: `simple-controller`
- **Port**: 8003
- **役割**: XY 調整前スポットに対する目標との差から、相対操作量を返す最初の制御器サービス
- **準拠先**: [05-controller.md](./05-controller.md)
- **依存**: recipe-service

## 概要

simple-controller サービスは、各サイクルで以下の 3 つを入力として受け取り、次の相対操作量を計算する。

1. XY 調整前スポット
2. 現在の commanded XY 位置
3. 直前の締結後スポット

ここで **XY 調整前スポット** は、前ステップの `sim_after_position` に緩め時揺らぎを加えた仮想観測値として定義する。

$$
spot_{pre}^{ctrl} = sim\_after\_position^{prev} + noise_{release}
$$

収束判定は常に `sim_after_bolt` を使う。

## 想定フロー

### Step 0（初期観測）

1. エピソード開始時にボルトモデルをランダム化する
2. 初期 XY 位置をランダム化する
3. 初期 XY 位置で Recipe step を 1 回実行する
4. `sim_after_position` を初期観測スポットとして取得する
5. `sim_after_bolt` を初期締結後スポットとして取得する
6. 初期補正を固定ゲイン 1 で行う

初期補正量:

$$
\Delta x_{boot} = x_{target} - x_{pre,0}
$$

$$
\Delta y_{boot} = y_{target} - y_{pre,0}
$$

### 制御ループ

1. 前ステップの `sim_after_position` に緩め時揺らぎを足して XY 調整前スポットを作る
2. その XY 調整前スポットと現在 commanded XY を制御器へ入力する
3. 制御器は相対操作量 `delta_coll_x`, `delta_coll_y` を返す
4. commanded XY を更新する
5. 更新後の XY 位置で Recipe step を実行する
6. `sim_after_bolt` で収束判定する
7. 未収束なら、緩め時揺らぎをサンプリングして次サイクルへ進む

## 数式

### 誤差定義

$$
e_x = x_{target} - x_{pre}^{ctrl}
$$

$$
e_y = y_{target} - y_{pre}^{ctrl}
$$

### 相対操作量

$$
\Delta coll_x = k_x \cdot e_x
$$

$$
\Delta coll_y = k_y \cdot e_y
$$

### クリップ

$$
\Delta coll_x = \mathrm{clip}(\Delta coll_x, -\Delta_{x,max}, \Delta_{x,max})
$$

$$
\Delta coll_y = \mathrm{clip}(\Delta coll_y, -\Delta_{y,max}, \Delta_{y,max})
$$

### commanded XY 更新

$$
coll_x^{next} = \mathrm{clamp}(coll_x^{current} + \Delta coll_x, coll_{x,min}, coll_{x,max})
$$

$$
coll_y^{next} = \mathrm{clamp}(coll_y^{current} + \Delta coll_y, coll_{y,min}, coll_{y,max})
$$

## `POST /control/step` での state 解釈

```jsonc
{
  "target_spot_center_x": 0.0,
  "target_spot_center_y": 0.0,
  "current_coll_x": 0.05,
  "current_coll_y": -0.02,
  "spot_pre_x": 0.012,
  "spot_pre_y": -0.008,
  "spot_post_x": 0.018,
  "spot_post_y": -0.014,
  "step_index": 3
}
```

### 各フィールドの意味

| フィールド | 意味 |
|-----------|------|
| `current_coll_x`, `current_coll_y` | 現在の commanded XY 位置 |
| `spot_pre_x`, `spot_pre_y` | XY 調整前スポット。前ステップ `sim_after_position` + 緩め時揺らぎ |
| `spot_post_x`, `spot_post_y` | 前ステップの締結後スポット。収束判定の参照値 |
| `step_index` | Step 0 を除いた制御ステップ番号 |

## `config` フィールド

```jsonc
{
  "gain_x": 1.0,
  "gain_y": 1.0,
  "delta_clip_x": 0.05,
  "delta_clip_y": 0.05,
  "coll_x_min": -0.5,
  "coll_x_max": 0.5,
  "coll_y_min": -0.5,
  "coll_y_max": 0.5,
  "release_perturbation": {
    "std_x": 0.002,
    "std_y": 0.002
  }
}
```

| 項目 | 意味 |
|------|------|
| `gain_x`, `gain_y` | 相対操作量を計算する比例ゲイン |
| `delta_clip_x`, `delta_clip_y` | 1 ステップの最大移動量 |
| `coll_x_min/max`, `coll_y_min/max` | commanded XY の可動範囲 |
| `release_perturbation.std_x/std_y` | ボルトを緩めた際の揺らぎ標準偏差 |

## `POST /control/step` の応答例

```jsonc
{
  "delta_coll_x": 0.012,
  "delta_coll_y": 0.008,
  "next_coll_x": 0.062,
  "next_coll_y": -0.012,
  "converged": false,
  "info": {
    "error_x": 0.012,
    "error_y": 0.008,
    "distance_pre": 0.014,
    "distance_post": 0.023,
    "clipped_x": false,
    "clipped_y": false
  }
}
```

## エピソードごとのランダム化

### ボルトモデル

- エピソード開始時に 1 回だけサンプルする
- 同一 trial 内では固定する
- 指定されていないボルトパラメータは experiment の既定値を使う

### 初期 XY 位置

- エピソード開始時に 1 回だけサンプルする
- Step 0 の入力位置として使用する

### 緩め時揺らぎ

- 各未収束ステップの終了時に 1 回サンプルする
- 次サイクルの `spot_pre` を作るために使用する

## 備考

- simple-controller は `spot_pre` を主入力とするため、ボルト締結前の戻り状態を意識した制御器である
- `spot_post` は収束判定と将来の拡張（ボルト影響の推定）に利用できる
- より高度な制御器では `history` 全体や `spot_post - spot_pre` の統計を使うことを想定している