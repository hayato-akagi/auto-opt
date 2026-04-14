from __future__ import annotations

import streamlit as st

from app.api_client import RecipeApiClient


def render(_: RecipeApiClient) -> None:
    st.header("制御ループ")
    st.info("Coming Soon")
