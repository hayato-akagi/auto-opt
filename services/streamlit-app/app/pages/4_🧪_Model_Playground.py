"""ページ4: 保存済みモデルを使った推論プレイグラウンド

過去のパイプラインで保存された .pt モデルを選択し、
ai-controller で複数試行を実行して挙動を確認する。
"""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.api_client import RecipeApiClient

st.set_page_config(
    page_title="モデルプレイグラウンド",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 モデルプレイグラウンド")
st.markdown(
    """
保存済みの学習モデル (`.pt`) を選んで、任意の実験 / 目標スポットに対して
**ai-controller** で推論を走らせ、収束軌跡や成功率を確認します。

- モデルは **🧬 パイプライン** で生成されたものを自動収集します
- 任意で `model_path` を手入力することも可能です
"""
)


def _client() -> RecipeApiClient:
    if "api_client" not in st.session_state:
        st.session_state["api_client"] = RecipeApiClient()
    return st.session_state["api_client"]


# ---------------------------------------------------------------------------
# Discover available models from completed pipelines
# ---------------------------------------------------------------------------

def _collect_models_from_pipelines(client: RecipeApiClient) -> list[dict[str, Any]]:
    """Walk completed pipelines and pull (pipeline_id, gen_id, model_path)."""
    pipelines = client.list_pipelines() or []
    models: list[dict[str, Any]] = []
    for p in pipelines:
        pid = p.get("pipeline_id")
        exp_id = p.get("experiment_id")
        for g in p.get("generations", []) or []:
            mp = g.get("model_path")
            if not mp:
                continue
            models.append({
                "label": f"{pid} / gen{g.get('gen_id')} (loss={g.get('final_train_loss')})",
                "model_path": mp,
                "pipeline_id": pid,
                "gen_id": g.get("gen_id"),
                "experiment_id": exp_id,
                "n_history": (p.get("config") or {}).get("model_config_train", {}).get("n_history"),
            })
    return models


client = _client()

with st.sidebar:
    st.markdown("## 🎯 モデル選択")
    if st.button("🔄 モデル一覧を更新", use_container_width=True):
        st.session_state.pop("_playground_models", None)

    models = st.session_state.get("_playground_models")
    if models is None:
        models = _collect_models_from_pipelines(client)
        st.session_state["_playground_models"] = models

    if models:
        labels = [m["label"] for m in models]
        idx = st.selectbox("保存済みモデル", range(len(models)), format_func=lambda i: labels[i])
        selected = models[idx]
        st.caption(f"path: `{selected['model_path']}`")
    else:
        st.info("利用可能なモデルがありません。🧬 パイプラインを実行してください。")
        selected = None

    manual_path = st.text_input(
        "🛠 model_path を手入力 (任意)",
        value="",
        help="一覧にない .pt を直接使う場合 (例: /data/models/<job_id>.pt)",
    )
    model_path = manual_path.strip() or (selected["model_path"] if selected else "")

    st.markdown("---")
    st.markdown("## 🔬 実験 / 目標")
    default_exp = (selected or {}).get("experiment_id") or st.session_state.get("last_experiment_id", "")
    experiment_id = st.text_input("experiment_id", value=default_exp)
    target_x = st.number_input("target X (mm)", value=0.0, step=0.05, format="%.3f")
    target_y = st.number_input("target Y (mm)", value=0.0, step=0.05, format="%.3f")
    init_x = st.number_input("initial coll_x (mm)", value=0.0, step=0.05, format="%.3f")
    init_y = st.number_input("initial coll_y (mm)", value=0.0, step=0.05, format="%.3f")

    st.markdown("---")
    st.markdown("## ⚙️ 推論設定")
    controller_choice = st.radio(
        "コントローラー",
        ["ai-controller (MLP)", "lstm-controller (LSTM)"],
        index=0,
        help="モデルの種類に合わせて選択してください。",
    )
    use_lstm = controller_choice.startswith("lstm")
    default_n_hist = (selected or {}).get("n_history") or 3
    n_history = st.slider(
        "n_history",
        1, 10, int(default_n_hist),
        disabled=use_lstm,
        help="LSTM では使用しません",
    )
    n_trials = st.slider("試行回数", 1, 100, 10)
    max_steps = st.slider("最大ステップ", 1, 50, 10)
    tolerance = st.number_input(
        "収束許容 (mm)", value=0.001, min_value=0.0001, step=0.0001, format="%.4f"
    )
    base_seed = st.number_input("乱数 seed (base)", value=0, step=1)


# ---------------------------------------------------------------------------
# Run inference
# ---------------------------------------------------------------------------

st.subheader("▶️ 実行")

run_disabled = not (model_path and experiment_id.strip())
if st.button("🚀 推論実行", type="primary", disabled=run_disabled, use_container_width=False):
    if use_lstm:
        algorithm = "lstm-controller"
        config_payload: dict[str, Any] = {
            "model_type": "lstm",
            "model_path": model_path,
        }
    else:
        algorithm = "ai-controller"
        config_payload = {
            "model_type": "mlp",
            "model_path": model_path,
            "n_history": int(n_history),
        }

    payloads = []
    for i in range(int(n_trials)):
        payloads.append({
            "experiment_id": experiment_id.strip(),
            "algorithm": algorithm,
            "config": config_payload,
            "target": {"spot_center_x": float(target_x), "spot_center_y": float(target_y)},
            "initial_coll": {"coll_x": float(init_x), "coll_y": float(init_y)},
            "max_steps": int(max_steps),
            "tolerance": float(tolerance),
            "random_seed": int(base_seed) + i,
        })

    results: list[dict[str, Any]] = []
    progress = st.progress(0.0, text="実行中...")
    for i, pl in enumerate(payloads):
        r = client.run_lstm_control(pl) if use_lstm else client.run_ai_control(pl)
        if r:
            results.append(r)
        progress.progress((i + 1) / len(payloads), text=f"{i+1}/{len(payloads)} 完了")
    progress.empty()
    st.session_state["_playground_results"] = results
    st.session_state["_playground_target"] = (float(target_x), float(target_y))

results = st.session_state.get("_playground_results") or []
target = st.session_state.get("_playground_target") or (0.0, 0.0)

if not results:
    st.info("実行結果はまだありません。サイドバーで設定して **🚀 推論実行** を押してください。")
    st.stop()

# ---------------------------------------------------------------------------
# Summarize results
# ---------------------------------------------------------------------------

st.subheader("📊 結果サマリー")

df = pd.DataFrame([
    {
        "trial": i,
        "converged": r.get("converged"),
        "steps": r.get("steps"),
        "final_distance": r.get("final_distance"),
        "final_x": r.get("final_spot_center_x"),
        "final_y": r.get("final_spot_center_y"),
        "model_version": r.get("model_version"),
    }
    for i, r in enumerate(results)
])

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("成功率", f"{df['converged'].mean() * 100:.1f}%")
with c2:
    st.metric("平均 steps", f"{df['steps'].mean():.2f}")
with c3:
    st.metric("平均 final_distance (mm)", f"{df['final_distance'].mean():.4f}")
with c4:
    st.metric("最大 final_distance (mm)", f"{df['final_distance'].max():.4f}")

st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Visualizations
# ---------------------------------------------------------------------------

st.subheader("🎯 最終スポット分布")

tx, ty = target
fig_scatter = go.Figure()
fig_scatter.add_trace(go.Scatter(
    x=df["final_x"],
    y=df["final_y"],
    mode="markers",
    marker=dict(
        size=10,
        color=df["converged"].map({True: "green", False: "red"}),
        line=dict(width=1, color="black"),
    ),
    text=[f"trial {i}<br>steps={s}<br>dist={d:.4f}"
          for i, s, d in zip(df["trial"], df["steps"], df["final_distance"])],
    hoverinfo="text",
    name="final spots",
))
fig_scatter.add_trace(go.Scatter(
    x=[tx], y=[ty], mode="markers",
    marker=dict(size=18, symbol="cross", color="red", line=dict(width=3, color="red")),
    name="target",
))
# tolerance circle
theta = np.linspace(0, 2 * np.pi, 64)
fig_scatter.add_trace(go.Scatter(
    x=tx + tolerance * np.cos(theta),
    y=ty + tolerance * np.sin(theta),
    mode="lines",
    line=dict(color="blue", dash="dot"),
    name=f"tolerance ({tolerance} mm)",
))
fig_scatter.update_layout(
    xaxis_title="X (mm)", yaxis_title="Y (mm)",
    yaxis=dict(scaleanchor="x", scaleratio=1),
    height=500,
)
st.plotly_chart(fig_scatter, use_container_width=True)

col_a, col_b = st.columns(2)
with col_a:
    st.markdown("#### 収束ステップ数のヒストグラム")
    fig_steps = go.Figure(go.Histogram(x=df["steps"], nbinsx=int(max_steps) + 1))
    fig_steps.update_layout(xaxis_title="steps", yaxis_title="trial 数", height=300)
    st.plotly_chart(fig_steps, use_container_width=True)
with col_b:
    st.markdown("#### 最終距離のヒストグラム (mm)")
    fig_dist = go.Figure(go.Histogram(x=df["final_distance"], nbinsx=30))
    fig_dist.add_vline(x=tolerance, line_color="red", line_dash="dot",
                       annotation_text=f"tol={tolerance}")
    fig_dist.update_layout(xaxis_title="final_distance", yaxis_title="trial 数", height=300)
    st.plotly_chart(fig_dist, use_container_width=True)
