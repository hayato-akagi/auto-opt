from __future__ import annotations

from typing import Any

import streamlit as st

from app.api_client import RecipeApiClient
from app.components.charts import plot_sweep_charts
from app.components.inputs import slider_number_input

SWEEP_DEFAULTS = {
    "coll_x": {"start": -0.1, "stop": 0.1, "step": 0.01},
    "coll_y": {"start": -0.1, "stop": 0.1, "step": 0.01},
}


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
        key="sweep_experiment_select",
        format_func=lambda exp_id: (
            f"{exp_id} | {id_to_experiment[exp_id]['name']} "
            f"({id_to_experiment[exp_id].get('engine_type', 'KrakenOS')})"
        ),
    )
    st.session_state["selected_experiment_id"] = selected_id
    return selected_id


def _build_values(start: float, stop: float, step: float) -> list[float] | None:
    if step == 0:
        st.error("step は 0 以外を指定してください")
        return None

    if (stop - start) * step < 0:
        st.error("start, stop, step の符号関係が不正です")
        return None

    values: list[float] = []
    current = start
    tolerance = abs(step) * 1e-8 + 1e-12

    if step > 0:
        while current <= stop + tolerance:
            values.append(round(current, 10))
            current += step
    else:
        while current >= stop - tolerance:
            values.append(round(current, 10))
            current += step

    if not values:
        st.error("スイープ値を生成できませんでした")
        return None

    if len(values) > 5000:
        st.error("スイープ点が多すぎます。5000 点以下にしてください")
        return None

    return values


def _build_result_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in results:
        pos = item.get("sim_after_position", {})
        bolt = item.get("sim_after_bolt", {})
        rows.append(
            {
                "step_index": item.get("step_index"),
                "param_value": item.get("param_value"),
                "pos_center_x": pos.get("spot_center_x"),
                "pos_center_y": pos.get("spot_center_y"),
                "pos_rms": pos.get("spot_rms_radius"),
                "pos_vignetting": pos.get("vignetting_ratio"),
                "bolt_center_x": bolt.get("spot_center_x"),
                "bolt_center_y": bolt.get("spot_center_y"),
                "bolt_rms": bolt.get("spot_rms_radius"),
                "bolt_vignetting": bolt.get("vignetting_ratio"),
            }
        )
    return rows


def render(api_client: RecipeApiClient) -> None:
    st.header("スイープ")

    experiment_id = _select_experiment(api_client)
    if experiment_id is None:
        return

    st.subheader("ベースパラメータ")
    coll_x = float(
        slider_number_input(
            label="coll_x (mm)",
            key="sweep_coll_x",
            min_value=-0.5,
            max_value=0.5,
            default=0.0,
            step=0.001,
            value_type="float",
            slider_format="%.3f",
        )
    )
    coll_y = float(
        slider_number_input(
            label="coll_y (mm)",
            key="sweep_coll_y",
            min_value=-0.5,
            max_value=0.5,
            default=0.0,
            step=0.001,
            value_type="float",
            slider_format="%.3f",
        )
    )
    st.subheader("スイープ設定")
    param_name = st.selectbox(
        "対象パラメータ",
        options=["coll_x", "coll_y"],
        key="sweep_param_name",
    )

    default_range = SWEEP_DEFAULTS[param_name]
    range_col1, range_col2, range_col3 = st.columns(3)
    with range_col1:
        start = float(
            st.number_input(
                "start",
                value=float(default_range["start"]),
                step=float(default_range["step"]),
                key="sweep_range_start",
            )
        )
    with range_col2:
        stop = float(
            st.number_input(
                "stop",
                value=float(default_range["stop"]),
                step=float(default_range["step"]),
                key="sweep_range_stop",
            )
        )
    with range_col3:
        step = float(
            st.number_input(
                "step",
                value=float(default_range["step"]),
                step=float(default_range["step"]),
                min_value=-10.0,
                max_value=10.0,
                key="sweep_range_step",
            )
        )

    if st.button("スイープ実行", type="primary"):
        sweep_values = _build_values(start, stop, step)
        if sweep_values is None:
            return

        payload = {
            "experiment_id": experiment_id,
            "base_command": {
                "coll_x": coll_x,
                "coll_y": coll_y,
            },
            "sweep": {
                "param_name": param_name,
                "values": sweep_values,
            },
        }
        result = api_client.run_sweep(payload)
        if result is not None:
            st.session_state["sweep_last_result"] = result
            st.session_state["sweep_last_experiment_id"] = experiment_id
            st.session_state["selected_trial_id"] = result.get("trial_id")
            st.success(f"スイープ完了: trial_id={result.get('trial_id')}")

    last_result = st.session_state.get("sweep_last_result")
    if not last_result:
        return

    st.divider()
    st.subheader("スイープ結果")
    st.caption(
        f"trial_id={last_result.get('trial_id')} | sweep_param={last_result.get('sweep_param')}"
    )

    results = last_result.get("results", [])
    if isinstance(results, list) and results:
        st.dataframe(_build_result_rows(results), use_container_width=True, hide_index=True)
        plot_sweep_charts(results, str(last_result.get("sweep_param", param_name)))
    else:
        st.info("表示可能なスイープ結果がありません")
