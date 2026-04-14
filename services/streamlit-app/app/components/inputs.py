from __future__ import annotations

from typing import Literal

import streamlit as st

ValueType = Literal["float", "int"]


def slider_number_input(
    label: str,
    key: str,
    min_value: float | int,
    max_value: float | int,
    default: float | int,
    step: float | int,
    *,
    value_type: ValueType = "float",
    slider_format: str | None = None,
) -> float | int:
    state_key = f"{key}__value"
    slider_key = f"{key}__slider"
    number_key = f"{key}__number"

    if value_type == "int":
        min_value = int(min_value)
        max_value = int(max_value)
        default = int(default)
        step = int(step)
        if slider_format is None:
            slider_format = "%d"
    else:
        min_value = float(min_value)
        max_value = float(max_value)
        default = float(default)
        step = float(step)
        if slider_format is None:
            slider_format = "%.3f"

    if state_key not in st.session_state:
        st.session_state[state_key] = default
    if slider_key not in st.session_state:
        st.session_state[slider_key] = st.session_state[state_key]
    if number_key not in st.session_state:
        st.session_state[number_key] = st.session_state[state_key]

    def _sync_from_slider() -> None:
        value = st.session_state[slider_key]
        if value_type == "int":
            value = int(value)
        else:
            value = float(value)
        st.session_state[state_key] = value
        st.session_state[number_key] = value

    def _sync_from_number() -> None:
        value = st.session_state[number_key]
        if value_type == "int":
            value = int(round(value))
        else:
            value = float(value)

        if value < min_value:
            value = min_value
        if value > max_value:
            value = max_value

        st.session_state[state_key] = value
        st.session_state[slider_key] = value
        st.session_state[number_key] = value

    slider_col, number_col = st.columns([3, 2])
    with slider_col:
        st.slider(
            label,
            min_value=min_value,
            max_value=max_value,
            step=step,
            key=slider_key,
            format=slider_format,
            on_change=_sync_from_slider,
        )
    with number_col:
        st.number_input(
            f"{label} numeric",
            min_value=min_value,
            max_value=max_value,
            step=step,
            key=number_key,
            format=slider_format,
            label_visibility="collapsed",
            on_change=_sync_from_number,
        )

    return st.session_state[state_key]
