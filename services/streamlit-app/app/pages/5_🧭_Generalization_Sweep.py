"""ページ5: 汎化性スイープ

複数の bolt_distribution レベル（環境の広さ）で自動的に学習パイプラインを回し、
学習済みモデルをレベル間で相互評価（held-out評価）して、
「学習分布での性能」と「未知の分布での性能」をマトリクスで比較する。

詳細: docs/19-generalization-experiment-plan.md
"""

from __future__ import annotations

import time
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from app.api_client import RecipeApiClient
from app.pipeline_view import render_generation_dashboard, render_pipeline_status_header

st.set_page_config(page_title="汎化性スイープ", page_icon="🧭", layout="wide")
st.title("🧭 汎化性スイープ")
st.caption(
    "複数の bolt_model 分布（G0=狭い 〜 G4=極端）で自動学習し、"
    "学習済みモデルをレベル間で相互評価して汎化ギャップを可視化します。"
)

# ---------------------------------------------------------------------------
# Color palette (dataviz skill reference palette — light mode values)
# ---------------------------------------------------------------------------

_CATEGORICAL = [
    "#2a78d6",  # blue
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#008300",  # green
    "#4a3aa7",  # violet
]
_SEQUENTIAL_COLORSCALE = [
    [0.0, "#cde2fb"],
    [0.25, "#6da7ec"],
    [0.5, "#256abf"],
    [0.75, "#184f95"],
    [1.0, "#0d366b"],
]
_STATUS_GOOD = "#0ca30c"
_STATUS_WARNING = "#fab219"
_STATUS_CRITICAL = "#d03b3b"

# ---------------------------------------------------------------------------
# Default G0-G4 presets (docs/19-generalization-experiment-plan.md §4)
# ---------------------------------------------------------------------------

_DEFAULT_LEVELS = {
    "G0": dict(x0_bias_x=(0.0, 0.0), a_x=(0.03, 0.03), b_x=(1.0, 1.0), noise=(0.01, 0.02)),
    "G1": dict(x0_bias_x=(0.0, 0.1), a_x=(0.01, 0.05), b_x=(0.9, 1.1), noise=(0.01, 0.05)),
    "G2": dict(x0_bias_x=(-0.1, 0.2), a_x=(-0.05, 0.08), b_x=(0.7, 1.3), noise=(0.02, 0.08)),
    "G3": dict(x0_bias_x=(-0.2, 0.3), a_x=(-0.15, 0.15), b_x=(0.6, 1.6), noise=(0.03, 0.10)),
    "G4": dict(x0_bias_x=(-0.3, 0.4), a_x=(-0.35, 0.35), b_x=(0.5, 1.8), noise=(0.05, 0.15)),
}


def _client() -> RecipeApiClient:
    if "api_client" not in st.session_state:
        st.session_state["api_client"] = RecipeApiClient()
    return st.session_state["api_client"]


def _level_color(level_name: str, all_names: list[str]) -> str:
    idx = all_names.index(level_name) if level_name in all_names else 0
    return _CATEGORICAL[idx % len(_CATEGORICAL)]


def _bolt_distribution_payload(
    x0_bias_x: tuple[float, float],
    a_x: tuple[float, float],
    b_x: tuple[float, float],
    noise: tuple[float, float],
) -> dict[str, Any]:
    return {
        "upper": {
            "x0_bias_x": list(x0_bias_x),
            "x0_bias_y": [0.0, 0.0],
            "a_x": list(a_x),
            "a_y": [0.0, 0.0],
            "b_x": list(b_x),
            "b_y": [1.0, 1.0],
            "noise_ratio_min_x": noise[0],
            "noise_ratio_max_x": noise[1],
            "noise_ratio_min_y": noise[0],
            "noise_ratio_max_y": noise[1],
        },
        "lower": {"a_x": [0.0, 0.0], "b_x": [1.0, 1.0], "a_y": [0.0, 0.0], "b_y": [1.0, 1.0]},
        "seed": 0,
    }


st.session_state.setdefault("sweep_id", None)
st.session_state.setdefault("sweep_status", None)
st.session_state.setdefault("sweep_auto_refresh", True)

is_running = bool(
    st.session_state["sweep_status"] and st.session_state["sweep_status"].get("status") == "running"
)

# ---------------------------------------------------------------------------
# Sidebar — base pipeline settings (shared by every level)
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 🎯 対象実験")
    experiment_id = st.text_input(
        "experiment_id",
        value=st.session_state.get("last_experiment_id", ""),
        disabled=is_running,
    )

    st.markdown("### 🎯 目標スポット (mm)")
    target_x = st.number_input("target X", value=0.0, step=0.05, format="%.3f", disabled=is_running)
    target_y = st.number_input("target Y", value=0.0, step=0.05, format="%.3f", disabled=is_running)

    st.markdown("---")
    st.markdown("## 🧠 コントローラー / 学習設定")
    gen1plus_controller = st.radio(
        "各レベルで学習するコントローラー",
        options=["ai-controller (MLP)", "lstm-controller (LSTM)"],
        index=0,
        disabled=is_running,
    )
    use_lstm = gen1plus_controller.startswith("lstm")
    gen1plus_controller_key = "lstm-controller" if use_lstm else "ai-controller"
    n_history = st.slider("履歴ステップ N", 1, 10, 3, disabled=is_running or use_lstm)
    hidden_dim = st.selectbox("隠れ層サイズ", [64, 128, 256, 512], index=1, disabled=is_running)
    num_layers = st.slider("LSTM 層数", 1, 4, 2, disabled=is_running) if use_lstm else 2
    epochs = st.slider("エポック数", 1, 100, 20, disabled=is_running)
    warm_start = st.checkbox("累積学習 (warm-start)", value=True, disabled=is_running)

    st.markdown("---")
    st.markdown("## 📦 各レベルのデータ収集規模")
    n_parallel_envs = st.slider("並列環境数", 1, 200, 10, disabled=is_running)
    trials_per_env = st.slider("環境あたり試行数", 1, 10, 1, disabled=is_running)
    max_steps = st.slider("最大ステップ", 1, 50, 10, disabled=is_running)
    tolerance = st.number_input("収束許容 (mm)", value=0.05, min_value=0.0001, step=0.0001, format="%.4f", disabled=is_running)
    n_generations = st.slider(
        "各レベルの世代数", 2, 30, 5, disabled=is_running,
        help="学習フェーズは最終世代の1つ前まで実行されるため、held-out評価用モデルを作るには最低2世代必要です。",
    )

    st.markdown("---")
    st.markdown("## 🧪 held-out評価設定")
    eval_n_envs = st.slider("評価env数 / セル", 1, 100, 20, disabled=is_running)
    eval_trials_per_env = st.slider("評価trial数 / env", 1, 10, 1, disabled=is_running)
    max_concurrent_eval_cells = st.slider("評価セル同時実行数", 1, 25, 3, disabled=is_running)

    st.markdown("---")
    st.session_state["sweep_auto_refresh"] = st.checkbox(
        "自動更新（3秒）", value=st.session_state["sweep_auto_refresh"]
    )

# ---------------------------------------------------------------------------
# Level editor
# ---------------------------------------------------------------------------

st.markdown("## 🌐 汎化レベル")
st.caption(
    "docs/19-generalization-experiment-plan.md の G0〜G4 をプリセットとして表示。"
    "含めるレベルを選び、必要なら範囲を調整してください（upper bolt の x0_bias_x / a_x / b_x / noise を可変）。"
)

selected_level_names = st.multiselect(
    "含めるレベル（2つ以上選択）",
    options=list(_DEFAULT_LEVELS.keys()),
    default=list(_DEFAULT_LEVELS.keys()),
    disabled=is_running,
)

level_payloads: list[dict[str, Any]] = []
for name in selected_level_names:
    preset = _DEFAULT_LEVELS[name]
    color = _level_color(name, selected_level_names)
    with st.expander(f"🔩 {name}", expanded=False):
        st.markdown(
            f'<span style="color:{color}">●</span> このレベルの色（比較チャートで使用）',
            unsafe_allow_html=True,
        )
        x0_bias_x = st.slider(
            f"{name}: x0_bias_x", -0.4, 0.4, preset["x0_bias_x"], step=0.01,
            disabled=is_running, key=f"lvl_{name}_x0",
        )
        a_x = st.slider(
            f"{name}: a_x", -0.5, 0.5, preset["a_x"], step=0.01,
            disabled=is_running, key=f"lvl_{name}_a",
        )
        b_x = st.slider(
            f"{name}: b_x", 0.1, 2.0, preset["b_x"], step=0.05,
            disabled=is_running, key=f"lvl_{name}_b",
        )
        noise = st.slider(
            f"{name}: noise_ratio", 0.0, 0.3, preset["noise"], step=0.01,
            disabled=is_running, key=f"lvl_{name}_noise",
        )
    level_payloads.append({
        "name": name,
        "bolt_distribution": _bolt_distribution_payload(x0_bias_x, a_x, b_x, noise),
    })

# ---------------------------------------------------------------------------
# Control panel
# ---------------------------------------------------------------------------

col_a, col_b, col_c = st.columns([1, 1, 3])
with col_a:
    start_disabled = is_running or not experiment_id.strip() or len(level_payloads) < 2
    if st.button("▶️ スイープ開始", type="primary", disabled=start_disabled, use_container_width=True):
        payload = {
            "experiment_id": experiment_id.strip(),
            "base_config": {
                "gen0_controller": "simple-controller",
                "gen1plus_controller": gen1plus_controller_key,
                "n_parallel_envs": int(n_parallel_envs),
                "trials_per_env": int(trials_per_env),
                "n_generations": int(n_generations),
                "max_steps": int(max_steps),
                "tolerance": float(tolerance),
                "target": {"spot_center_x": float(target_x), "spot_center_y": float(target_y)},
                "model_config_train": {
                    "n_history": int(n_history),
                    "hidden_dim": int(hidden_dim),
                    "num_layers": int(num_layers),
                    "epochs": int(epochs),
                    "warm_start": bool(warm_start),
                },
            },
            "levels": level_payloads,
            "eval_n_envs": int(eval_n_envs),
            "eval_trials_per_env": int(eval_trials_per_env),
            "max_concurrent_eval_cells": int(max_concurrent_eval_cells),
        }
        created = _client().start_sweep(payload)
        if created and "sweep_id" in created:
            st.session_state["sweep_id"] = created["sweep_id"]
            st.session_state["sweep_status"] = {"status": "running"}
            st.success(f"✅ sweep_id = {created['sweep_id']}")
            time.sleep(0.3)
            st.rerun()

with col_b:
    if st.button("🔄 状態取得", use_container_width=True, disabled=not st.session_state["sweep_id"]):
        st.rerun()

with col_c:
    if st.session_state["sweep_id"]:
        st.code(f"sweep_id = {st.session_state['sweep_id']}", language="text")
    elif len(level_payloads) < 2:
        st.warning("⚠️ レベルを2つ以上選択してください")
    elif not experiment_id.strip():
        st.warning("⚠️ experiment_id を入力してください")

st.markdown("---")

# ---------------------------------------------------------------------------
# Polling & status display
# ---------------------------------------------------------------------------

sweep_id = st.session_state["sweep_id"]
status: dict | None = None
if sweep_id:
    status = _client().get_sweep_status(sweep_id)
    if status:
        st.session_state["sweep_status"] = status

if not status:
    if sweep_id:
        st.warning("スイープ情報を取得できませんでした。")
    else:
        st.info("レベルを選択し、サイドバーを設定してから ▶️ で開始してください。")
    st.stop()

st.subheader("📊 スイープ進捗")
top1, top2 = st.columns(2)
with top1:
    st.metric("ステータス", status.get("status", "?"))
with top2:
    st.metric("開始", str(status.get("started_at", ""))[:19])
if status.get("error"):
    st.error(f"スイープエラー: {status['error']}")

levels: list[dict[str, Any]] = status.get("levels", [])
level_names = [lvl["name"] for lvl in levels]

if levels:
    st.markdown("#### 🧬 レベル別 学習進捗")
    level_rows = [
        {
            "レベル": lvl["name"],
            "状態": lvl["status"],
            "学習分布での成功率": lvl.get("train_success_rate"),
            "model_path": lvl.get("model_path"),
            "エラー": lvl.get("error"),
        }
        for lvl in levels
    ]
    st.dataframe(level_rows, use_container_width=True, hide_index=True)

    running_level = next((lvl for lvl in levels if lvl["status"] == "running"), None)
    if running_level:
        with st.expander(f"🔬 学習中: {running_level['name']}（pipeline_id={running_level['pipeline_id']}）", expanded=True):
            pipeline_status = _client().get_pipeline_status(running_level["pipeline_id"])
            if pipeline_status:
                render_pipeline_status_header(pipeline_status)
                render_generation_dashboard(pipeline_status, key_prefix=f"sweep_{running_level['name']}")

# ---------------------------------------------------------------------------
# Comparison: train x eval success-rate matrix
# ---------------------------------------------------------------------------

matrix: list[dict[str, Any]] = status.get("matrix", [])
if matrix:
    st.markdown("---")
    st.markdown("## 🔬 学習 × 評価 マトリクス比較")

    train_levels = sorted({c["train_level"] for c in matrix}, key=lambda n: level_names.index(n) if n in level_names else 0)
    eval_levels = sorted({c["eval_level"] for c in matrix}, key=lambda n: level_names.index(n) if n in level_names else 0)
    cell_by_key = {(c["train_level"], c["eval_level"]): c for c in matrix}

    z = [
        [
            (cell_by_key.get((t, e), {}) or {}).get("success_rate")
            for e in eval_levels
        ]
        for t in train_levels
    ]
    text = [
        [
            f"{v * 100:.0f}%" if isinstance(v, (int, float)) else "実行中"
            for v in row
        ]
        for row in z
    ]

    heatmap = go.Figure(
        data=go.Heatmap(
            z=[[v * 100 if isinstance(v, (int, float)) else None for v in row] for row in z],
            x=eval_levels,
            y=train_levels,
            colorscale=_SEQUENTIAL_COLORSCALE,
            zmin=0,
            zmax=100,
            text=text,
            texttemplate="%{text}",
            textfont=dict(size=13),
            colorbar=dict(title="成功率 (%)", ticksuffix="%"),
            hovertemplate="学習=%{y} / 評価=%{x}<br>成功率=%{z:.1f}%<extra></extra>",
        )
    )
    heatmap.update_layout(
        title="学習分布 × 評価分布 の成功率 (%)",
        xaxis_title="評価に使った分布（held-out）",
        yaxis_title="学習に使った分布",
        height=120 + 60 * len(train_levels),
    )
    st.plotly_chart(heatmap, use_container_width=True)

    # Generalization gap: diagonal (in-distribution) minus mean of other eval levels
    gap_rows = []
    for t in train_levels:
        diag = cell_by_key.get((t, t), {}).get("success_rate")
        others = [
            cell_by_key[(t, e)]["success_rate"]
            for e in eval_levels
            if e != t and cell_by_key.get((t, e), {}).get("success_rate") is not None
        ]
        if diag is None or not others:
            continue
        gap = diag - (sum(others) / len(others))
        gap_rows.append((t, gap))

    if gap_rows:
        st.markdown("#### 📉 汎化ギャップ（学習分布での成功率 − 他分布での平均成功率）")
        bar_colors = []
        for _, gap in gap_rows:
            if gap < 0.10:
                bar_colors.append(_STATUS_GOOD)
            elif gap < 0.25:
                bar_colors.append(_STATUS_WARNING)
            else:
                bar_colors.append(_STATUS_CRITICAL)

        gap_fig = go.Figure(
            go.Bar(
                x=[t for t, _ in gap_rows],
                y=[gap * 100 for _, gap in gap_rows],
                marker_color=bar_colors,
                text=[f"{gap * 100:.1f}%" for _, gap in gap_rows],
                textposition="outside",
            )
        )
        gap_fig.update_layout(
            xaxis_title="学習に使った分布",
            yaxis_title="汎化ギャップ (pt)",
            height=350,
            showlegend=False,
        )
        st.plotly_chart(gap_fig, use_container_width=True)
        st.caption(
            f"🟢 <10pt（良好） 🟡 10〜25pt（要注意） 🔴 ≥25pt（学習分布に過学習している可能性）"
        )

    # Final distance histogram overlay for a chosen training level
    st.markdown("#### 📐 最終距離の分布（学習レベルを選んで評価レベル間を比較）")
    chosen_train = st.selectbox("学習レベル", options=train_levels, key="sweep_dist_train_select")
    dist_fig = go.Figure()
    for e in eval_levels:
        cell = cell_by_key.get((chosen_train, e))
        if not cell or not cell.get("final_distances"):
            continue
        dist_fig.add_trace(
            go.Histogram(
                x=cell["final_distances"],
                name=e,
                opacity=0.55,
                nbinsx=30,
                marker_color=_level_color(e, level_names),
            )
        )
    if dist_fig.data:
        dist_fig.update_layout(
            title=f"学習={chosen_train} のモデルを各評価レベルに晒したときの最終距離 (mm)",
            xaxis_title="final_distance (mm)",
            yaxis_title="trial 数",
            barmode="overlay",
            height=380,
        )
        st.plotly_chart(dist_fig, use_container_width=True)
    else:
        st.info("このレベルの評価結果はまだありません。")

# auto refresh while running
if status.get("status") == "running" and st.session_state["sweep_auto_refresh"]:
    time.sleep(3.0)
    st.rerun()
