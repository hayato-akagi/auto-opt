"""Shared rendering for a single generation-pipeline's status.

Extracted from pages/2_🧬_Generation_Pipeline.py so the same dashboard
(top summary + per-generation charts) can also be embedded in
pages/5_🧭_Generalization_Sweep.py to show the level currently being trained.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_pipeline_status_header(status: dict) -> None:
    """Top summary row + progress bar + error callouts for a pipeline status dict."""
    top1, top2, top3, top4 = st.columns(4)
    with top1:
        st.metric("ステータス", status.get("status", "?"))
    with top2:
        st.metric("世代", f"{status.get('current_generation', 0)} / {status.get('total_generations', 0)}")
    with top3:
        st.metric("進捗", f"{status.get('progress', 0.0) * 100:.1f}%")
    with top4:
        st.metric("開始", str(status.get("started_at", ""))[:19])

    st.progress(float(status.get("progress", 0.0) or 0.0))

    if status.get("error"):
        st.error(f"パイプラインエラー: {status['error']}")

    for g in status.get("generations", []):
        if g.get("status") == "failed" and g.get("error"):
            with st.expander(f"🔴 Gen{g['gen_id']} エラー詳細", expanded=True):
                st.code(g["error"], language="text")


def render_generation_dashboard(status: dict, key_prefix: str = "pipeline") -> None:
    """Generations table + success/loss chart + per-generation detail charts.

    key_prefix must be unique per call site on a page so widget keys (multiselect,
    radio) don't collide if this is rendered more than once in the same run.
    """
    generations = status.get("generations", [])
    if not generations:
        st.info("まだ世代結果がありません。")
        return

    df = pd.DataFrame(generations)
    if "final_train_loss" in df.columns:
        df["rmse_um"] = df["final_train_loss"].apply(
            lambda v: round(math.sqrt(max(v, 0)) * 1000, 3) if v is not None else None
        )
    cols = [
        "gen_id", "status", "controller",
        "total_trials", "converged_trials", "success_rate",
        "rmse_um", "train_job_id", "model_path",
        "started_at", "finished_at", "error",
    ]
    df = df[[c for c in cols if c in df.columns]]
    st.dataframe(df, use_container_width=True, hide_index=True)

    # success rate over generations
    if "success_rate" in df.columns and df["success_rate"].notna().any():
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=df["gen_id"],
                y=df["success_rate"] * 100,
                mode="lines+markers",
                name="合格率 (%)",
                line=dict(color="blue", width=3),
            )
        )
        if "final_train_loss" in df.columns and df["final_train_loss"].notna().any():
            fig.add_trace(
                go.Scatter(
                    x=df["gen_id"],
                    y=df["final_train_loss"].apply(lambda v: math.sqrt(max(v, 0)) * 1000 if v is not None else None),
                    mode="lines+markers",
                    name="RMSE (μm)",
                    yaxis="y2",
                    line=dict(color="red", width=2, dash="dot"),
                )
            )
        fig.update_layout(
            title="世代ごとの合格率と学習ロス",
            xaxis_title="世代",
            yaxis=dict(title="合格率 (%)", side="left", range=[0, 100]),
            yaxis2=dict(title="RMSE (μm)", overlaying="y", side="right"),
            hovermode="x unified",
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- Detailed per-generation metrics ---
    st.markdown("#### 🔬 世代別 詳細メトリクス")
    gens_with_data = [
        g for g in generations
        if g.get("steps_per_trial") or g.get("final_distances") or g.get("epoch_losses")
    ]
    if not gens_with_data:
        return

    # Steps per trial box plot
    box_fig = go.Figure()
    for g in gens_with_data:
        steps = g.get("steps_per_trial") or []
        if steps:
            box_fig.add_trace(go.Box(y=steps, name=f"gen{g['gen_id']}", boxmean=True))
    if box_fig.data:
        box_fig.update_layout(
            title="trial 収束ステップ数の分布",
            yaxis_title="steps",
            xaxis_title="世代",
            height=350,
        )
        st.plotly_chart(box_fig, use_container_width=True)

    # Final distance histogram
    dist_fig = go.Figure()
    for g in gens_with_data:
        dists = g.get("final_distances") or []
        if dists:
            dist_fig.add_trace(
                go.Histogram(
                    x=dists,
                    name=f"gen{g['gen_id']}",
                    opacity=0.6,
                    nbinsx=30,
                )
            )
    if dist_fig.data:
        dist_fig.update_layout(
            title="最終距離の分布 (mm)",
            xaxis_title="final_distance (mm)",
            yaxis_title="trial 数",
            barmode="overlay",
            height=350,
        )
        st.plotly_chart(dist_fig, use_container_width=True)

    # Epoch loss curves (RMSE in μm) — interactive controls
    gens_with_loss = [g for g in gens_with_data if g.get("epoch_losses")]
    if gens_with_loss:
        st.markdown("##### 📉 エポック毎の学習ロス (RMSE)")
        ctrl_col1, ctrl_col2 = st.columns([3, 1])
        with ctrl_col1:
            all_gen_ids = [g["gen_id"] for g in gens_with_loss]
            selected_gen_ids = st.multiselect(
                "表示する世代",
                options=all_gen_ids,
                default=all_gen_ids,
                format_func=lambda g: f"Gen {g}",
                key=f"{key_prefix}_loss_curve_gen_select",
            )
        with ctrl_col2:
            y_scale = st.radio(
                "Y軸スケール",
                options=["対数", "線形"],
                index=0,
                horizontal=True,
                key=f"{key_prefix}_loss_curve_scale",
            )

        loss_fig = go.Figure()
        for g in gens_with_loss:
            if g["gen_id"] not in selected_gen_ids:
                continue
            losses = g.get("epoch_losses") or []
            rmse_um = [math.sqrt(max(l, 0)) * 1000 for l in losses]
            loss_fig.add_trace(
                go.Scatter(
                    x=list(range(1, len(rmse_um) + 1)),
                    y=rmse_um,
                    mode="lines",
                    name=f"Gen {g['gen_id']}",
                )
            )
        if loss_fig.data:
            loss_fig.add_hline(
                y=1.0,
                line_dash="dash",
                line_color="green",
                annotation_text="目標: 1 μm",
                annotation_position="bottom right",
            )
            loss_fig.update_layout(
                xaxis_title="epoch",
                yaxis_title="RMSE (μm)",
                yaxis_type="log" if y_scale == "対数" else "linear",
                hovermode="x unified",
                height=380,
                margin=dict(t=20),
            )
            st.plotly_chart(loss_fig, use_container_width=True)
