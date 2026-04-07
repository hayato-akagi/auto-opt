# Bolt Service 仕様

- **Port**: 8005
- **役割**: ボルト締結トルクからレンズ位置ずれを計算。試行ごとにノイズが変動。
- **依存**: なし

## API

### `POST /bolt/apply`

#### Request Body

```jsonc
{
  "torque_upper": 0.5,       // N·m, 上ボルトトルク
  "torque_lower": 0.5,       // N·m, 下ボルトトルク
  "bolt_model": {
    "upper": {
      "shift_x_per_nm": 0.001,    // mm/N·m, トルクあたりX方向ずれ
      "shift_y_per_nm": 0.003,    // mm/N·m, トルクあたりY方向ずれ
      "noise_std_x": 0.002,       // mm, ばらつき (1σ)
      "noise_std_y": 0.005        // mm, ばらつき (1σ)
    },
    "lower": {
      "shift_x_per_nm": -0.0005,
      "shift_y_per_nm": 0.002,
      "noise_std_x": 0.001,
      "noise_std_y": 0.003
    }
  },
  "random_seed": null           // 再現性が必要な場合に指定
}
```

#### Response (200)

```jsonc
{
  "delta_x": 0.003,            // mm, X方向ずれ合計
  "delta_y": 0.008,            // mm, Y方向ずれ合計
  "used_seed": 1234567890,     // 実際に使用されたシード（再現用）
  "detail": {
    "upper": {"delta_x": 0.0015, "delta_y": 0.0055},
    "lower": {"delta_x": 0.0015, "delta_y": 0.0025}
  }
}
```

#### Error Response (422)

```jsonc
{
  "detail": [
    {"loc": ["body", "torque_upper"], "msg": "field required", "type": "value_error.missing"}
  ]
}
```

### `GET /health`

```jsonc
{"status": "ok", "service": "bolt-service", "version": "0.1.0"}
```

## エラーレスポンス定義

| ステータス | 条件 | 内容 |
|-----------|------|------|
| 200 | 正常完了 | ずれ計算結果 |
| 422 | パラメータ不正・欠落 | FastAPI標準のバリデーションエラー |

## 計算モデル

上下ボルトそれぞれについて:

$$\Delta x_i = T_i \cdot s_{xi} + \mathcal{N}(0,\, \sigma_{xi}^2)$$
$$\Delta y_i = T_i \cdot s_{yi} + \mathcal{N}(0,\, \sigma_{yi}^2)$$

合計:

$$\Delta x = \Delta x_{\text{upper}} + \Delta x_{\text{lower}}$$
$$\Delta y = \Delta y_{\text{upper}} + \Delta y_{\text{lower}}$$

- $T_i$: トルク (N·m)
- $s$: `shift_per_nm` (mm/N·m)
- $\sigma$: `noise_std` (mm)
- 試行ごとにノイズが異なる（同じトルクでも結果が変動）

## ノイズ適用タイミング

ノイズは **API 呼び出しごとに毎回新たにサンプリング** される。

- 1回のステップ実行 = 1回の Bolt Service 呼び出し = 1回のノイズサンプリング
- 試行開始時にシードを固定するような仕組みはない
- 再現性が必要な場合は `random_seed` を明示的に指定する

## ノイズシードの挙動

| `random_seed` 値 | 挙動 |
|------------------|------|
| `null` (デフォルト) | 呼び出しごとにランダムなシードを生成。毎回異なる結果になる |
| 整数値 (例: `42`) | 指定シードでノイズを生成。同じ入力なら同じ結果になる |

レスポンスの `used_seed` に実際に使われたシードが返る。
Recipe Service はこの値を step JSON に記録することで、後から同一結果を再現できる。

### 再現実験の手順

1. 過去の step JSON から `bolt_shift.used_seed` を取得
2. 同じトルク・ボルトモデル・`random_seed` で再呼出し
3. 同一の `delta_x`, `delta_y` が得られる

## パラメータ範囲

| パラメータ | 単位 | デフォルト | 範囲 |
|-----------|------|----------|------|
| torque_upper | N·m | 0.5 | 0〜2.0 |
| torque_lower | N·m | 0.5 | 0〜2.0 |
| shift_x_per_nm | mm/N·m | - | 任意 |
| shift_y_per_nm | mm/N·m | - | 任意 |
| noise_std_x | mm | - | ≥ 0 |
| noise_std_y | mm | - | ≥ 0 |
