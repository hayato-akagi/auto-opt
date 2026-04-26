from __future__ import annotations

import json
import math
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from app.api_client import RecipeApiClient
from app.components.inputs import slider_number_input


MM_TO_UM = 1000.0


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
        key="control_experiment_select",
        format_func=lambda exp_id: (
            f"{exp_id} | {id_to_experiment[exp_id]['name']} "
            f"({id_to_experiment[exp_id].get('engine_type', 'KrakenOS')})"
        ),
    )
    st.session_state["selected_experiment_id"] = selected_id
    return selected_id


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_um(value: float | None) -> float | None:
    if value is None:
        return None
    return value * MM_TO_UM


def _list_to_um(values: list[float | None]) -> list[float | None]:
    return [_to_um(v) for v in values]


def _trial_label(trial: dict[str, Any]) -> str:
    status = "completed" if trial.get("completed") else "running"
    return (
        f"{trial.get('trial_id')} | steps={trial.get('total_steps')} | "
        f"{status} | {trial.get('started_at')}"
    )


def _extract_target_and_tolerance(trial_detail: dict[str, Any]) -> tuple[float, float, float | None]:
    control = trial_detail.get("control") or {}
    target = control.get("target") or {}
    target_x = _safe_float(target.get("spot_center_x")) or 0.0
    target_y = _safe_float(target.get("spot_center_y")) or 0.0
    tolerance = _safe_float(control.get("tolerance"))
    return target_x, target_y, tolerance


def _build_series(
    steps: list[dict[str, Any]],
    target_x: float,
    target_y: float,
) -> dict[str, list[float | int | None]]:
    step_indexes: list[int] = []
    loosen_x: list[float | None] = []
    loosen_y: list[float | None] = []
    xy_moved_x: list[float | None] = []
    xy_moved_y: list[float | None] = []
    tightened_x: list[float | None] = []
    tightened_y: list[float | None] = []
    error: list[float | None] = []
    coll_x: list[float | None] = []
    coll_y: list[float | None] = []
    delta_x: list[float | None] = []
    delta_y: list[float | None] = []
    delta_norm: list[float | None] = []

    prev_coll_x: float | None = None
    prev_coll_y: float | None = None

    for item in steps:
        idx = int(item.get("step_index", 0))
        sim_pos = item.get("sim_after_position") or {}
        sim_bolt = item.get("sim_after_bolt") or {}
        command = item.get("command") or {}

        bx = _safe_float(sim_pos.get("spot_center_x"))
        by = _safe_float(sim_pos.get("spot_center_y"))
        ax = _safe_float(sim_bolt.get("spot_center_x"))
        ay = _safe_float(sim_bolt.get("spot_center_y"))
        cx = _safe_float(command.get("coll_x"))
        cy = _safe_float(command.get("coll_y"))

        step_indexes.append(idx)
        xy_moved_x.append(bx)
        xy_moved_y.append(by)
        tightened_x.append(ax)
        tightened_y.append(ay)
        coll_x.append(cx)
        coll_y.append(cy)

        if ax is None or ay is None:
            error.append(None)
        else:
            error.append(math.hypot(target_x - ax, target_y - ay))

        if prev_coll_x is None or prev_coll_y is None or cx is None or cy is None:
            delta_x.append(None)
            delta_y.append(None)
            delta_norm.append(None)
        else:
            dx = cx - prev_coll_x
            dy = cy - prev_coll_y
            delta_x.append(dx)
            delta_y.append(dy)
            delta_norm.append(math.hypot(dx, dy))

        prev_coll_x = cx if cx is not None else prev_coll_x
        prev_coll_y = cy if cy is not None else prev_coll_y

    # 「ボルト緩める」は原則として1つ前stepの観測点を採用。
    # 初回stepのみ参照元がないため、XY位置調整後(before_bolt)を初期値として扱う。
    prev_ax: float | None = None
    prev_ay: float | None = None
    for bx, by, ax, ay in zip(xy_moved_x, xy_moved_y, tightened_x, tightened_y):
        if prev_ax is None or prev_ay is None:
            loosen_x.append(bx)
            loosen_y.append(by)
        else:
            loosen_x.append(prev_ax)
            loosen_y.append(prev_ay)
        if ax is not None and ay is not None:
            prev_ax = ax
            prev_ay = ay

    return {
        "step_indexes": step_indexes,
        "loosen_x": loosen_x,
        "loosen_y": loosen_y,
        "xy_moved_x": xy_moved_x,
        "xy_moved_y": xy_moved_y,
        "tightened_x": tightened_x,
        "tightened_y": tightened_y,
        "error": error,
        "coll_x": coll_x,
        "coll_y": coll_y,
        "delta_x": delta_x,
        "delta_y": delta_y,
        "delta_norm": delta_norm,
    }


def _render_trial_charts(
    title_prefix: str,
    series: dict[str, list[float | int | None]],
    target_x: float,
    target_y: float,
    tolerance: float | None,
    show_target_label: bool,
    show_trial_index: bool,
) -> None:
    traj_fig = go.Figure()

    step_labels = [str(v) for v in series["step_indexes"]] if show_trial_index else None
    loosen_x = _list_to_um(series["loosen_x"])
    loosen_y = _list_to_um(series["loosen_y"])
    xy_moved_x = _list_to_um(series["xy_moved_x"])
    xy_moved_y = _list_to_um(series["xy_moved_y"])
    tightened_x = _list_to_um(series["tightened_x"])
    tightened_y = _list_to_um(series["tightened_y"])
    target_x_um = _to_um(target_x) or 0.0
    target_y_um = _to_um(target_y) or 0.0
    tolerance_um = _to_um(tolerance)

    loosen_to_xy_x: list[float | None] = []
    loosen_to_xy_y: list[float | None] = []
    xy_to_tighten_x: list[float | None] = []
    xy_to_tighten_y: list[float | None] = []

    for lx, ly, bx, by, ax, ay in zip(
        loosen_x,
        loosen_y,
        xy_moved_x,
        xy_moved_y,
        tightened_x,
        tightened_y,
    ):
        if lx is not None and ly is not None and bx is not None and by is not None:
            loosen_to_xy_x.extend([lx, bx, None])
            loosen_to_xy_y.extend([ly, by, None])
        if bx is not None and by is not None and ax is not None and ay is not None:
            xy_to_tighten_x.extend([bx, ax, None])
            xy_to_tighten_y.extend([by, ay, None])

    traj_fig.add_trace(
        go.Scatter(
            x=loosen_to_xy_x,
            y=loosen_to_xy_y,
            mode="lines",
            line=dict(color="rgba(120,120,120,0.8)", width=1.2, dash="dot"),
            name="①ボルト緩める->②XY位置を動かす",
        )
    )
    traj_fig.add_trace(
        go.Scatter(
            x=xy_to_tighten_x,
            y=xy_to_tighten_y,
            mode="lines",
            line=dict(color="rgba(120,120,120,0.6)", width=1.0),
            name="②XY位置を動かす->③ボルト締める",
        )
    )
    traj_fig.add_trace(
        go.Scatter(
            x=loosen_x,
            y=loosen_y,
            mode="markers",
            marker=dict(symbol="triangle-up-open", size=9),
            name="①ボルト緩める",
        )
    )
    traj_fig.add_trace(
        go.Scatter(
            x=xy_moved_x,
            y=xy_moved_y,
            mode="markers",
            marker=dict(symbol="circle-open", size=9),
            name="②XY位置を動かす (before_bolt)",
        )
    )
    traj_fig.add_trace(
        go.Scatter(
            x=tightened_x,
            y=tightened_y,
            mode="markers",
            marker=dict(symbol="square-open", size=9),
            name="③ボルト締める",
        )
    )
    # 試行番号は最終状態(③ボルト締める)に重ねて表示
    if show_trial_index:
        traj_fig.add_trace(
            go.Scatter(
                x=tightened_x,
                y=tightened_y,
                mode="text",
                text=step_labels,
                textposition="bottom center",
                showlegend=False,
                hoverinfo="skip",
            )
        )
    traj_fig.add_trace(
        go.Scatter(
            x=[target_x_um],
            y=[target_y_um],
            mode="markers+text" if show_target_label else "markers",
            text=["Target position"] if show_target_label else None,
            textposition="top right",
            marker=dict(symbol="cross-thin", size=12, line=dict(width=1.0, color="black")),
            name="target",
        )
    )

    if tolerance_um is not None:
        circle_angles = [i * (2.0 * math.pi / 120.0) for i in range(121)]
        circle_x = [target_x_um + tolerance_um * math.cos(a) for a in circle_angles]
        circle_y = [target_y_um + tolerance_um * math.sin(a) for a in circle_angles]
        traj_fig.add_trace(
            go.Scatter(
                x=circle_x,
                y=circle_y,
                mode="lines",
                line=dict(dash="dot"),
                name="tolerance",
            )
        )

    traj_fig.update_layout(
        title=f"{title_prefix}: ①緩める→②XY移動→③締める",
        xaxis_title="spot_center_x [um]",
        yaxis_title="spot_center_y [um]",
        height=420,
    )
    st.plotly_chart(traj_fig, width="stretch")

    err_fig = go.Figure()
    err_fig.add_trace(
        go.Scatter(
            x=series["step_indexes"],
            y=_list_to_um(series["error"]),
            mode="lines+markers",
            name="distance_to_target",
        )
    )
    if tolerance_um is not None:
        err_fig.add_hline(y=tolerance_um, line_dash="dot", annotation_text="tolerance")
    err_fig.update_layout(
        title=f"{title_prefix}: 誤差推移",
        xaxis_title="step",
        yaxis_title="distance [um]",
        height=320,
    )
    st.plotly_chart(err_fig, width="stretch")

    ctrl_fig = go.Figure()
    ctrl_fig.add_trace(
        go.Scatter(
            x=series["step_indexes"],
            y=_list_to_um(series["delta_x"]),
            mode="lines+markers",
            name="delta_coll_x",
        )
    )
    ctrl_fig.add_trace(
        go.Scatter(
            x=series["step_indexes"],
            y=_list_to_um(series["delta_y"]),
            mode="lines+markers",
            name="delta_coll_y",
        )
    )
    ctrl_fig.add_trace(
        go.Scatter(
            x=series["step_indexes"],
            y=_list_to_um(series["delta_norm"]),
            mode="lines+markers",
            name="||delta_coll||",
        )
    )
    ctrl_fig.update_layout(
        title=f"{title_prefix}: 操作量推移",
        xaxis_title="step",
        yaxis_title="delta coll [um]",
        height=320,
    )
    st.plotly_chart(ctrl_fig, width="stretch")


def _render_comparison(
    api_client: RecipeApiClient,
    experiment_id: str,
    preferred_trial_id: str | None,
    show_target_label: bool,
    show_trial_index: bool,
) -> None:
    trials = api_client.list_trials(experiment_id)
    if trials is None:
        return

    control_trials = [item for item in trials if item.get("mode") == "control_loop"]
    st.subheader("保存済み自動実行の比較")
    st.caption("自動実行結果は recipe-service の trial として保存されます")

    if not control_trials:
        st.info("この実験には control_loop の保存済み試行がありません")
        return

    control_trials = sorted(control_trials, key=lambda x: str(x.get("started_at", "")), reverse=True)
    trial_map = {item["trial_id"]: item for item in control_trials if "trial_id" in item}
    trial_ids = list(trial_map.keys())

    default_selected: list[str] = []
    if preferred_trial_id in trial_map:
        default_selected = [preferred_trial_id]
    elif trial_ids:
        default_selected = [trial_ids[0]]

    selected_trial_ids = st.multiselect(
        "比較する trial を選択",
        options=trial_ids,
        default=default_selected,
        format_func=lambda trial_id: _trial_label(trial_map[trial_id]),
        key="control_compare_trials",
    )

    if not selected_trial_ids:
        st.info("比較する trial を1つ以上選択してください")
        return

    summary_rows: list[dict[str, Any]] = []
    export_rows: list[dict[str, Any]] = []

    overlay_traj = go.Figure()
    overlay_err = go.Figure()
    overlay_ctrl = go.Figure()
    tolerance_lines: list[float] = []

    for trial_id in selected_trial_ids:
        detail = api_client.get_trial(experiment_id, trial_id)
        if detail is None:
            continue
        steps = api_client.list_steps(experiment_id, trial_id)
        if steps is None or not steps:
            continue

        target_x, target_y, tolerance = _extract_target_and_tolerance(detail)
        series = _build_series(steps, target_x, target_y)

        step_labels = [str(v) for v in series["step_indexes"]] if show_trial_index else None
        loosen_x = _list_to_um(series["loosen_x"])
        loosen_y = _list_to_um(series["loosen_y"])
        xy_moved_x = _list_to_um(series["xy_moved_x"])
        xy_moved_y = _list_to_um(series["xy_moved_y"])
        tightened_x = _list_to_um(series["tightened_x"])
        tightened_y = _list_to_um(series["tightened_y"])
        target_x_um = _to_um(target_x) or 0.0
        target_y_um = _to_um(target_y) or 0.0
        tolerance_um = _to_um(tolerance)

        loosen_to_xy_x: list[float | None] = []
        loosen_to_xy_y: list[float | None] = []
        xy_to_tighten_x: list[float | None] = []
        xy_to_tighten_y: list[float | None] = []
        for lx, ly, bx, by, ax, ay in zip(
            loosen_x,
            loosen_y,
            xy_moved_x,
            xy_moved_y,
            tightened_x,
            tightened_y,
        ):
            if lx is not None and ly is not None and bx is not None and by is not None:
                loosen_to_xy_x.extend([lx, bx, None])
                loosen_to_xy_y.extend([ly, by, None])
            if bx is not None and by is not None and ax is not None and ay is not None:
                xy_to_tighten_x.extend([bx, ax, None])
                xy_to_tighten_y.extend([by, ay, None])

        overlay_traj.add_trace(
            go.Scatter(
                x=loosen_x,
                y=loosen_y,
                mode="markers",
                marker=dict(symbol="triangle-up-open", size=8),
                name=f"{trial_id} ①緩める",
            )
        )
        overlay_traj.add_trace(
            go.Scatter(
                x=xy_moved_x,
                y=xy_moved_y,
                mode="markers",
                marker=dict(symbol="circle-open", size=8),
                name=f"{trial_id} ②XY移動(before)",
            )
        )
        overlay_traj.add_trace(
            go.Scatter(
                x=tightened_x,
                y=tightened_y,
                mode="markers",
                marker=dict(symbol="square-open", size=8),
                name=f"{trial_id} ③締める",
            )
        )
        if show_trial_index:
            overlay_traj.add_trace(
                go.Scatter(
                    x=tightened_x,
                    y=tightened_y,
                    mode="text",
                    text=step_labels,
                    textposition="bottom center",
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
        overlay_traj.add_trace(
            go.Scatter(
                x=loosen_to_xy_x,
                y=loosen_to_xy_y,
                mode="lines",
                line=dict(width=1.0, dash="dot"),
                name=f"{trial_id} ①->②",
            )
        )
        overlay_traj.add_trace(
            go.Scatter(
                x=xy_to_tighten_x,
                y=xy_to_tighten_y,
                mode="lines",
                line=dict(width=1.0),
                name=f"{trial_id} ②->③",
            )
        )
        overlay_traj.add_trace(
            go.Scatter(
                x=[target_x_um],
                y=[target_y_um],
                mode="markers+text" if show_target_label else "markers",
                text=["Target position"] if show_target_label else None,
                textposition="top right",
                marker=dict(symbol="cross-thin", size=10, line=dict(width=1.0, color="black")),
                name=f"{trial_id}:target",
                showlegend=False,
            )
        )

        overlay_err.add_trace(
            go.Scatter(
                x=series["step_indexes"],
                y=_list_to_um(series["error"]),
                mode="lines+markers",
                name=trial_id,
            )
        )
        overlay_ctrl.add_trace(
            go.Scatter(
                x=series["step_indexes"],
                y=_list_to_um(series["delta_norm"]),
                mode="lines+markers",
                name=trial_id,
            )
        )

        valid_errors = [float(v) for v in series["error"] if v is not None]
        valid_delta_norms = [float(v) for v in series["delta_norm"] if v is not None]
        final_distance = valid_errors[-1] if valid_errors else None
        control_effort = sum(valid_delta_norms) if valid_delta_norms else 0.0

        converged = None
        if tolerance is not None and final_distance is not None:
            converged = final_distance < tolerance
            if tolerance_um is not None:
                tolerance_lines.append(tolerance_um)

        summary_rows.append(
            {
                "trial_id": trial_id,
                "steps": len(series["step_indexes"]),
                "target_x": target_x,
                "target_y": target_y,
                "tolerance": tolerance,
                "final_distance": final_distance,
                "converged": converged,
                "control_effort": control_effort,
            }
        )
        export_rows.append(
            {
                "trial": trial_map[trial_id],
                "detail": detail,
                "summary": summary_rows[-1],
            }
        )

    if not summary_rows:
        st.warning("選択した trial のデータ取得に失敗しました")
        return

    st.dataframe(summary_rows, width="stretch", hide_index=True)

    overlay_traj.update_layout(
        title="軌跡比較 (①緩める→②XY移動→③締める)",
        xaxis_title="spot_center_x [um]",
        yaxis_title="spot_center_y [um]",
        height=420,
    )
    st.plotly_chart(overlay_traj, width="stretch")

    for tol in sorted(set(tolerance_lines)):
        overlay_err.add_hline(y=tol, line_dash="dot", annotation_text=f"tolerance={tol:.1f}um")
    overlay_err.update_layout(
        title="誤差比較",
        xaxis_title="step",
        yaxis_title="distance [um]",
        height=320,
    )
    st.plotly_chart(overlay_err, width="stretch")

    overlay_ctrl.update_layout(
        title="操作量ノルム比較",
        xaxis_title="step",
        yaxis_title="||delta_coll|| [um]",
        height=320,
    )
    st.plotly_chart(overlay_ctrl, width="stretch")

    st.download_button(
        "比較結果(JSON)をダウンロード",
        data=json.dumps(export_rows, ensure_ascii=False, indent=2),
        file_name=f"control-comparison-{experiment_id}.json",
        mime="application/json",
    )


def render(api_client: RecipeApiClient) -> None:
    st.header("制御ループ")
    st.caption(f"SIMPLE_CONTROLLER_URL: {api_client.simple_controller_url}")

    experiment_id = _select_experiment(api_client)
    if experiment_id is None:
        return

    st.subheader("制御設定")
    c1, c2 = st.columns(2)
    with c1:
        target_x = float(
            slider_number_input(
                label="target_spot_center_x (mm)",
                key="control_target_x",
                min_value=-0.2,
                max_value=0.2,
                default=0.0,
                step=0.001,
                value_type="float",
                slider_format="%.3f",
            )
        )
        initial_coll_x = float(
            slider_number_input(
                label="initial_coll_x (mm)",
                key="control_initial_coll_x",
                min_value=-0.5,
                max_value=0.5,
                default=0.0,
                step=0.001,
                value_type="float",
                slider_format="%.3f",
            )
        )
        delta_clip_x = float(
            slider_number_input(
                label="delta_clip_x (mm)",
                key="control_delta_clip_x",
                min_value=0.001,
                max_value=0.2,
                default=0.05,
                step=0.001,
                value_type="float",
                slider_format="%.3f",
            )
        )
        release_std_x = float(
            slider_number_input(
                label="release_perturbation std_x (mm)",
                key="control_release_std_x",
                min_value=0.0,
                max_value=0.05,
                default=0.002,
                step=0.0005,
                value_type="float",
                slider_format="%.4f",
            )
        )

    with c2:
        target_y = float(
            slider_number_input(
                label="target_spot_center_y (mm)",
                key="control_target_y",
                min_value=-0.2,
                max_value=0.2,
                default=0.0,
                step=0.001,
                value_type="float",
                slider_format="%.3f",
            )
        )
        initial_coll_y = float(
            slider_number_input(
                label="initial_coll_y (mm)",
                key="control_initial_coll_y",
                min_value=-0.5,
                max_value=0.5,
                default=0.0,
                step=0.001,
                value_type="float",
                slider_format="%.3f",
            )
        )
        delta_clip_y = float(
            slider_number_input(
                label="delta_clip_y (mm)",
                key="control_delta_clip_y",
                min_value=0.001,
                max_value=0.2,
                default=0.05,
                step=0.001,
                value_type="float",
                slider_format="%.3f",
            )
        )
        release_std_y = float(
            slider_number_input(
                label="release_perturbation std_y (mm)",
                key="control_release_std_y",
                min_value=0.0,
                max_value=0.05,
                default=0.002,
                step=0.0005,
                value_type="float",
                slider_format="%.4f",
            )
        )

    a1, a2, a3 = st.columns(3)
    with a1:
        max_steps = int(
            slider_number_input(
                label="max_steps",
                key="control_max_steps",
                min_value=0,
                max_value=200,
                default=20,
                step=1,
                value_type="int",
                slider_format="%d",
            )
        )
    with a2:
        tolerance = float(
            slider_number_input(
                label="tolerance (mm, default=0.05 = 50µm スポット許容誤差)",
                key="control_tolerance",
                min_value=0.001,
                max_value=0.5,
                default=0.05,
                step=0.001,
                value_type="float",
                slider_format="%.3f",
            )
        )
    with a3:
        random_seed = int(
            slider_number_input(
                label="random_seed",
                key="control_random_seed",
                min_value=0,
                max_value=999999,
                default=42,
                step=1,
                value_type="int",
                slider_format="%d",
            )
        )

    st.subheader("可視化オプション")
    v1, v2 = st.columns(2)
    with v1:
        show_target_label = st.checkbox(
            "Target position ラベル表示",
            value=True,
            key="control_show_target_label",
        )
    with v2:
        show_trial_index = st.checkbox(
            "試行番号ラベル表示",
            value=False,
            key="control_show_trial_index",
        )

    if st.button("自動制御を実行", type="primary"):
        payload = {
            "experiment_id": experiment_id,
            "algorithm": "simple-controller",
            "config": {
                "spot_to_coll_scale_x": 50.0,
                "spot_to_coll_scale_y": 50.0,
                "delta_clip_x": delta_clip_x,
                "delta_clip_y": delta_clip_y,
                "coll_x_min": -0.5,
                "coll_x_max": 0.5,
                "coll_y_min": -0.5,
                "coll_y_max": 0.5,
                "release_perturbation": {
                    "std_x": release_std_x,
                    "std_y": release_std_y,
                },
            },
            "target": {
                "spot_center_x": target_x,
                "spot_center_y": target_y,
            },
            "initial_coll": {
                "coll_x": initial_coll_x,
                "coll_y": initial_coll_y,
            },
            "max_steps": max_steps,
            "tolerance": tolerance,
            "random_seed": random_seed,
        }

        result = api_client.control_run(payload)
        if result is not None:
            st.session_state["control_last_result"] = result
            st.session_state["control_last_request"] = payload
            st.success("自動制御を実行しました")

    last_result = st.session_state.get("control_last_result")
    if last_result:
        st.divider()
        st.subheader("実行結果")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("trial_id", last_result.get("trial_id"))
        r2.metric("converged", str(last_result.get("converged")))
        r3.metric("steps", last_result.get("steps"))
        r4.metric("final_distance", last_result.get("final_distance"))
        st.json(last_result)

        trial_id = str(last_result.get("trial_id", ""))
        if trial_id:
            steps = api_client.list_steps(experiment_id, trial_id)
            if steps:
                target_x = target_x
                target_y = target_y
                tolerance_value = tolerance
                control_request = st.session_state.get("control_last_request") or {}
                target_payload = (control_request.get("target") or {}) if isinstance(control_request, dict) else {}
                target_x = _safe_float(target_payload.get("spot_center_x")) or target_x
                target_y = _safe_float(target_payload.get("spot_center_y")) or target_y
                tolerance_value = _safe_float(control_request.get("tolerance")) or tolerance_value

                st.subheader("最新実行の軌跡")
                series = _build_series(steps, target_x, target_y)
                _render_trial_charts(
                    title_prefix=trial_id,
                    series=series,
                    target_x=target_x,
                    target_y=target_y,
                    tolerance=tolerance_value,
                    show_target_label=show_target_label,
                    show_trial_index=show_trial_index,
                )

    st.divider()
    preferred_trial_id = None
    if isinstance(last_result, dict):
        preferred_trial_id = str(last_result.get("trial_id")) if last_result.get("trial_id") is not None else None
    _render_comparison(
        api_client,
        experiment_id,
        preferred_trial_id,
        show_target_label=show_target_label,
        show_trial_index=show_trial_index,
    )

    with st.expander("利用可能アルゴリズム"):
        algorithms = api_client.control_algorithms()
        if algorithms is not None:
            st.json(algorithms)
