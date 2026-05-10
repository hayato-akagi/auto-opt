from __future__ import annotations

import os
from collections.abc import Callable

import streamlit as st

from app.api_client import RecipeApiClient
from app.pages import control, experiment, manual, results, sweep, ai_control, collection, training, model_store

PageRenderer = Callable[[RecipeApiClient], None]

PAGES: dict[str, PageRenderer] = {
    "✅ 実験管理": experiment.render,
    "✅ 手動操作": manual.render,
    "✅ スイープ": sweep.render,
    "✅ 結果閲覧": results.render,
    "✅ 制御ループ": control.render,
    "🚧 AI制御": ai_control.render,
    "🚧 データ収集": collection.render,
    "🚧 トレーニング": training.render,
    "🚧 モデルストア": model_store.render,
}


@st.cache_resource
def get_api_client() -> RecipeApiClient:
    return RecipeApiClient(
        base_url=os.getenv("RECIPE_SERVICE_URL", "http://recipe-service:8002")
    )


def _initialize_state() -> None:
    st.session_state.setdefault("selected_experiment_id", None)
    st.session_state.setdefault("selected_trial_id", None)


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

    page_name = st.sidebar.radio("ページ", options=list(PAGES.keys()))
    PAGES[page_name](api_client)


if __name__ == "__main__":
    main()
