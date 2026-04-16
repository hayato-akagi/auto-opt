# position-service

コリメートレンズのXY位置設定サービス。命令位置を受け取り、実際の到達位置を返す。

- **Port**: 8004
- **技術スタック**: Python, FastAPI
- **依存サービス**: なし
- **バージョン**: v1.1（レスポンスフォーマット変更）

> **v1.0 からの変更点**:
> - レスポンスフィールド: `coll_x_shift`, `coll_y_shift` → `actual_x`, `actual_y`
> - ボルトサービス連携: 返却値がボルト締結前の初期位置 `(x0, y0)` として使用される

## API

### `POST /position/apply`

#### Request

```jsonc
{
  "coll_x": 0.02,    // mm, 命令X位置
  "coll_y": -0.05    // mm, 命令Y位置
}
```

#### Response (200)

```jsonc
{
  "actual_x": 0.02,    // mm, 実際の到達X位置
  "actual_y": -0.05    // mm, 実際の到達Y位置
}
```

### 命令値と実際値の区別

- `coll_x`, `coll_y` = **命令値**（ユーザーが指定した目標位置）
- `actual_x`, `actual_y` = **実際の到達位置**（機構の誤差を含む）
- 現時点ではパススルーのため同一値。将来位置決め誤差やノイズが入ると乖離する
- **重要**: この値がボルト締結前の初期位置 `(x0, y0)` として bolt-service に渡される

### `GET /health`

```jsonc
{"status": "ok", "service": "position-service", "version": "0.1.0"}
```

## エラーレスポンス

| ステータス | 条件 | 内容 |
|-----------|------|------|
| 200 | 正常完了 | 位置計算結果 |
| 422 | パラメータ不正・欠落 | FastAPI標準バリデーションエラー |

## 現時点の実装

入力をそのまま返す（パススルー）。

## 将来拡張

- 位置決め機構の非線形性（バックラッシュ、ヒステリシス）
- ステージの分解能・量子化
- 繰り返し精度のノイズモデル: `actual = target + noise`
- Z軸方向（`coll_z`）の追加

## 連携サービス

### Bolt Service との連携

```
1. position-service: apply(coll_x, coll_y)
   → {actual_x, actual_y} = (x0, y0)

2. bolt-service: apply(x0, y0, bolt_model)
   → {delta_x, delta_y}

3. 最終位置 = (x0 + delta_x, y0 + delta_y)
```

`actual_x`, `actual_y` がボルト締結前の初期位置として次のステップに渡されます。

## 環境変数

| 変数 | デフォルト | 内容 |
|------|----------|------|
| `PORT` | `8004` | リッスンポート |

## 開発

```bash
cd services/position-service
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8004 --reload
```
