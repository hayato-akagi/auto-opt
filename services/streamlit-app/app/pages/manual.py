from __future__ import annotations

from typing import Any

import streamlit as st

from app.api_client import RecipeApiClient
from app.components.charts import render_camera_image, render_sim_metrics, render_spot_heatmap
from app.components.inputs import slider_number_input


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
        key="manual_experiment_select",
        format_func=lambda exp_id: f"{exp_id} | {id_to_experiment[exp_id]['name']}",
    )
    st.session_state["selected_experiment_id"] = selected_id
    return selected_id


def _format_trial(item: dict[str, Any]) -> str:
    status = "completed" if item.get("completed") else "running"
    return (
        f"{item.get('trial_id')} | mode={item.get('mode')} | "
        f"steps={item.get('total_steps')} | {status}"
    )


def render(api_client: RecipeApiClient) -> None:
    st.header("手動操作")

    experiment_id = _select_experiment(api_client)
    if experiment_id is None:
        return

    st.caption(f"選択中の実験: {experiment_id}")

    # 実験のカメラ設定を取得
    experiment_detail = api_client.get_experiment(experiment_id)
    camera_cfg = (experiment_detail or {}).get("camera") or {}

    trials = api_client.list_trials(experiment_id)
    if trials is None:
        trials = []

    st.subheader("試行管理")
    if trials:
        st.dataframe(trials, use_container_width=True, hide_index=True)
    else:
        st.info("この実験にはまだ試行がありません")

    action_col1, action_col2 = st.columns(2)
    with action_col1:
        if st.button("新規試行開始", type="primary"):
            created = api_client.create_trial(experiment_id, mode="manual", control=None)
            if created is not None:
                st.session_state["selected_trial_id"] = created.get("trial_id")
                st.success(f"試行を開始しました: {created.get('trial_id')}")
                st.rerun()
    with action_col2:
        if st.button("試行一覧を更新"):
            st.rerun()

    selected_trial_id: str | None = None
    if trials:
        trial_ids = [item["trial_id"] for item in trials]
        default_trial_id = st.session_state.get("selected_trial_id")
        if default_trial_id not in trial_ids:
            default_trial_id = trial_ids[-1]
        index = trial_ids.index(default_trial_id)

        trial_map = {item["trial_id"]: item for item in trials}
        selected_trial_id = st.selectbox(
            "試行選択",
            options=trial_ids,
            index=index,
            key="manual_trial_select",
            format_func=lambda trial_id: _format_trial(trial_map[trial_id]),
        )
        st.session_state["selected_trial_id"] = selected_trial_id

    st.divider()
    st.subheader("ステップ実行")

    coll_x = float(
        slider_number_input(
            label="coll_x (mm)",
            key="manual_coll_x",
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
            key="manual_coll_y",
            min_value=-0.5,
            max_value=0.5,
            default=0.0,
            step=0.001,
            value_type="float",
            slider_format="%.3f",
        )
    )
    torque_upper = float(
        slider_number_input(
            label="torque_upper (N.m)",
            key="manual_torque_upper",
            min_value=0.0,
            max_value=2.0,
            default=0.5,
            step=0.01,
            value_type="float",
            slider_format="%.2f",
        )
    )
    torque_lower = float(
        slider_number_input(
            label="torque_lower (N.m)",
            key="manual_torque_lower",
            min_value=0.0,
            max_value=2.0,
            default=0.5,
            step=0.01,
            value_type="float",
            slider_format="%.2f",
        )
    )

    run_col, complete_col = st.columns(2)
    with run_col:
        if st.button("実行", type="primary", disabled=selected_trial_id is None):
            result = api_client.execute_step(
                experiment_id,
                selected_trial_id or "",
                coll_x=coll_x,
                coll_y=coll_y,
                torque_upper=torque_upper,
                torque_lower=torque_lower,
                return_ray_hits=True,
                return_images=False,
            )
            if result is not None:
                st.session_state["manual_last_step_result"] = result
                st.session_state["manual_last_step_trial_id"] = selected_trial_id
                st.success(f"ステップ {result.get('step_index')} を実行しました")

    with complete_col:
        if st.button("試行完了", disabled=selected_trial_id is None):
            summary = api_client.complete_trial(experiment_id, selected_trial_id or "")
            if summary is not None:
                st.success(
                    f"試行を完了しました: total_steps={summary.get('total_steps')}"
                )
                st.session_state.pop("manual_last_step_result", None)
                st.rerun()

    last_result = st.session_state.get("manual_last_step_result")
    last_trial_id = st.session_state.get("manual_last_step_trial_id")

    if last_result and selected_trial_id and selected_trial_id == last_trial_id:
        st.divider()
        st.subheader("結果表示")

        left_col, right_col = st.columns(2)
        with left_col:
            render_sim_metrics("位置調整後", last_result.get("sim_after_position", {}))
            st.caption("after_position")
            st.json(last_result.get("after_position", {}))

        with right_col:
            render_sim_metrics("ボルト締結後", last_result.get("sim_after_bolt", {}))
            st.caption("after_bolt")
            st.json(last_result.get("after_bolt", {}))

        bolt_shift = last_result.get("bolt_shift", {})
        st.markdown("#### ボルトずれ情報")
        b1, b2 = st.columns(2)
        b1.metric("delta_x", bolt_shift.get("delta_x"))
        b2.metric("delta_y", bolt_shift.get("delta_y"))

        st.divider()
        st.subheader("スポット像")
        hm_left, hm_right = st.columns(2)
        sim_pos = last_result.get("sim_after_position", {})
        sim_bolt = last_result.get("sim_after_bolt", {})
        with hm_left:
            render_spot_heatmap(
                "位置調整後",
                sim_pos.get("ray_hits"),
                sim_pos.get("spot_center_x"),
                sim_pos.get("spot_center_y"),
            )
        with hm_right:
            render_spot_heatmap(
                "ボルト締結後",
                sim_bolt.get("ray_hits"),
                sim_bolt.get("spot_center_x"),
                sim_bolt.get("spot_center_y"),
            )

        st.divider()
        st.subheader("カメラ像")
        cam_w = int(camera_cfg.get("pixel_w", 640))
        cam_h = int(camera_cfg.get("pixel_h", 480))
        cam_pitch = float(camera_cfg.get("pixel_pitch_um", 5.3))
        cam_sigma = float(camera_cfg.get("gaussian_sigma_px", 3.0))
        st.caption(
            f"カメラ設定: {cam_w}×{cam_h} px, "
            f"ピッチ {cam_pitch} um, σ {cam_sigma} px"
        )

        cam_left, cam_right = st.columns(2)
        with cam_left:
            render_camera_image(
                "位置調整後 (カメラ像)",
                sim_pos.get("ray_hits"),
                pixel_w=cam_w,
                pixel_h=cam_h,
                pixel_pitch_um=cam_pitch,
                gaussian_sigma_px=cam_sigma,
                spot_center_x=sim_pos.get("spot_center_x"),
                spot_center_y=sim_pos.get("spot_center_y"),
            )
        with cam_right:
            render_camera_image(
                "ボルト締結後 (カメラ像)",
                sim_bolt.get("ray_hits"),
                pixel_w=cam_w,
                pixel_h=cam_h,
                pixel_pitch_um=cam_pitch,
                gaussian_sigma_px=cam_sigma,
                spot_center_x=sim_bolt.get("spot_center_x"),
                spot_center_y=sim_bolt.get("spot_center_y"),
            )
