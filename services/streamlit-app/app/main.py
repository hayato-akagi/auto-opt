from __future__ import annotations

import os
from collections.abc import Callable

import streamlit as st

from app.api_client import RecipeApiClient
from app.pages import experiment, manual_confirmation, model_creation, results

PageRenderer = Callable[[RecipeApiClient], None]

# Task-based workflow screens
SCREENS: dict[str, PageRenderer] = {
    "1️⃣ 実験作成": experiment.render,
    "2️⃣ 手動確認": manual_confirmation.render,
    "3️⃣ モデル学習": model_creation.render,
    "4️⃣ 結果比較": results.render,
}


@st.cache_resource
def get_api_client() -> RecipeApiClient:
    return RecipeApiClient(
        base_url=os.getenv("RECIPE_SERVICE_URL", "http://recipe-service:8002")
    )


def _initialize_state() -> None:
    """Initialize session state for task-based workflow"""
    st.session_state.setdefault("selected_experiment_id", None)
    st.session_state.setdefault("selected_trial_id", None)
    st.session_state.setdefault("current_model_version", None)
    st.session_state.setdefault("collection_job_id", None)


def _render_context_header(api_client: RecipeApiClient) -> None:
    """Render persistent context header showing current experiment and model"""
    exp_id = st.session_state.get("selected_experiment_id")
    model_ver = st.session_state.get("current_model_version")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if exp_id:
            st.caption(f"📋 **実験**: {exp_id}")
        else:
            st.caption("📋 **実験**: 未選択")
    with col2:
        if model_ver:
            st.caption(f"🧠 **モデル版**: {model_ver}")
        else:
            st.caption("🧠 **モデル版**: 未学習")
    st.divider()


def main() -> None:
    st.set_page_config(page_title="auto-opt streamlit-app", layout="wide")
    _initialize_state()

    api_client = get_api_client()

    st.sidebar.title("auto-opt")
    st.sidebar.markdown("---")
    st.sidebar.caption("🔌 **接続サービス**")
    st.sidebar.caption(f"📋 Recipe: {api_client.base_url}")
    st.sidebar.caption(f"⚡ Controller: {api_client.simple_controller_url}")
    st.sidebar.caption(f"🧠 Trainer: {api_client.trainer_url}")
    st.sidebar.caption(f"🏪 Model Store: {api_client.model_store_url}")
    st.sidebar.caption(f"🤖 AI Controller: {api_client.ai_controller_url}")
    st.sidebar.caption(f"📊 Collection: {api_client.collection_orchestrator_url}")
    st.sidebar.markdown("---")

    screen_name = st.sidebar.radio("タスク型ワークフロー", options=list(SCREENS.keys()))
    
    # Render context header on main area
    _render_context_header(api_client)
    
    # Render selected screen
    SCREENS[screen_name](api_client)


if __name__ == "__main__":
    main()
