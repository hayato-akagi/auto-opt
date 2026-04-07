# position-service

コリメートレンズのXY位置設定サービス。命令位置を受け取り、実効レンズ配置ズレ値を返す。

- **Port**: 8004
- **技術スタック**: Python, FastAPI
- **依存サービス**: なし

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
  "coll_x_shift": 0.02,    // mm, 実効X方向ズレ
  "coll_y_shift": -0.05    // mm, 実効Y方向ズレ
}
```

### 命令値と実効値の区別

- `coll_x`, `coll_y` = **命令値**（ユーザーが指定した位置）
- `coll_x_shift`, `coll_y_shift` = **実効値**（機構を通した後の実際のズレ）
- 現時点ではパススルーのため同一値。将来非線形性が入ると乖離する

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
- 繰り返し精度のノイズモデル
- Z軸方向（`coll_z`）の追加

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
