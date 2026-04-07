# streamlit-app

光学系シミュレーションの操作・可視化 UI。Recipe Service のみと通信する。

- **Port**: 8501
- **技術スタック**: Python, Streamlit
- **依存サービス**: recipe-service

## 通信先

Streamlit は **Recipe Service (`http://recipe-service:8002`) のみ**と通信する。

## 画面構成

### 1. 実験管理画面

- 実験一覧表示 (`GET /experiments`)
- 新規実験作成フォーム
  - 光学系パラメータ入力（スライダー＋数値入力）
  - ボルトモデルパラメータ入力（ばらつき範囲含む）
- 実験選択 → 試行一覧へ

### 2. 手動操作画面

- 選択中の実験に対して手動ステップ実行
  - XY位置スライダー
  - 上下ボルトトルクスライダー
  - 「実行」ボタン → `POST /experiments/{id}/trials/{id}/steps`
- 結果表示:
  - 位置調整後スポット / ボルト締結後スポット の並列表示
  - スポット中心位置、RMS半径、ケラレ率
  - スポット打点図（ray_hits がある場合）

### 3. スイープ画面

- ベースパラメータ設定
- スイープ対象パラメータ選択 + 範囲指定
- 結果グラフ:
  - パラメータ vs スポット中心位置
  - パラメータ vs スポットRMS半径
  - パラメータ vs ケラレ率

### 4. 結果閲覧画面

- 試行のステップ一覧
- ステップごとの詳細データ表示
- 試行間の比較グラフ

### 5. 制御ループ画面（将来）

- PIDゲイン設定
- 制御ループ実行
- 収束過程グラフ

## API呼び出し一覧

| 画面 | 操作 | API |
|------|-----|-----|
| 実験管理 | 一覧表示 | `GET /experiments` |
| 実験管理 | 新規作成 | `POST /experiments` |
| 実験管理 | 詳細表示 | `GET /experiments/{id}` |
| 手動操作 | 試行開始 | `POST /experiments/{id}/trials` |
| 手動操作 | ステップ実行 | `POST /experiments/{id}/trials/{id}/steps` |
| 手動操作 | 試行完了 | `POST /experiments/{id}/trials/{id}/complete` |
| 手動操作 | 画像取得 | `POST /experiments/{id}/trials/{id}/steps/{idx}/images` |
| スイープ | スイープ実行 | `POST /recipes/sweep` |
| 結果閲覧 | 試行一覧 | `GET /experiments/{id}/trials` |
| 結果閲覧 | ステップ一覧 | `GET /experiments/{id}/trials/{id}/steps` |
| 結果閲覧 | ステップ詳細 | `GET /experiments/{id}/trials/{id}/steps/{idx}` |

## 環境変数

| 変数 | デフォルト | 内容 |
|------|----------|------|
| `RECIPE_SERVICE_URL` | - | Recipe Service のURL |

## 開発

```bash
cd services/streamlit-app
pip install -r requirements.txt
streamlit run app/main.py --server.port 8501
```
