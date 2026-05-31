# Streamlit UI リニューアル 実装プラン

docs/14-ux-redesign.md の仕様に基づく段階的実装プラン。
各フェーズは独立してテスト可能。

---

## Phase 0: 足場づくり（所要ファイル操作のみ）

### 0-1. 旧ページファイル削除
```
rm services/streamlit-app/app/pages/ai_control.py
rm services/streamlit-app/app/pages/collection.py
rm services/streamlit-app/app/pages/control.py
rm services/streamlit-app/app/pages/experiment.py
rm services/streamlit-app/app/pages/manual.py
rm services/streamlit-app/app/pages/manual_confirmation.py
rm services/streamlit-app/app/pages/model_creation.py
rm services/streamlit-app/app/pages/model_store.py
rm services/streamlit-app/app/pages/results.py
rm services/streamlit-app/app/pages/sweep.py
rm services/streamlit-app/app/pages/training.py
```

### 0-2. 空ページファイル作成（スタブ render 関数のみ）
- `app/pages/sim_validation.py` — `def render(api_client): st.header("🔬 シミュレーター検証")`
- `app/pages/benchmark.py` — `def render(api_client): st.header("🎯 ベンチマーク設定")`
- `app/pages/learning_run.py` — `def render(api_client): st.header("🚀 学習ラン")`
- `app/pages/comparison.py` — `def render(api_client): st.header("📊 結果比較")`

### 0-3. main.py 書き換え
4画面ナビゲーション構成に置き換え。

### 0-4. api_client.py に `reload_ai_model()` 追加

### テスト方法
```bash
docker compose up -d --build streamlit-app
# ブラウザで http://localhost:9501 を開き、4画面の切り替えを確認
```

---

## Phase 1: 画面 1 — シミュレーター検証

### 1-1. タブ1: 手動操作
- 既存の `manual.py` / `manual_confirmation.py` から手動ステップ実行ロジックを移植
- 実験選択 → coll_x/coll_y スライダー → 1ステップ実行 → 結果表示
- `render_sim_metrics` を活用

### 1-2. タブ2: パラメータスイープ
- 既存の `sweep.py` からスイープロジックを移植
- `POST /recipes/sweep` → `plot_sweep_charts` で表示

### 1-3. タブ3: ボルト応答確認
- スライダーで bolt_model パラメータ設定
- `render_bolt_response_graph` で可視化
- 実験作成 → ステップ実行でボルト前後の差を表示

### テスト方法
```bash
docker compose up -d
# 各タブの操作を手動確認:
# - 手動操作: 実験選択 → スライダー操作 → ボタン → 結果表示
# - スイープ: 範囲指定 → 実行 → ヒートマップ表示
# - ボルト: パラメータ変更 → グラフ更新
```

---

## Phase 2: 画面 2 — ベンチマーク設定

### 2-1. 共通ユーティリティ作成
以下の関数を `app/pages/benchmark.py` 内（またはモジュール分離）に実装:
- `generate_random_bolt_model()` — upper/lower ネスト形式のランダム bolt_model 生成
- `build_experiment_payload()` — POST /experiments ペイロード構築
- `compute_benchmark_metrics()` — task_results から指標集計

### 2-2. フォーム UI
- x0_bias_abs_max, a_abs_max, noise_min, noise_max, num_cases, seeds_per_experiment, seed の入力
- 「ベンチ環境を生成してルールベース実行」ボタン

### 2-3. 実行フロー
- 実験生成 → collection job 投入 → ポーリング → 指標集計 → session_state 保存
- 設定済み状態の表示
- 「再設定」で benchmark_result クリア + 全ランの benchmark_metrics クリア

### テスト方法
```bash
docker compose up -d
# 1. フォーム入力 → 実行ボタン
# 2. ジョブ完了まで待機（自動リフレッシュ）
# 3. 収束率・中央誤差・P95 が表示されることを確認
# 4. 再設定ボタンでリセットされることを確認
```

### 単体テスト
- `generate_random_bolt_model` の出力が upper/lower 構造であること
- `build_experiment_payload` が正しいペイロード形式であること
- `compute_benchmark_metrics` の計算が正しいこと（モックデータで検証）

---

## Phase 3: 画面 3 — 学習ラン（パイプライン基盤）

### 3-1. フォーム UI
- ラン名、model_type、epochs、世代数、seed_base の入力
- Gen 0 / Gen N の bolt パラメータ範囲、環境数、seeds/環境、AI比率
- 「実行開始」ボタン → session_state に run を追加（status="pending"）

### 3-2. パイプラインステートマシン
- `advance_pipeline()` 実装
- `advance_all_runs()` キュー管理
- ポーリング（sleep(3) + st.rerun()）

### 3-3. 進捗表示 UI
- 実行中: 世代番号、pipeline_state、epoch/loss プログレスバー
- 完了: ラン名、世代数、最終誤差のサマリー

### 3-4. generate/build 関数の共有
Phase 2 で作った `generate_random_bolt_model` / `build_experiment_payload` を再利用する。
benchmark.py 内に書いた場合は learning_run.py から import する。

### テスト方法
```bash
docker compose up -d
# 1. ベンチマーク設定済みの状態で学習ラン画面へ
# 2. ラン定義 → 実行開始
# 3. 世代 0: 実験作成 → 収集 → 学習 が自動で進むことを確認
# 4. 世代 1+: AI混合収集が2ジョブに分かれることを確認
# 5. 全世代完了後 status="completed" になることを確認
```

### 段階的テスト（世代数=1 で最小ケース）
```
世代数=1, 環境数=2, seeds/環境=2 で高速に1サイクルを検証
```

---

## Phase 4: 画面 4 — 結果比較

### 4-1. ラン選択 UI
- 完了済みランのチェックボックス選択

### 4-2. グラフ
- 収束率の世代推移折れ線（Plotly）
- 中央誤差の世代推移折れ線
- ルールベース基準の破線

### 4-3. 比較テーブル
- 最終世代の指標 + 「超えた世代」判定
- `find_generation_beat_benchmark()` 実装

### テスト方法
```bash
# Phase 3 で完了済みランが2つ以上ある状態で:
# 1. 複数ランを選択 → グラフに複数線が描画される
# 2. ルールベース基準の破線が表示される
# 3. テーブルに正しい値が出る
```

---

## Phase 5: 統合テスト・仕上げ

### 5-1. E2E シナリオ
1. シミュレーター検証で動作確認
2. ベンチマーク設定（num_cases=5, seeds=3）
3. 学習ラン A（世代数=2、易しい条件）
4. 学習ラン B（世代数=2、難しい条件）
5. 結果比較で A vs B

### 5-2. エッジケース確認
- ベンチマーク未設定で学習ラン画面 → 警告表示
- 実行中にページ遷移 → ポーリングが止まらないこと
- API エラー発生時 → run.status = "failed" になること
- ベンチマーク再設定 → benchmark_metrics がクリアされること

### 5-3. Docker ビルド確認
```bash
docker compose build streamlit-app
docker compose up -d
```

---

## ファイル依存関係

```
main.py
  ├── api_client.py (reload_ai_model 追加)
  ├── pages/sim_validation.py
  │     └── components/charts.py, components/inputs.py
  ├── pages/benchmark.py
  │     ├── generate_random_bolt_model()
  │     ├── build_experiment_payload()
  │     └── compute_benchmark_metrics()
  ├── pages/learning_run.py
  │     ├── benchmark.py の generate/build 関数を import
  │     ├── advance_pipeline()
  │     └── advance_all_runs()
  └── pages/comparison.py
        └── find_generation_beat_benchmark()
```
