from __future__ import annotations

from typing import Any

import streamlit as st

from app.api_client import RecipeApiClient


def _build_trial_label(item: dict[str, Any]) -> str:
    status = "completed" if item.get("completed") else "running"
    return (
        f"{item.get('trial_id')} | mode={item.get('mode')} | "
        f"steps={item.get('total_steps')} | {status}"
    )


def _collect_data_stats(api_client: RecipeApiClient, experiment_id: str, trial_id: str) -> dict[str, Any] | None:
    steps = api_client.list_steps(experiment_id, trial_id)
    if steps is None:
        return None

    ai_log_count = 0
    bolt_count = 0
    for s in steps:
        if s.get("ai_step_log") is not None:
            ai_log_count += 1
        if s.get("bolt_shift") is not None:
            bolt_count += 1

    return {
        "step_count": len(steps),
        "with_ai_step_log": ai_log_count,
        "with_bolt_shift": bolt_count,
    }


def render(api_client: RecipeApiClient) -> None:
    st.header("📊 データ収集")

    h_collection, _, err_collection = api_client.get_service_health("collection_orchestrator")
    h_simple, _, err_simple = api_client.get_service_health("simple_controller")
    h_recipe = api_client.list_experiments() is not None

    status_rows = [
        {
            "service": "collection-orchestrator",
            "health": "ok" if h_collection else "ng",
            "note": "jobs API 実装が必要" if h_collection else f"{err_collection}",
        },
        {
            "service": "simple-controller",
            "health": "ok" if h_simple else "ng",
            "note": "control/run 利用可" if h_simple else f"{err_simple}",
        },
        {
            "service": "recipe-service",
            "health": "ok" if h_recipe else "ng",
            "note": "実験/試行/ステップ取得" if h_recipe else "experiments API failed",
        },
    ]
    st.subheader("サービス実装状態")
    st.dataframe(status_rows, width="stretch", hide_index=True)

    st.divider()
    st.subheader("収集ジョブ管理")

    if h_collection and h_simple and h_recipe:
        experiments_for_job = api_client.list_experiments() or []
        exp_ids_for_job = [str(x.get("experiment_id")) for x in experiments_for_job if x.get("experiment_id")]
        if exp_ids_for_job:
            with st.form("collection_job_create_form"):
                selected_exp_for_job = st.selectbox("experiment_id", exp_ids_for_job, key="collection_job_exp")
                seeds_text = st.text_input("seeds (comma separated)", value="1,2,3,4,5")
                algorithm = st.selectbox("algorithm", ["simple-controller", "ai-controller"], index=0)
                max_steps = st.number_input("max_steps", min_value=1, max_value=200, value=10, step=1)
                tolerance = st.number_input("tolerance", min_value=0.0001, value=0.05, step=0.01, format="%.4f")
                max_workers = st.number_input("max_workers", min_value=1, max_value=32, value=4, step=1)
                submit_job = st.form_submit_button("収集ジョブ作成", type="primary")

            if submit_job:
                raw_seeds = [x.strip() for x in seeds_text.split(",") if x.strip()]
                try:
                    seeds = [int(x) for x in raw_seeds]
                except ValueError:
                    st.error("seeds は整数のカンマ区切りで入力してください")
                    seeds = []

                if not seeds:
                    st.warning("seeds を1つ以上指定してください")
                else:
                    job_payload = {
                        "algorithm": algorithm,
                        "controller_config": {
                            "spot_to_coll_scale_x": 50.0,
                            "spot_to_coll_scale_y": 50.0,
                            "delta_clip_x": 0.1,
                            "delta_clip_y": 0.1,
                            "coll_x_min": -0.5,
                            "coll_x_max": 0.5,
                            "coll_y_min": -0.5,
                            "coll_y_max": 0.5,
                        },
                        "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
                        "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
                        "max_steps": int(max_steps),
                        "tolerance": float(tolerance),
                        "tasks": [{"experiment_id": selected_exp_for_job, "seeds": seeds}],
                        "max_workers": int(max_workers),
                    }
                    created = api_client.start_collection_job(job_payload)
                    if created:
                        st.success(
                            f"ジョブ作成: {created.get('job_id')} status={created.get('status')} total_tasks={created.get('total_tasks')}"
                        )

        jobs = api_client.get_collection_jobs() or []
        if jobs:
            st.markdown("#### ジョブ一覧")
            st.dataframe(jobs, width="stretch", hide_index=True)

            job_ids = [str(j.get("job_id")) for j in jobs if j.get("job_id")]
            if job_ids:
                selected_job_id = st.selectbox("詳細表示する job_id", job_ids, key="collection_job_detail_select")
                detail = api_client.get_collection_job_status(selected_job_id)
                if detail:
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("status", str(detail.get("status", "-")))
                    with c2:
                        st.metric("completed_tasks", int(detail.get("completed_tasks", 0)))
                    with c3:
                        st.metric("failed_tasks", int(detail.get("failed_tasks", 0)))
                    with st.expander("job detail JSON", expanded=False):
                        st.json(detail)
        else:
            st.info("収集ジョブはまだありません")
    else:
        st.info("collection-orchestrator / simple-controller / recipe-service が揃うとジョブ管理UIが有効になります")

    st.divider()
    st.subheader("収集データ可視化（Recipe Service ベース）")

    experiments = api_client.list_experiments() or []
    if not experiments:
        st.info("実験がありません")
        return

    exp_ids = [str(x.get("experiment_id")) for x in experiments if x.get("experiment_id")]
    selected_exp = st.selectbox("実験", exp_ids, key="collection_exp_select")

    trials = api_client.list_trials(selected_exp) or []
    if not trials:
        st.info("試行がありません")
        return

    trial_ids = [str(x.get("trial_id")) for x in trials if x.get("trial_id")]
    selected_trial = st.selectbox(
        "試行",
        trial_ids,
        key="collection_trial_select",
        format_func=lambda t: _build_trial_label(next((x for x in trials if str(x.get("trial_id")) == t), {})),
    )

    stats = _collect_data_stats(api_client, selected_exp, selected_trial)
    if stats is None:
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("steps", stats["step_count"])
    with c2:
        st.metric("steps with ai_step_log", stats["with_ai_step_log"])
    with c3:
        st.metric("steps with bolt_shift", stats["with_bolt_shift"])

    steps = api_client.list_steps(selected_exp, selected_trial) or []
    if steps:
        sample_rows = []
        for s in steps:
            ai_log = s.get("ai_step_log") or {}
            sample_rows.append(
                {
                    "step_index": s.get("step_index"),
                    "coll_x": (s.get("command") or {}).get("coll_x"),
                    "coll_y": (s.get("command") or {}).get("coll_y"),
                    "has_ai_step_log": s.get("ai_step_log") is not None,
                    "model_version": ai_log.get("model_version"),
                    "safety_triggered": ai_log.get("safety_triggered"),
                }
            )
        st.dataframe(sample_rows, width="stretch", hide_index=True)
