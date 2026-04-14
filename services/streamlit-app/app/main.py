from __future__ import annotations

import os
from collections.abc import Callable

import streamlit as st

from app.api_client import RecipeApiClient
from app.pages import control, experiment, manual, results, sweep

PageRenderer = Callable[[RecipeApiClient], None]

PAGES: dict[str, PageRenderer] = {
    "実験管理": experiment.render,
    "手動操作": manual.render,
    "スイープ": sweep.render,
    "結果閲覧": results.render,
    "制御ループ": control.render,
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
    st.sidebar.caption("Recipe Service only")
    st.sidebar.caption(f"RECIPE_SERVICE_URL: {api_client.base_url}")

    page_name = st.sidebar.radio("ページ", options=list(PAGES.keys()))
    PAGES[page_name](api_client)


if __name__ == "__main__":
    main()
