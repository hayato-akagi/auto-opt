# Simple Optics Sim サービス仕様

- **Port**: 9011（コンテナ内は8000）
- **役割**: シンプルなガウシアン分布ベースの光学シミュレーション。複雑な光線追跡を行わず、LD発光面サイズと倍率から直接スポット像を生成。
- **依存**: なし（純粋計算エンジン）
- **デフォルトエンジン**: v1.1以降、recipe-serviceのデフォルトエンジンはSimpleに設定されています

## 概要

既存の KrakenOS ベース Optics Sim サービスの代替として、シンプルな光学系向けに軽量な実装を提供します。

### Streamlit UIでの利用

**エンジン選択**（Experiments ページ）:
- デフォルト: **Simple**（推奨）
- 代替: KrakenOS（精密な光線追跡が必要な場合のみ）

**Simple エンジンで必要なパラメータ**:
Simpleモード選択時、以下3つのパラメータのみ入力が必要です：
- `ld_emit_w` (μm): LD発光幅（Slow axis）
- `ld_emit_h` (μm): LD発光高さ（Fast axis）
- `ld_tilt` (deg): LD傾き

その他のパラメータ（wavelength、divergence、collimator仕様等）は自動的にデフォルト値が使用されます。

### 光学モデル

- **LD発光面**: `ld_emit_w`（横、Slow axis）× `ld_emit_h`（縦、Fast axis）の楕円形発光面
- **ガウシアン分布**: 1/e² 強度がLDサイズと一致するガウシアン分布でスポットを生成
  - σ_x = `ld_emit_w` / 2
  - σ_y = `ld_emit_h` / 2
- **倍率**: コリメートレンズ位置 × 50倍 = カメラ上のスポット位置
  - `spot_center_x` = `coll_x_shift` × 50
  - `spot_center_y` = `coll_y_shift` × 50

### 画像生成

- カメラ画像はリクエストの `camera` パラメータ（またはフォールバックとして環境変数）で設定された解像度・視野範囲でガウシアン強度分布を生成
- スポット図・光路図ともに同じガウシアン分布画像を返す（光路図は意味を持たないが互換性のため）
- グレースケールPNG形式、base64エンコード

#### 画像生成の詳細

**フォーマット**:
- PNG（グレースケール8bit）
- base64文字列としてエンコード
- サイズ: `camera.pixel_w` × `camera.pixel_h` または環境変数 `CAMERA_WIDTH_PX` × `CAMERA_HEIGHT_PX`

**座標系**:
- 画像中心 = 物理座標 (0, 0)
- X軸: 左→右が正（Slow axis）
- Y軸: 下→上が正（Fast axis、matplotlib標準）
- 視野範囲: `camera.fov_width_mm` × `camera.fov_height_mm` または環境変数

**正規化方法（ボケると全体が薄くなる仕様）**:

ガウシアン分布の理論的ピーク強度は常に 1.0 ですが、焦点がずれると光が広範囲に分散し、単位面積あたりの光量が減少します。この物理的効果を再現するため、σの面積比で強度をスケーリングします：

```python
# 1. 基準σ（デフォーカスなし）
σ_base_x = (ld_emit_w * 1e-3) / 2  # μm → mm
σ_base_y = (ld_emit_h * 1e-3) / 2

# 2. デフォーカス適用後の実効σ
if coll_z_shift != 0:
    defocus_factor = 1.0 + abs(coll_z_shift) * DEFOCUS_COEFFICIENT
    σ_eff_x = σ_base_x * defocus_factor
    σ_eff_y = σ_base_y * defocus_factor
else:
    σ_eff_x = σ_base_x
    σ_eff_y = σ_base_y

# 3. 強度スケーリング係数（面積比の逆数）
# σが2倍 → 面積4倍 → 単位面積あたり強度1/4
intensity_scale = (σ_base_x * σ_base_y) / (σ_eff_x * σ_eff_y)

# 4. カメラ座標系でのσ（倍率適用）
σ_cam_x = σ_eff_x * MAGNIFICATION
σ_cam_y = σ_eff_y * MAGNIFICATION

# 5. 2次元ガウシアン分布
I = np.exp(-(dx**2 / (2 * σ_cam_x**2) + dy**2 / (2 * σ_cam_y**2)))

# 6. スケーリング適用
I_scaled = I * intensity_scale

# 7. グレースケール変換（0-255にクリップ）
grayscale = np.clip(I_scaled * 255, 0, 255).astype(np.uint8)
```

**効果の例**:

| 状態 | defocus_factor | intensity_scale | ピーク輝度 | 見た目 |
|------|---------------|-----------------|----------|--------|
| 焦点ぴったり | 1.0 | 1.0 | 255 | ✨ 明るい白スポット |
| 少しボケ (Δz=0.1mm) | 2.0 | 0.25 | 64 | 🌫️ やや薄いグレー |
| かなりボケ (Δz=0.4mm) | 5.0 | 0.04 | 10 | 🌁 ほぼ見えない |

**視覚的イメージ**:

```
焦点が合っている:          ボケている:
    ███                       ░░░░░
  ███████                   ░░░░░░░░░
 █████████                 ░░░░░░░░░░░
  ███████                   ░░░░░░░░░
    ███                       ░░░░░
(明るい)                    (薄い)
```

この正規化により、焦点状態を視覚的に直感的に把握できます。

**視野外スポットの処理**:

スポット中心が視野範囲外にある場合：

1. **警告を返す**: `spot_warnings` フィールドに `"Spot center is outside the field of view"` を追加
2. **視野を自動拡大**: スポットを含むように視野を拡大して画像生成（スポット中心の2.5倍を目安）
3. 拡大後の視野範囲は画像内に反映されるが、元の `fov_width_mm` / `fov_height_mm` は変更されない

## API

### `POST /simulate`

既存の Optics Sim サービスと**完全に同じAPI仕様**を持ちます。

#### Request Body

```jsonc
{
  // --- A. 光源 (LD) ---
  "wavelength": 780,           // nm, 波長（本実装では参照のみ）
  "ld_tilt": 0.0,              // deg, 光軸に対する傾き角（本実装では未使用）
  "ld_div_fast": 25.0,         // deg, Fast axis FWHM（本実装では未使用）
  "ld_div_slow": 8.0,          // deg, Slow axis FWHM（本実装では未使用）
  "ld_div_fast_err": 0.0,      // deg, Fast axis 製品誤差（本実装では未使用）
  "ld_div_slow_err": 0.0,      // deg, Slow axis 製品誤差（本実装では未使用）
  "ld_emit_w": 3.0,            // um, 発光点幅 (Slow axis) **使用**
  "ld_emit_h": 1.0,            // um, 発光点高さ (Fast axis) **使用**
  "num_rays": 500,             // 光線本数（本実装では参照のみ）

  // --- B. コリメートレンズ ---
  "coll_r1": -3.5,             // mm, 第1面曲率半径（本実装では未使用）
  "coll_r2": -15.0,            // mm, 第2面曲率半径（本実装では未使用）
  "coll_k1": -1.0,             // 第1面コーニック定数（本実装では未使用）
  "coll_k2": 0.0,              // 第2面コーニック定数（本実装では未使用）
  "coll_t": 2.0,               // mm, 中心厚み（本実装では未使用）
  "coll_n": 1.517,             // 屈折率（本実装では未使用）
  "dist_ld_coll": 4.0,         // mm, LD発光点→レンズ前面距離（本実装では未使用）
  "coll_x_shift": 0.0,         // mm, X方向(Slow axis)配置ズレ **使用**
  "coll_y_shift": 0.0,         // mm, Y方向(Fast axis)配置ズレ **使用**

  // --- C. 対物レンズ・観測系 ---
  "obj_f": 4.0,                // mm, 対物レンズ焦点距離（本実装では未使用）
  "dist_coll_obj": 50.0,       // mm, コリメート後面→対物レンズ距離（本実装では未使用）
  "sensor_pos": 4.0,           // mm, 対物レンズ→観測面距離（本実装では未使用）

  // --- D. オプション ---
  "return_ray_hits": true,              // 光線座標データを含めるか (オプション, デフォルト false)
  "return_ray_path_image": false,       // 光路図を含めるか (オプション, デフォルト false)
  "return_spot_diagram_image": false,   // スポット図を含めるか (オプション, デフォルト false)

  // --- E. カメラ設定（オプション） ---
  "camera": {                            // null の場合は環境変数を使用
    "pixel_w": 640,                      // カメラ画像幅（ピクセル）
    "pixel_h": 480,                      // カメラ画像高さ（ピクセル）
    "pixel_pitch_um": 5.3,               // ピクセルピッチ（本実装では未使用）
    "gaussian_sigma_px": 3.0,            // ガウシアンσ（本実装では未使用）
    "fov_width_mm": 1.0,                 // 視野幅（mm） **使用**
    "fov_height_mm": 1.0                 // 視野高さ（mm） **使用**
  }
}
```

**使用パラメータ**:
- **必須**: `ld_emit_w`, `ld_emit_h`, `coll_x_shift`, `coll_y_shift`
- **拡張機能**: `ld_tilt`（LD角度ずれ）, `coll_z_shift`（コリメートレンズz軸ずれ、ドキュメント上は未定義だが将来対応）
- **参照のみ**: `wavelength`, `num_rays`（レスポンスに反映）
- **未使用**: その他の光学パラメータ（レンズ形状等）

**注**: position-service が将来 `coll_z_shift` に対応した場合、本サービスは自動的にデフォーカス効果を計算します。

#### Response (200 OK)

```jsonc
{
  // --- スポット定量値 ---
  "spot_center_x": 0.0,         // mm, coll_x_shift × 50
  "spot_center_y": 0.0,         // mm, coll_y_shift × 50
  "spot_rms_radius": 0.123,     // mm, RMS半径（ガウシアンから計算）
  "spot_geo_radius": 0.246,     // mm, 幾何学的半径（3σ相当）
  "spot_peak_x": 0.0,           // mm, spot_center_x と同じ
  "spot_peak_y": 0.0,           // mm, spot_center_y と同じ

  // --- 光線統計 ---
  "num_rays_launched": 500,     // リクエストの num_rays をそのまま返す
  "num_rays_arrived": 500,      // ケラレなしと仮定
  "vignetting_ratio": 0.0,      // 常に 0.0

  // --- 光線座標（return_ray_hits=true時） ---
  "ray_hits": [
    {"x": 0.011, "y": -0.040},
    {"x": 0.013, "y": -0.043}
    // ... ガウシアン分布に従ってサンプリングされた num_rays_arrived 個
  ],

  // --- 画像（要求時のみ、base64 PNG） ---
  "ray_path_image": null,       // return_ray_path_image=true 時はガウシアン画像
  "spot_diagram_image": null,   // return_spot_diagram_image=true 時はガウシアン画像

  // --- 警告（オプション） ---
  "spot_warnings": null,         // スポットが視野外など警告がある場合のメッセージリスト

  // --- メタ ---
  "computation_time_ms": 5
}
```

#### Error Response (422)

```jsonc
{
  "detail": [
    {"loc": ["body", "ld_emit_w"], "msg": "field required", "type": "value_error.missing"}
  ]
}
```

### `GET /health`

```jsonc
{"status": "ok", "service": "simple-optics-sim", "version": "0.1.0"}
```

## 環境変数

サービスの動作を制御する環境変数：

### 基本設定

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `CAMERA_WIDTH_PX` | 640 | カメラ画像の幅（ピクセル） |
| `CAMERA_HEIGHT_PX` | 480 | カメラ画像の高さ（ピクセル） |
| `CAMERA_FOV_WIDTH_MM` | 1.0 | カメラ視野の物理幅（mm） |
| `CAMERA_FOV_HEIGHT_MM` | 1.0 | カメラ視野の物理高さ（mm） |
| `MAGNIFICATION` | 50.0 | コリメートレンズ位置からスポット位置への倍率 |
| `MOCK_SIMULATION` | false | true の場合はモックモード（高速テスト用） |

### 拡張機能パラメータ

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `DEFOCUS_COEFFICIENT` | 10.0 | mm⁻¹, z軸ずれ1mmあたりのスポット拡大係数 |
| `TILT_SENSITIVITY_X` | 0.1 | mm/deg, LD傾き1度あたりのX方向スポットオフセット |
| `TILT_SENSITIVITY_Y` | 0.1 | mm/deg, LD傾き1度あたりのY方向スポットオフセット |

## 計算ロジック

### 1. 基本ガウシアン標準偏差の計算

ガウシアン分布 I(r) = I₀ exp(-r²/2σ²) において、1/e² 強度となる半径がLDサイズと一致するように設定：

```
I(r) / I₀ = 1/e² = exp(-2)
-r²/2σ² = -2
r² = 4σ²
r = 2σ
```

よって基本標準偏差：
```python
σ_x_base = (ld_emit_w * 1e-3) / 2  # μm → mm 変換
σ_y_base = (ld_emit_h * 1e-3) / 2
```

### 2. デフォーカス効果（z軸ずれ）

コリメートレンズのz軸ずれがある場合、スポットが拡大：

```python
if coll_z_shift != 0:
    defocus_factor = 1.0 + abs(coll_z_shift) * DEFOCUS_COEFFICIENT
    σ_x_effective = σ_x_base * defocus_factor
    σ_y_effective = σ_y_base * defocus_factor
else:
    σ_x_effective = σ_x_base
    σ_y_effective = σ_y_base
```

**物理的解釈**: z方向のミスアライメントによりスポットがぼける効果をモデル化。`DEFOCUS_COEFFICIENT` が大きいほど敏感。

### 3. スポット中心位置（倍率 + LD傾きオフセット）

コリメートレンズ位置による主効果とLD傾きによる副次効果：

```python
# LD傾きによるビーム光軸オフセット
tilt_offset_x = ld_tilt * TILT_SENSITIVITY_X  # deg → mm
tilt_offset_y = ld_tilt * TILT_SENSITIVITY_Y

# 合成位置
spot_center_x = coll_x_shift * MAGNIFICATION + tilt_offset_x
spot_center_y = coll_y_shift * MAGNIFICATION + tilt_offset_y
```

デフォルトでは MAGNIFICATION = 50.0、TILT_SENSITIVITY = 0.1 mm/deg

### 4. スポット半径

2次元ガウシアン分布の RMS 半径（デフォーカス効果を反映した実効σを使用）:

```python
σ_cam_x = σ_x_effective * MAGNIFICATION  # カメラ座標系でのσ
σ_cam_y = σ_y_effective * MAGNIFICATION

spot_rms_radius = sqrt(σ_cam_x² + σ_cam_y²)
```

幾何学的半径（3σ相当）:

```
spot_geo_radius = 3 × spot_rms_radius
```

**注**: z軸ずれが大きいほど `spot_rms_radius` と `spot_geo_radius` が増加します。

### 5. 画像生成

カメラ座標系での2次元ガウシアン：

```python
x_camera = np.linspace(-FOV_WIDTH/2, FOV_WIDTH/2, CAMERA_WIDTH_PX)
y_camera = np.linspace(-FOV_HEIGHT/2, FOV_HEIGHT/2, CAMERA_HEIGHT_PX)
X, Y = np.meshgrid(x_camera, y_camera)

# デフォーカス効果を含む実効σを使用
σ_cam_x = σ_x_effective * MAGNIFICATION
σ_cam_y = σ_y_effective * MAGNIFICATION

# LD傾きオフセットを含むスポット中心
dx = X - spot_center_x
dy = Y - spot_center_y
intensity = exp(-(dx²/(2σ_cam_x²) + dy²/(2σ_cam_y²)))
```

### 6. ray_hits のサンプリング

`return_ray_hits=true` の場合、2次元ガウシアン分布から `num_rays` 個の点をサンプリング：

```python
# デフォーカス・LD傾き効果を反映したパラメータでサンプリング
x_hits = np.random.normal(spot_center_x, σ_cam_x, num_rays)
y_hits = np.random.normal(spot_center_y, σ_cam_y, num_rays)
```

**生成される分布**: z軸ずれがあればより広がった分布、LD傾きがあればオフセットされた分布になります。

## 使用方法

### Docker Compose での切り替え

既存の Optics Sim と Simple Optics Sim を切り替えるには、`docker-compose.yml` でサービス定義を切り替えます：

```yaml
# 既存の Optics Sim を使う場合
services:
  optics-sim:
    build: ./services/optics-sim
    # ...

# Simple Optics Sim を使う場合
services:
  optics-sim:
    build: ./services/simple-optics-sim
    environment:
      # 基本設定
      - CAMERA_WIDTH_PX=640
      - CAMERA_HEIGHT_PX=480
      - CAMERA_FOV_WIDTH_MM=1.0
      - CAMERA_FOV_HEIGHT_MM=1.0
      - MAGNIFICATION=50.0
      # 拡張機能（オプション）
      - DEFOCUS_COEFFICIENT=10.0
      - TILT_SENSITIVITY_X=0.1
      - TILT_SENSITIVITY_Y=0.1
    # ...
```

Recipe Service、Streamlit App からは透過的に同じAPIで利用できます。

## 制限事項と近似

- **光線追跡なし**: レンズ形状パラメータ（`coll_r1`, `coll_r2` など）は無視されます
- **物理現象の簡略化**: ケラレ、収差、波面誤差は考慮されません
- **線形倍率**: 倍率は固定（環境変数設定）で、レンズ配置による変化はモデル化されません
- **デフォーカスモデル**: z軸ずれによるスポット拡大は単純な線形係数で近似
- **LD傾きモデル**: スポット位置オフセットとして近似（楕円回転や高次効果は未実装）
- **z軸パラメータ**: `coll_z_shift` は position-service が対応していないため、現時点では常に 0.0 を想定
- **光路図**: 意味を持たず、スポット図と同じ画像を返します

**精度**: 環境変数の係数（`DEFOCUS_COEFFICIENT`, `TILT_SENSITIVITY_X/Y`）は経験的に調整する必要があります。既存の KrakenOS ベース optics-sim との定量的一致は保証されません。

## ユースケース

- **プロトタイピング**: 複雑な光学系の前に簡易モデルで検証
- **高速テスト**: CI/CD で KrakenOS を使わずに高速テスト
- **教育・デモ**: シンプルな光学系の振る舞いを直感的に理解
- **制御アルゴリズム開発**: 光線追跡のオーバーヘッドなしでPID制御等をテスト
