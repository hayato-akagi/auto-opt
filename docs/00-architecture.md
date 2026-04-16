# アーキテクチャ概要

## システム構成図

```
┌──────────────┐
│  Streamlit   │  :8501  可視化・操作UI
└──────┬───────┘
       │ 指示・データ参照
       ▼
┌──────────────┐
│   Recipe     │  :8002  管理・オーケストレーション・保存
│   Service    │
└──┬──┬────┬───┘
   │  │    │
   │  │    ▼
   │  │ ┌──────────┐
   │  │ │ Position │  :8004  レンズ位置調整
   │  │ └──────────┘
   │  ▼
   │ ┌──────────┐
   │ │  Bolt    │  :8005  ボルト締結→ずれ計算
   │ └──────────┘
   ▼
┌──────────────┐
│  Optics Sim  │  :8001  光線追跡 (KrakenOS)
└──────────────┘
```

Controller (:8003) は将来追加。Streamlit と Recipe Service の間に入る。

## 座標系定義

```
        Y (Fast axis)
        ↑
        │
        │
  Z ────┘──→ X (Slow axis)
  (光軸)

  光の進行方向: +Z

  LD → [コリメートレンズ] →→→ [対物レンズ] → 観測面
                          Z軸 (光軸)
```

| 軸 | 方向 | 対応 |
|----|------|------|
| X | 水平（紙面左右） | Slow axis, `coll_x_shift`, `ld_emit_w` |
| Y | 垂直（紙面上下） | Fast axis, `coll_y_shift`, `ld_emit_h` |
| Z | 光軸方向 | `dist_ld_coll`, `dist_coll_obj`, `sensor_pos` |

## サービス一覧

| # | サービス | Port | 技術スタック | 責務 |
|---|---------|------|------------|------|
| 1a | optics-sim (KrakenOS) | 8001 | Python, KrakenOS, FastAPI | 精密光線追跡計算 |
| 1b | optics-sim (Simple) | 8011 | Python, NumPy, FastAPI | 高速ガウシアンモデル計算 |
| 2 | recipe-service | 8002 | Python, FastAPI | オーケストレーション・データ保存 |
| 3 | position-service | 8004 | Python, FastAPI | レンズXY位置設定 |
| 4 | bolt-service | 8005 | Python, FastAPI | 初期位置→位置ずれ変換 |
| 5 | streamlit-app | 8501 | Python, Streamlit | UI・可視化 |
| 6 | controller (将来) | 8003 | Python, FastAPI | PID制御等 |

**注**: optics-simは2つのエンジンが選択可能：
- **KrakenOS版**（1a）: 厳密な光線追跡、全パラメータ使用
- **Simple版**（1b）: ガウシアンモデル、高速・省パラメータ

実験作成時に `engine_type` で選択。Recipe Service が自動的に適切なエンドポイントを呼び出す。

## 疎結合の原則

- 全サービス間通信は HTTP JSON API のみ
- 各サービスは他サービスの内部実装を知らない
- Optics Sim はレンズ位置がどう決まったかを知らない
- Bolt Service は光学系パラメータを知らない
- Position Service はボルトの存在を知らない
- Recipe Service だけが実行順序を知るオーケストレーター

## 典型的な実行フロー

### 手動実行（1ステップ）

```
Streamlit → Recipe: "XY=(0.02, -0.05) で実行"
  Recipe → Position: XY位置指定 → actual_x/y 返却（初期位置 x0, y0）
  Recipe → Optics Sim: 位置調整後パラメータで追跡 → 結果A保存
  Recipe → Bolt: 初期位置(x0, y0)指定 → Δx, Δy 返却
  Recipe → Optics Sim: ボルト締結後パラメータで追跡 → 結果B保存
  Recipe → Streamlit: 結果A, 結果B を返却
```

### 制御ループ（将来）

```
Streamlit → Controller: POST /control/run
  (実験ID, PIDゲイン, 目標スポット位置)
  Controller → Recipe: POST /experiments/{id}/trials (mode=control_loop)
  ループ開始:
    Controller: PID演算 → 次の coll_x, coll_y を決定
    Controller → Recipe: POST /experiments/{id}/trials/{id}/steps
      Recipe → Position → Sim → Bolt → Sim (通常のステップ実行)
    Controller: ボルト締結後スポットを取得 → 誤差確認
    収束 or max_iterations で終了
  Controller → Recipe: POST /experiments/{id}/trials/{id}/complete
  Controller → Streamlit: 全試行履歴
```

Controller は Recipe Service の既存APIのみを使う。新しいAPIは不要。
```
