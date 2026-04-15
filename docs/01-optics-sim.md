# Optics Sim サービス仕様

- **Port**: 8001
- **役割**: KrakenOS による逐次光線追跡。完成パラメータを受け取り1回のシミュレーション結果を返す。
- **依存**: なし（純粋計算エンジン）

## API

### `POST /simulate`

#### Request Body

```jsonc
{
  // --- A. 光源 (LD) ---
  "wavelength": 780,           // nm, 波長
  "ld_tilt": 0.0,              // deg, 光軸に対する傾き角
  "ld_div_fast": 25.0,         // deg, Fast axis FWHM
  "ld_div_slow": 8.0,          // deg, Slow axis FWHM
  "ld_div_fast_err": 0.0,      // deg, Fast axis 製品誤差
  "ld_div_slow_err": 0.0,      // deg, Slow axis 製品誤差
  "ld_emit_w": 3.0,            // um, 発光点幅 (Slow axis)
  "ld_emit_h": 1.0,            // um, 発光点高さ (Fast axis)
  "num_rays": 500,             // 光線本数

  // --- B. コリメートレンズ ---
  "coll_r1": -3.5,             // mm, 第1面曲率半径
  "coll_r2": -15.0,            // mm, 第2面曲率半径
  "coll_k1": -1.0,             // 第1面コーニック定数 (-1=放物面, 0=球面)
  "coll_k2": 0.0,              // 第2面コーニック定数
  "coll_t": 2.0,               // mm, 中心厚み
  "coll_n": 1.517,             // 屈折率 (BK7 @ 780nm相当)
  "dist_ld_coll": 4.0,         // mm, LD発光点→レンズ前面距離
  "coll_x_shift": 0.0,         // mm, X方向(Slow axis)配置ズレ
  "coll_y_shift": 0.0,         // mm, Y方向(Fast axis)配置ズレ
  // "coll_z_shift": 0.0,      // mm, 光軸方向（将来拡張）

  // --- C. 対物レンズ・観測系 ---
  "obj_f": 4.0,                // mm, 対物レンズ焦点距離（薄肉近似）
  "dist_coll_obj": 50.0,       // mm, コリメート後面→対物レンズ距離
  "sensor_pos": 4.0,           // mm, 対物レンズ→観測面距離

  // --- D. オプション ---
  "return_ray_hits": true,              // 光線座標データを含めるか (オプション, デフォルト false)
  "return_ray_path_image": false,       // 光路図を含めるか (オプション, デフォルト false)
  "return_spot_diagram_image": false,   // スポット図を含めるか (オプション, デフォルト false)

  // --- E. カメラ設定（オプション、KrakenOS版では未使用） ---
  "camera": null                         // CameraSettings オブジェクト（後方互換性のため受け付けるが無視される）
}
```

全パラメータ必須（デフォルト値はサービス側では持たない。Recipe Service が管理）。

> **画像データの扱い**: Optics Sim は `return_ray_path_image` / `return_spot_diagram_image` が `true` の場合に base64 PNG を返す。
> Optics Sim は常にリクエストの `return_*` フラグに忠実に動作する（フィルタは行わない）。
> **画像を除去するのは Recipe Service の責務**: Recipe Service はステップ保存時に Optics Sim を `return_*_image=false` で呼び出す。
> Streamlit が画像を表示したい場合は、Recipe Service の画像再取得 API（`POST /experiments/{id}/trials/{id}/steps/{idx}/images`）を呼ぶ。
> この API が内部で同じパラメータ + `return_*_image=true` で Optics Sim を再呼出しする。
> `ray_hits` のみオプションで保存対象となる。

#### Response (200 OK)

```jsonc
{
  // --- スポット定量値 ---
  "spot_center_x": 0.012,       // mm, 光軸からのX方向ずれ
  "spot_center_y": -0.042,      // mm, 光軸からのY方向ずれ
  "spot_rms_radius": 0.005,     // mm, RMS半径
  "spot_geo_radius": 0.012,     // mm, 幾何学的半径（最遠光線）
  "spot_peak_x": 0.011,         // mm, ピーク強度位置X
  "spot_peak_y": -0.041,        // mm, ピーク強度位置Y

  // --- 光線統計 ---
  "num_rays_launched": 500,
  "num_rays_arrived": 487,
  "vignetting_ratio": 0.026,    // ケラレ率

  // --- 光線座標（return_ray_hits=true時） ---
  "ray_hits": [
    {"x": 0.011, "y": -0.040},
    {"x": 0.013, "y": -0.043}
    // ... num_rays_arrived 個
  ],

  // --- 画像（要求時のみ、base64 PNG） ---
  "ray_path_image": null,
  "spot_diagram_image": null,

  // --- 警告（オプション） ---
  "spot_warnings": null,         // KrakenOS版では常にnull（将来拡張用）

  // --- メタ ---
  "computation_time_ms": 120
}
```

#### Error Response (422)

```jsonc
{
  "detail": [
    {"loc": ["body", "coll_r1"], "msg": "field required", "type": "value_error.missing"}
  ]
}
```

### `GET /health`

```jsonc
{"status": "ok", "service": "optics-sim", "version": "0.1.0"}
```

## エラーレスポンス定義

| ステータス | 条件 | 内容 |
|-----------|------|------|
| 200 | 正常完了 | シミュレーション結果 |
| 422 | パラメータ不正・欠落 | FastAPI標準のバリデーションエラー |
| 500 | KrakenOS内部エラー | `{"detail": "simulation failed: <メッセージ>"}` |

## シミュレーション・ロジック

1. 有限サイズ発光領域（矩形 `ld_emit_w` × `ld_emit_h`）からランダム発射
2. ガウシアン角度分布（FWHM = `ld_div_fast/slow` + `err`）、`ld_tilt` で初期角オフセット
3. KrakenOS 面定義: 曲率半径 + コーニック定数の非球面レンズ、デセンタ (`coll_x/y_shift`) 適用
4. 対物レンズは KrakenOS 理想薄肉レンズ（`obj_f`）
5. 逐次光線追跡（スネルの法則）
6. 観測面到達光線からスポット中心・RMS半径を算出

### 光線数について

- `num_rays_launched` は常に `num_rays` と同じ値（指定本数がそのまま発射される）
- `num_rays_arrived` はシミュレーションごとに異なりうる（ケラレ、全反射等による）
- 1ステップ内で Sim が2回呼ばれる場合（after_position と after_bolt）、光線のランダム発射が独立なため `num_rays_arrived` が微小に異なることがある。これは期待動作である
