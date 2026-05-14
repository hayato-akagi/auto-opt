from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import streamlit as st

from app.api_client import RecipeApiClient


def _select_experiments(api_client: RecipeApiClient) -> list[str]:
    experiments = api_client.list_experiments() or []
    if not experiments:
        st.warning("学習対象の実験がありません。先に『実験管理』から作成してください。")
        return []

    labels: dict[str, str] = {
        str(exp.get("experiment_id")): (
            f"{exp.get('experiment_id')} | {exp.get('name')} "
            f"({exp.get('engine_type', 'KrakenOS')})"
        )
        for exp in experiments
    }
    options = list(labels.keys())
    selected = st.multiselect(
        "学習対象の実験ID",
        options=options,
        default=options[:1],
        format_func=lambda x: labels[x],
        key="training_experiment_ids",
    )
    return [str(x) for x in selected]


def _render_train_metrics(train_metrics: dict[str, Any] | None) -> None:
    if not train_metrics:
        st.info("train_metrics はまだありません")
        return

    epoch_losses = train_metrics.get("epoch_losses") or []
    final_loss = train_metrics.get("final_train_loss")
    epochs = train_metrics.get("epochs")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("epochs", f"{epochs}" if epochs is not None else "-")
    with c2:
        st.metric("final_train_loss", f"{float(final_loss):.6f}" if final_loss is not None else "-")
    with c3:
        st.metric("loss points", len(epoch_losses))

    if epoch_losses:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=list(range(1, len(epoch_losses) + 1)),
                y=epoch_losses,
                mode="lines+markers",
                name="epoch_losses",
                line=dict(color="#1f77b4", width=2),
            )
        )
        fig.update_layout(
            title="学習損失推移",
            xaxis_title="Epoch",
            yaxis_title="Loss",
            height=300,
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.plotly_chart(fig, width="stretch")


def _render_benchmark_results(benchmark_results: dict[str, Any] | None) -> None:
    if not benchmark_results:
        st.info("benchmark_results はまだありません")
        return

    new_model = benchmark_results.get("new_model") or {}
    current_model = benchmark_results.get("current_model") or {}

    rows = [
        {
            "metric": "median_final_error_mm",
            "new_model": new_model.get("median_final_error_mm"),
            "current_model": current_model.get("median_final_error_mm"),
        },
        {
            "metric": "p95_final_error_mm",
            "new_model": new_model.get("p95_final_error_mm"),
            "current_model": current_model.get("p95_final_error_mm"),
        },
        {
            "metric": "converge_rate",
            "new_model": new_model.get("converge_rate"),
            "current_model": current_model.get("converge_rate"),
        },
    ]
    st.dataframe(rows, width="stretch", hide_index=True)

    fig = go.Figure()
    labels = ["median_final_error_mm", "p95_final_error_mm", "converge_rate"]
    fig.add_trace(
        go.Bar(
            name="new_model",
            x=labels,
            y=[new_model.get("median_final_error_mm"), new_model.get("p95_final_error_mm"), new_model.get("converge_rate")],
            marker_color="#2ca02c",
        )
    )
    fig.add_trace(
        go.Bar(
            name="current_model",
            x=labels,
            y=[current_model.get("median_final_error_mm"), current_model.get("p95_final_error_mm"), current_model.get("converge_rate")],
            marker_color="#ff7f0e",
        )
    )
    fig.update_layout(
        barmode="group",
        title="ベンチマーク比較",
        height=320,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig, width="stretch")


def render(api_client: RecipeApiClient) -> None:
    st.header("🧠 トレーニング")

    health_ok, _, health_err = api_client.get_service_health("trainer")
    if health_ok:
        st.success("Trainer Service: healthy")
    else:
        st.error(f"Trainer Service に接続できません: {health_err}")
        return

    st.subheader("学習ジョブ開始")
    with st.form("training_start_form"):
        experiment_ids = _select_experiments(api_client)
        model_type = st.selectbox("model_type", ["mlp", "baseline_only"], index=0)
        epochs = st.number_input("epochs", min_value=1, max_value=500, value=50, step=1)
        batch_size = st.number_input("batch_size", min_value=1, max_value=256, value=32, step=1)
        submitted = st.form_submit_button("学習開始", type="primary")

    if submitted:
        if not experiment_ids:
            st.warning("experiment_ids を1件以上選択してください")
        else:
            response = api_client.start_training(
                {
                    "experiment_ids": experiment_ids,
                    "model_type": model_type,
                    "epochs": int(epochs),
                    "batch_size": int(batch_size),
                }
            )
            if response:
                st.success(f"ジョブ開始: {response.get('train_job_id')} ({response.get('status')})")

    st.divider()
    st.subheader("トレーニングジョブ一覧")

    jobs = api_client.get_training_jobs() or []
    if not jobs:
        st.info("トレーニングジョブはありません")
        return

    st.dataframe(jobs, width="stretch", hide_index=True)

    job_ids = [str(j.get("train_job_id", "")) for j in jobs if j.get("train_job_id")]
    if not job_ids:
        st.warning("ジョブIDを持つデータがありません")
        return

    selected_job_id = st.selectbox("詳細表示するジョブ", job_ids, key="training_selected_job_id")
    detail = api_client.get_training_job_status(selected_job_id)
    if not detail:
        return

    st.subheader("ジョブ詳細")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("status", str(detail.get("status", "-")))
    with c2:
        st.metric("promoted", str(detail.get("promoted", "-")))
    with c3:
        st.metric("promoted_version", str(detail.get("promoted_version", "-")))

    st.markdown("#### Train Metrics")
    _render_train_metrics(detail.get("train_metrics"))

    st.markdown("#### Benchmark Results")
    _render_benchmark_results(detail.get("benchmark_results"))

    with st.expander("Raw JSON", expanded=False):
        st.json(detail)
