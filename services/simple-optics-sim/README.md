# simple-optics-sim

シンプルなガウシアン分布ベースの光学シミュレーションサービス。複雑な光線追跡を行わず、LD発光面サイズと倍率から直接スポット像を生成する軽量実装。

- **Port**: 8000（Docker内部）、8011（ホスト側、既存optics-simと並行稼働時）
- **技術スタック**: Python, FastAPI, NumPy, Matplotlib
- **依存サービス**: なし

## 概要

既存の KrakenOS ベース Optics Sim サービスと**完全に同じAPI仕様**を持ちます。Recipe Service から透過的に切り替え可能。

### 光学モデル

- **LD発光面**: `ld_emit_w` × `ld_emit_h` の楕円形発光面
- **ガウシアン分布**: 1/e² 強度がLDサイズと一致
- **倍率**: コリメートレンズ位置 × 50倍（デフォルト） = カメラ上のスポット位置
- **デフォーカス効果**: z軸ずれでスポット拡大（線形近似）
- **LD傾き効果**: スポット位置オフセット

### 使用パラメータ

| カテゴリ | 使用 | パラメータ |
|---------|------|-----------|
| **計算に使用** | ✓ | `ld_emit_w`, `ld_emit_h`, `ld_tilt`, `coll_x_shift`, `coll_y_shift` |
| **将来対応** | △ | `coll_z_shift`（position-service未対応） |
| **参照のみ** | ○ | `wavelength`, `num_rays` |
| **無視** | - | レンズ形状パラメータ、角度発散等 |

## 環境変数

### 基本設定

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `CAMERA_WIDTH_PX` | 640 | 画像幅（ピクセル） |
| `CAMERA_HEIGHT_PX` | 480 | 画像高さ（ピクセル） |
| `CAMERA_FOV_WIDTH_MM` | 1.0 | 視野幅（mm） |
| `CAMERA_FOV_HEIGHT_MM` | 1.0 | 視野高さ（mm） |
| `MAGNIFICATION` | 50.0 | 倍率 |

**注**: リクエストの `camera` フィールドがあればそちらを優先使用。環境変数はフォールバック。

### 拡張機能

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `DEFOCUS_COEFFICIENT` | 10.0 | mm⁻¹, z軸ずれ1mmあたりのスポット拡大係数 |
| `TILT_SENSITIVITY_X` | 0.1 | mm/deg, LD傾き1度あたりのX方向オフセット |
| `TILT_SENSITIVITY_Y` | 0.1 | mm/deg, LD傾き1度あたりのY方向オフセット |

## API

### `POST /simulate`

完全にKrakenOS版と同じインターフェース。詳細は `docs/09-simple-optics-sim.md` 参照。

#### 主な違い: 画像生成

- **KrakenOS版**: 光線の散布図（scatter plot）
- **Simple版**: ガウシアン強度分布のグレースケール画像
  - デフォーカス時は全体が薄くなる（正規化によりピーク輝度が低下）
  - 視野外スポットは自動視野拡大 + 警告（`spot_warnings`）

### `GET /health`

```jsonc
{"status": "ok", "service": "simple-optics-sim", "version": "0.1.0"}
```

## 画像正規化の仕組み

焦点がずれると光が広範囲に分散し、単位面積あたりの光量が減少します。この物理的効果を再現：

```python
# σが2倍 → 面積4倍 → 単位面積あたり強度1/4
intensity_scale = (σ_base_x * σ_base_y) / (σ_eff_x * σ_eff_y)
grayscale = np.clip(I * intensity_scale * 255, 0, 255).astype(np.uint8)
```

| 状態 | defocus_factor | intensity_scale | ピーク輝度 | 見た目 |
|------|---------------|-----------------|----------|---------|
| 焦点ぴったり | 1.0 | 1.0 | 255 | ✨ 明るい |
| 少しボケ | 2.0 | 0.25 | 64 | 🌫️ やや薄い |
| かなりボケ | 5.0 | 0.04 | 10 | 🌁 ほぼ見えない |

## 制限事項

- 光線追跡なし（レンズ形状パラメータ無視）
- ケラレ、収差、波面誤差未考慮
- デフォーカス・LD傾きは線形近似
- z軸パラメータは将来対応
- 精度は経験的調整が必要

## ユースケース

- プロトタイピング（簡易モデルで検証）
- 高速テスト（CI/CD等）
- 教育・デモ
- 制御アルゴリズム開発

## Docker 起動

```bash
# 単独起動
docker build -t simple-optics-sim .
docker run -p 8011:8000 \
  -e CAMERA_WIDTH_PX=640 \
  -e CAMERA_HEIGHT_PX=480 \
  -e CAMERA_FOV_WIDTH_MM=1.0 \
  -e CAMERA_FOV_HEIGHT_MM=1.0 \
  -e MAGNIFICATION=50.0 \
  simple-optics-sim

# docker-compose（両エンジン並行稼働）
# docker-compose.yml で設定
```

## 開発

```bash
# ローカル開発環境セットアップ
cd services/simple-optics-sim
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# サーバー起動
uvicorn app.main:app --reload --port 8000

# テスト実行
pytest tests/
```

詳細な仕様は `docs/09-simple-optics-sim.md` を参照してください。
