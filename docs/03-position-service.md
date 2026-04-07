# Position Service 仕様

- **Port**: 8004
- **役割**: コリメートレンズのXY位置設定。指令位置を受け取り、実際のレンズ配置ズレ値を返す。
- **依存**: なし

## API

### `POST /position/apply`

#### Request Body

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

> **命令値と実効値の区別**:
> - `coll_x`, `coll_y` = 命令値（ユーザーが指定した位置）
> - `coll_x_shift`, `coll_y_shift` = 実効値（機構を通した後の実際のズレ）
> - 現時点ではパススルーのため同一値。将来非線形性が入ると乖離する

#### Error Response (422)

```jsonc
{
  "detail": [
    {"loc": ["body", "coll_x"], "msg": "field required", "type": "value_error.missing"}
  ]
}
```

### `GET /health`

```jsonc
{"status": "ok", "service": "position-service", "version": "0.1.0"}
```

## エラーレスポンス定義

| ステータス | 条件 | 内容 |
|-----------|------|------|
| 200 | 正常完了 | 位置計算結果 |
| 422 | パラメータ不正・欠落 | FastAPI標準のバリデーションエラー |

## 現時点の実装

入力をそのまま返す（パススルー）。

## 将来拡張

- 位置決め機構の非線形性（バックラッシュ、ヒステリシス）
- ステージの分解能・量子化
- 繰り返し精度のノイズモデル
- Z軸方向（`coll_z`）の追加
