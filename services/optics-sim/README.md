# optics-sim

KrakenOS による逐次光線追跡サービス。完成パラメータを受け取り、1回のシミュレーション結果を返す純粋計算エンジン。

- **Port**: 8001
- **技術スタック**: Python, FastAPI, KrakenOS
- **依存サービス**: なし

## 座標系

```
        Y (Fast axis)
        ↑
        │
  Z ────┘──→ X (Slow axis)
  (光軸)
```

| 軸 | 方向 | 対応パラメータ |
|----|------|--------------|
| X | Slow axis | `coll_x_shift`, `ld_emit_w` |
| Y | Fast axis | `coll_y_shift`, `ld_emit_h` |
| Z | 光軸方向 | `dist_ld_coll`, `dist_coll_obj`, `sensor_pos` |

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
  "return_ray_hits": false,              // 光線座標データを含めるか (デフォルト false)
  "return_ray_path_image": false,        // 光路図を含めるか (デフォルト false)
  "return_spot_diagram_image": false,     // スポット図を含めるか (デフォルト false)

  // --- E. カメラ設定（オプション、KrakenOS版では無視） ---
  "camera": null                         // 後方互換性のため受け付けるが使用しない
}
```

A〜Cの光学パラメータは全て必須。デフォルト値はこのサービスでは持たない（Recipe Service が管理）。
Dのオプションはすべてデフォルト `false`。

#### Response (200)

```jsonc
{
  "spot_center_x": 0.012,       // mm, 光軸からのX方向ずれ
  "spot_center_y": -0.042,      // mm, 光軸からのY方向ずれ
  "spot_rms_radius": 0.005,     // mm, RMS半径
  "spot_geo_radius": 0.012,     // mm, 幾何学的半径（最遠光線）
  "spot_peak_x": 0.011,         // mm, ピーク強度位置X
  "spot_peak_y": -0.041,        // mm, ピーク強度位置Y

  "num_rays_launched": 500,
  "num_rays_arrived": 487,
  "vignetting_ratio": 0.026,    // ケラレ率

  "ray_hits": null,              // return_ray_hits=true 時のみ配列
  "ray_path_image": null,       // return_ray_path_image=true 時のみ base64 PNG
  "spot_diagram_image": null,   // return_spot_diagram_image=true 時のみ base64 PNG

  "spot_warnings": null,         // KrakenOS版では常にnull（Simple版との互換性用）

  "computation_time_ms": 120
}
```

### `GET /health`

```jsonc
{"status": "ok", "service": "optics-sim", "version": "0.1.0"}
```

## エラーレスポンス

| ステータス | 条件 | 内容 |
|-----------|------|------|
| 200 | 正常完了 | シミュレーション結果 |
| 422 | パラメータ不正・欠落 | FastAPI標準バリデーションエラー |
| 500 | KrakenOS内部エラー | `{"detail": "simulation failed: <メッセージ>"}` |

## シミュレーション・ロジック

1. 有限サイズ発光領域（矩形 `ld_emit_w` × `ld_emit_h`）からランダム発射
2. ガウシアン角度分布（FWHM = `ld_div_fast/slow` + `err`）、`ld_tilt` で初期角オフセット
3. KrakenOS 面定義: 曲率半径 + コーニック定数の非球面レンズ、デセンタ (`coll_x/y_shift`) 適用
4. 対物レンズは KrakenOS 理想薄肉レンズ（`obj_f`）
5. 逐次光線追跡（スネルの法則）
6. 観測面到達光線からスポット中心・RMS半径を算出

### 光線数について

- `num_rays_launched` は常に `num_rays` と同じ値
- `num_rays_arrived` はシミュレーションごとに異なりうる（ケラレ、全反射等）
- 1ステップ内でSimが2回呼ばれる場合（after_position と after_bolt）、光線のランダム発射が独立なため `num_rays_arrived` が微小に異なることがある。これは期待動作

### 画像データの扱い

- このサービスは `return_*` フラグに忠実に動作する（フィルタは行わない）
- 画像を保存対象から除外するのは Recipe Service の責務
- Streamlit が画像を表示したい場合は Recipe Service の画像再取得 API を使う

## 環境変数

| 変数 | デフォルト | 内容 |
|------|----------|------|
| `PORT` | `8001` | リッスンポート |
| `MOCK_SIMULATION` | `false` | `true` のとき KrakenOS 非依存のモック計算モードで応答 |

## 開発

```bash
cd services/optics-sim
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```
