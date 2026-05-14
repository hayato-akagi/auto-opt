from __future__ import annotations

from typing import Any

import math
import plotly.graph_objects as go
import streamlit as st

from app.api_client import RecipeApiClient


def _select_experiment(api_client: RecipeApiClient) -> str | None:
    experiments = api_client.list_experiments()
    if experiments is None:
        return None
    if not experiments:
        st.warning("実験が存在しません。実験管理画面で作成してください")
        st.session_state["selected_experiment_id"] = None
        return None

    experiment_ids = [item["experiment_id"] for item in experiments]
    selected_id = st.session_state.get("selected_experiment_id")
    if selected_id not in experiment_ids:
        selected_id = experiment_ids[0]
    index = experiment_ids.index(selected_id)

    id_to_experiment = {item["experiment_id"]: item for item in experiments}
    selected_id = st.selectbox(
        "実験",
        options=experiment_ids,
        index=index,
        key="ai_control_experiment_select",
        format_func=lambda exp_id: (
            f"{exp_id} | {id_to_experiment[exp_id]['name']} "
            f"({id_to_experiment[exp_id].get('engine_type', 'KrakenOS')})"
        ),
    )
    st.session_state["selected_experiment_id"] = selected_id
    return selected_id


def _build_trial_option(item: dict[str, Any]) -> str:
    status = "completed" if item.get("completed") else "running"
    return f"{item.get('trial_id')} | mode={item.get('mode')} | steps={item.get('total_steps')} | {status}"


def _render_ai_step_log(steps: list[dict[str, Any]]) -> None:
    ai_steps = [s for s in steps if s.get("ai_step_log") is not None]
    if not ai_steps:
        st.info("ai_step_log を持つステップがありません")
        return

    rows = []
    for s in ai_steps:
        log = s.get("ai_step_log") or {}
        baseline_x = log.get("baseline_delta_x")
        baseline_y = log.get("baseline_delta_y")
        residual_x = log.get("dnn_residual_x")
        residual_y = log.get("dnn_residual_y")
        final_norm = None
        if baseline_x is not None and baseline_y is not None and residual_x is not None and residual_y is not None:
            final_norm = math.sqrt((baseline_x + residual_x) ** 2 + (baseline_y + residual_y) ** 2)
        rows.append(
            {
                "step_index": s.get("step_index"),
                "baseline_delta_x": baseline_x,
                "baseline_delta_y": baseline_y,
                "dnn_residual_x": residual_x,
                "dnn_residual_y": residual_y,
                "final_delta_norm": final_norm,
                "safety_triggered": log.get("safety_triggered"),
                "model_version": log.get("model_version"),
            }
        )

    st.dataframe(rows, width="stretch", hide_index=True)

    x = [r["step_index"] for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=[r["baseline_delta_x"] for r in rows], mode="lines+markers", name="baseline_delta_x"))
    fig.add_trace(go.Scatter(x=x, y=[r["dnn_residual_x"] for r in rows], mode="lines+markers", name="dnn_residual_x"))
    fig.add_trace(go.Scatter(x=x, y=[r["baseline_delta_y"] for r in rows], mode="lines+markers", name="baseline_delta_y"))
    fig.add_trace(go.Scatter(x=x, y=[r["dnn_residual_y"] for r in rows], mode="lines+markers", name="dnn_residual_y"))
    fig.update_layout(
        title="AI Step Log (baseline / residual)",
        xaxis_title="step_index",
        yaxis_title="delta (mm)",
        height=360,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig, width="stretch")


def render(api_client: RecipeApiClient) -> None:
    st.header("🤖 AI制御ループ")

    health_ai, _, err_ai = api_client.get_service_health("ai_controller")
    endpoint_ai, _, endpoint_ai_err = api_client.check_endpoint(
        "ai_controller",
        "/control/run",
        method="POST",
        payload={},
    )
    health_simple, _, err_simple = api_client.get_service_health("simple_controller")

    st.subheader("サービス実装状態")
    st.dataframe(
        [
            {
                "service": "ai-controller",
                "health": "ok" if health_ai else "ng",
                "control_run": "available" if endpoint_ai else "not available",
                "note": "health only implementation" if health_ai and not endpoint_ai else (endpoint_ai_err or err_ai or ""),
            },
            {
                "service": "simple-controller",
                "health": "ok" if health_simple else "ng",
                "control_run": "available" if health_simple else "not available",
                "note": err_simple or "",
            },
        ],
        width="stretch",
        hide_index=True,
    )

    experiment_id = _select_experiment(api_client)
    if experiment_id is None:
        return

    st.divider()
    st.subheader("制御実行")

    backend_options = ["simple-controller"]
    if endpoint_ai:
        backend_options.insert(0, "ai-controller")
    backend = st.selectbox("実行バックエンド", backend_options, key="ai_ctrl_backend")

    c1, c2, c3 = st.columns(3)
    with c1:
        target_x = st.number_input("target spot x", value=0.0, step=0.001, format="%.6f")
    with c2:
        target_y = st.number_input("target spot y", value=0.0, step=0.001, format="%.6f")
    with c3:
        tolerance = st.number_input("tolerance", min_value=0.0, value=0.05, step=0.01, format="%.4f")

    c4, c5, c6 = st.columns(3)
    with c4:
        initial_x = st.number_input("initial coll_x", value=0.0, step=0.001, format="%.6f")
    with c5:
        initial_y = st.number_input("initial coll_y", value=0.0, step=0.001, format="%.6f")
    with c6:
        max_steps = st.number_input("max_steps", min_value=1, max_value=200, value=10, step=1)

    payload = {
        "experiment_id": experiment_id,
        "algorithm": backend,
        "config": {
            "spot_to_coll_scale_x": 50.0,
            "spot_to_coll_scale_y": 50.0,
            "delta_clip_x": 0.1,
            "delta_clip_y": 0.1,
            "coll_x_min": -0.5,
            "coll_x_max": 0.5,
            "coll_y_min": -0.5,
            "coll_y_max": 0.5,
            "release_perturbation": {"std_x": 0.0, "std_y": 0.0},
        },
        "target": {"spot_center_x": float(target_x), "spot_center_y": float(target_y)},
        "initial_coll": {"coll_x": float(initial_x), "coll_y": float(initial_y)},
        "max_steps": int(max_steps),
        "tolerance": float(tolerance),
        "random_seed": 42,
    }

    run_key = "ai_control_last_trial_id"
    if st.button("制御ループ実行", type="primary"):
        if backend == "ai-controller":
            result = api_client.run_ai_control(payload)
        else:
            result = api_client.control_run(payload)
        if result:
            trial_id = result.get("trial_id")
            if trial_id:
                st.session_state[run_key] = trial_id
            st.success(f"実行完了: trial_id={trial_id}, converged={result.get('converged')}")
            st.json(result)

    st.divider()
    st.subheader("試行可視化")

    trials = api_client.list_trials(experiment_id) or []
    control_trials = [t for t in trials if t.get("mode") == "control_loop"]
    if not control_trials:
        st.info("control_loop 試行がありません")
        return

    trial_ids = [str(t.get("trial_id")) for t in control_trials if t.get("trial_id")]
    default_trial = st.session_state.get(run_key)
    if default_trial not in trial_ids:
        default_trial = trial_ids[0]
    default_index = trial_ids.index(default_trial)

    selected_trial = st.selectbox(
        "試行",
        options=trial_ids,
        index=default_index,
        format_func=lambda tid: _build_trial_option(next((t for t in control_trials if str(t.get("trial_id")) == tid), {})),
        key="ai_control_trial_select",
    )

    steps = api_client.list_steps(experiment_id, selected_trial) or []
    if not steps:
        st.info("ステップがありません")
        return

    step_rows = []
    for s in steps:
        sim = s.get("sim_after_bolt") or {}
        step_rows.append(
            {
                "step_index": s.get("step_index"),
                "spot_center_x": sim.get("spot_center_x"),
                "spot_center_y": sim.get("spot_center_y"),
                "spot_rms_radius": sim.get("spot_rms_radius"),
                "has_ai_step_log": s.get("ai_step_log") is not None,
            }
        )
    st.dataframe(step_rows, width="stretch", hide_index=True)

    st.markdown("#### ai_step_log")
    _render_ai_step_log(steps)
