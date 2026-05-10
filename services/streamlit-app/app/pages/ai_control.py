from __future__ import annotations

from typing import Any

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


def render(api_client: RecipeApiClient) -> None:
    st.header("🤖 AI制御ループ")
    st.warning("🚧 この機能はまだ実装中です (stub)")
    
    experiment_id = _select_experiment(api_client)
    if experiment_id is None:
        return

    st.info(
        "DNNベースのフィードバック制御を実行します。\n\n"
        "このページでは以下の機能が実装予定です:\n"
        "- 学習済みモデルの選択\n"
        "- 制御ループのパラメータ設定\n"
        "- DNN推論結果と実際の挙動の比較\n"
        "- ai_step_log の可視化"
    )
    
    st.divider()
    st.subheader("機能予定")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **実装予定の機能**
        - モデル選択ウィジェット
        - 制御パラメータ (target_x, target_y, tolerance)
        - オプション設定 (max_steps, perturbation)
        """)
    
    with col2:
        st.markdown("""
        **可視化予定**
        - DNN推論ログ (dnn_residual_x/y)
        - ベースラインΔ との比較 (baseline_delta_x/y)
        - 安全トリガー状態表示
        - ステップごとのモデルバージョン追跡
        """)
