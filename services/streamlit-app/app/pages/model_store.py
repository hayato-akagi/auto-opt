from __future__ import annotations

from typing import Any

import streamlit as st

from app.api_client import RecipeApiClient


def _extract_model_rows(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for m in models:
        bm = m.get("benchmark_metrics") or {}
        rows.append(
            {
                "version": m.get("version"),
                "model_type": m.get("model_type"),
                "status": m.get("status"),
                "median_final_error_mm": bm.get("median_final_error_mm") or bm.get("median_error_mm"),
                "p95_final_error_mm": bm.get("p95_final_error_mm"),
                "converge_rate": bm.get("converge_rate"),
                "train_job_id": m.get("train_job_id"),
                "created_at": m.get("created_at"),
                "promoted_at": m.get("promoted_at"),
            }
        )
    return rows


def render(api_client: RecipeApiClient) -> None:
    st.header("🏪 モデルストア")

    health_ok, _, health_err = api_client.get_service_health("model_store")
    if health_ok:
        st.success("Model Store Service: healthy")
    else:
        st.error(f"Model Store Service に接続できません: {health_err}")
        return

    st.subheader("モデル一覧")
    models = api_client.get_models() or []
    if not models:
        st.info("登録済みモデルはありません")
    else:
        st.dataframe(_extract_model_rows(models), width="stretch", hide_index=True)

    st.divider()
    st.subheader("モデル詳細")

    versions = [str(m.get("version")) for m in models if m.get("version")]
    if versions:
        selected_version = st.selectbox("version", options=versions, key="model_store_version")
        detail = api_client.get_model(selected_version)
        if detail:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("status", str(detail.get("status", "-")))
            with c2:
                st.metric("model_type", str(detail.get("model_type", "-")))
            with c3:
                st.metric("train_job_id", str(detail.get("train_job_id", "-")))

            bm = detail.get("benchmark_metrics") or {}
            if bm:
                st.markdown("#### benchmark_metrics")
                st.dataframe([bm], width="stretch", hide_index=True)

            st.markdown("#### Raw JSON")
            st.json(detail)

            promote_col, _ = st.columns([1, 3])
            with promote_col:
                if st.button("このモデルを current に昇格", key="promote_model_button"):
                    promoted = api_client.promote_model(selected_version, {"version": selected_version})
                    if promoted:
                        st.success(
                            f"昇格完了: {promoted.get('version')} -> {promoted.get('new_status')}"
                        )
                        st.rerun()
    else:
        st.info("詳細表示できる version がありません")

    st.divider()
    st.subheader("モデル登録（手動）")
    with st.form("model_register_form"):
        version = st.text_input("version", value="v1.0.0")
        model_type = st.selectbox("model_type", ["mlp", "baseline_only"], index=0)
        status = st.selectbox("status", ["candidate", "current", "archived"], index=0)
        train_job_id = st.text_input("train_job_id", value="train_job_manual")
        created_at = st.text_input("created_at", value="2026-05-11T00:00:00Z")
        submit_register = st.form_submit_button("モデル登録")

    if submit_register:
        payload = {
            "version": version.strip(),
            "model_type": model_type,
            "status": status,
            "benchmark_metrics": {"median_error_mm": 0.05},
            "benchmark_trial_ids": [],
            "benchmark_experiment_ids": [],
            "train_job_id": train_job_id.strip() or None,
            "created_at": created_at.strip(),
        }
        result = api_client.register_model(payload)
        if result:
            st.success(f"モデル登録完了: {result.get('version')}")
            st.rerun()
