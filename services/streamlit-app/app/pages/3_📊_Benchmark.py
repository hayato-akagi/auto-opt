"""ページ3: ベンチマーク比較

orchestrator が管理するパイプラインから世代結果を取得し、合格率の推移や
ハイパーパラメータ相関を可視化する。
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.api_client import RecipeApiClient

st.set_page_config(
    page_title="ベンチマーク比較",
    page_icon="📊",
    layout="wide",
)

st.title("📊 ベンチマーク & 比較分析")


def _client() -> RecipeApiClient:
    if "api_client" not in st.session_state:
        st.session_state["api_client"] = RecipeApiClient()
    return st.session_state["api_client"]


# ---------------------------------------------------------------------------
# Fetch pipelines
# ---------------------------------------------------------------------------

if st.button("🔄 更新"):
    st.session_state.pop("_pipelines_cache", None)

pipelines = st.session_state.get("_pipelines_cache")
if pipelines is None:
    pipelines = _client().list_pipelines() or []
    st.session_state["_pipelines_cache"] = pipelines

if not pipelines:
    st.info(
        "パイプラインがまだ存在しません。\n\n"
        "**🧬 世代交代パイプライン** ページから少なくとも1つ実行してください。"
    )
    st.stop()


# ---------------------------------------------------------------------------
# Per-pipeline summary table
# ---------------------------------------------------------------------------

summary_rows: list[dict] = []
for p in pipelines:
    gens = p.get("generations") or []
    success_rates = [g.get("success_rate") for g in gens if g.get("success_rate") is not None]
    final_sr = success_rates[-1] if success_rates else None
    best_sr = max(success_rates) if success_rates else None
    losses = [g.get("final_train_loss") for g in gens if g.get("final_train_loss") is not None]
    final_loss = losses[-1] if losses else None

    summary_rows.append({
        "pipeline_id": p.get("pipeline_id"),
        "experiment_id": p.get("experiment_id"),
        "status": p.get("status"),
        "completed_generations": len([g for g in gens if g.get("status") == "completed"]),
        "total_generations": p.get("total_generations"),
        "final_success_rate(%)": round(final_sr * 100, 1) if final_sr is not None else None,
        "best_success_rate(%)": round(best_sr * 100, 1) if best_sr is not None else None,
        "final_train_loss": round(final_loss, 6) if final_loss is not None else None,
        "started_at": p.get("started_at", "")[:19],
    })

summary_df = pd.DataFrame(summary_rows)

st.subheader("🏆 パイプライン リーダーボード")
st.dataframe(
    summary_df.sort_values("best_success_rate(%)", ascending=False, na_position="last"),
    use_container_width=True,
    hide_index=True,
)


# ---------------------------------------------------------------------------
# Per-pipeline comparison
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("📈 世代ごとの合格率推移（重ね書き）")

selected_ids = st.multiselect(
    "比較するパイプライン",
    options=[p["pipeline_id"] for p in pipelines],
    default=[p["pipeline_id"] for p in pipelines[:5]],
)

if selected_ids:
    fig = go.Figure()
    for p in pipelines:
        if p["pipeline_id"] not in selected_ids:
            continue
        gens = p.get("generations") or []
        gen_ids = [g["gen_id"] for g in gens if g.get("success_rate") is not None]
        rates = [g["success_rate"] * 100 for g in gens if g.get("success_rate") is not None]
        if gen_ids:
            fig.add_trace(go.Scatter(
                x=gen_ids, y=rates,
                mode="lines+markers",
                name=p["pipeline_id"],
            ))
    fig.update_layout(
        xaxis_title="世代",
        yaxis_title="合格率 (%)",
        yaxis=dict(range=[0, 100]),
        hovermode="x unified",
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Generation-level long table for correlation
# ---------------------------------------------------------------------------

long_rows: list[dict] = []
for p in pipelines:
    pid = p["pipeline_id"]
    for g in (p.get("generations") or []):
        if g.get("success_rate") is None:
            continue
        long_rows.append({
            "pipeline_id": pid,
            "gen_id": g.get("gen_id"),
            "controller": g.get("controller"),
            "success_rate": g.get("success_rate"),
            "total_trials": g.get("total_trials"),
            "converged_trials": g.get("converged_trials"),
            "final_train_loss": g.get("final_train_loss"),
        })

if long_rows:
    long_df = pd.DataFrame(long_rows)

    st.markdown("---")
    st.subheader("🔗 世代特徴量の相関")

    numeric_cols = ["gen_id", "success_rate", "total_trials", "converged_trials", "final_train_loss"]
    available = [c for c in numeric_cols if c in long_df.columns and long_df[c].notna().any()]
    if len(available) >= 2:
        corr = long_df[available].corr()
        fig_corr = px.imshow(
            corr,
            text_auto=".2f",
            color_continuous_scale="RdBu_r",
            zmin=-1, zmax=1,
            title="相関係数（符号保持）",
        )
        st.plotly_chart(fig_corr, use_container_width=True)
    else:
        st.info("相関計算に十分なデータがありません。")
