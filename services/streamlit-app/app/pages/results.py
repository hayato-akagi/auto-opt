from __future__ import annotations

import base64
import binascii
from typing import Any

import streamlit as st

from app.api_client import RecipeApiClient
from app.components.charts import plot_trial_step_charts, render_camera_image, render_spot_heatmap


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
        key="results_experiment_select",
        format_func=lambda exp_id: (
            f"{exp_id} | {id_to_experiment[exp_id]['name']} "
            f"({id_to_experiment[exp_id].get('engine_type', 'KrakenOS')})"
        ),
    )
    st.session_state["selected_experiment_id"] = selected_id
    return selected_id


def _build_step_rows(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in steps:
        command = item.get("command", {})
        sim_pos = item.get("sim_after_position", {})
        sim_bolt = item.get("sim_after_bolt", {})
        rows.append(
            {
                "step_index": item.get("step_index"),
                "coll_x": command.get("coll_x"),
                "coll_y": command.get("coll_y"),
                "torque_upper": command.get("torque_upper"),
                "torque_lower": command.get("torque_lower"),
                "pos_center_x": sim_pos.get("spot_center_x"),
                "pos_center_y": sim_pos.get("spot_center_y"),
                "pos_rms": sim_pos.get("spot_rms_radius"),
                "bolt_center_x": sim_bolt.get("spot_center_x"),
                "bolt_center_y": sim_bolt.get("spot_center_y"),
                "bolt_rms": sim_bolt.get("spot_rms_radius"),
            }
        )
    return rows


def _decode_image(encoded: str | None) -> bytes | None:
    if not encoded:
        return None

    payload = encoded
    if payload.startswith("data:image") and "," in payload:
        payload = payload.split(",", 1)[1]

    try:
        return base64.b64decode(payload)
    except (binascii.Error, ValueError):
        st.error("画像データのデコードに失敗しました")
        return None


def _format_trial(trial: dict[str, Any]) -> str:
    status = "completed" if trial.get("completed") else "running"
    return (
        f"{trial.get('trial_id')} | mode={trial.get('mode')} | "
        f"steps={trial.get('total_steps')} | {status}"
    )


def render(api_client: RecipeApiClient) -> None:
    st.header("結果閲覧")

    experiment_id = _select_experiment(api_client)
    if experiment_id is None:
        return

    # 実験のカメラ設定を取得
    experiment_detail = api_client.get_experiment(experiment_id)
    camera_cfg = (experiment_detail or {}).get("camera") or {}

    trials = api_client.list_trials(experiment_id)
    if trials is None:
        return
    if not trials:
        st.info("この実験に試行がありません")
        return

    trial_ids = [item["trial_id"] for item in trials]
    selected_trial_id = st.session_state.get("selected_trial_id")
    if selected_trial_id not in trial_ids:
        selected_trial_id = trial_ids[-1]

    trial_map = {item["trial_id"]: item for item in trials}
    trial_index = trial_ids.index(selected_trial_id)
    selected_trial_id = st.selectbox(
        "試行",
        options=trial_ids,
        index=trial_index,
        key="results_trial_select",
        format_func=lambda trial_id: _format_trial(trial_map[trial_id]),
    )
    st.session_state["selected_trial_id"] = selected_trial_id

    steps = api_client.list_steps(experiment_id, selected_trial_id)
    if steps is None:
        return

    st.subheader("ステップ一覧")
    if steps:
        st.dataframe(_build_step_rows(steps), use_container_width=True, hide_index=True)
    else:
        st.info("ステップが存在しません")
        return

    st.subheader("ステップ推移グラフ")
    plot_trial_step_charts(steps)

    step_indexes = [int(item.get("step_index", 0)) for item in steps]
    default_step_index = st.session_state.get("results_step_index")
    if default_step_index not in step_indexes:
        default_step_index = step_indexes[-1]

    detail_index = step_indexes.index(default_step_index)
    selected_step_index = st.selectbox(
        "ステップ詳細",
        options=step_indexes,
        index=detail_index,
        key="results_step_select",
    )
    st.session_state["results_step_index"] = selected_step_index

    step_detail = api_client.get_step(experiment_id, selected_trial_id, selected_step_index)
    if step_detail is None:
        return

    st.subheader("スポット像")
    sim_pos = step_detail.get("sim_after_position", {})
    sim_bolt = step_detail.get("sim_after_bolt", {})
    pos_hits = sim_pos.get("ray_hits")
    bolt_hits = sim_bolt.get("ray_hits")

    if pos_hits or bolt_hits:
        hm_left, hm_right = st.columns(2)
        with hm_left:
            render_spot_heatmap(
                "位置調整後",
                pos_hits,
                sim_pos.get("spot_center_x"),
                sim_pos.get("spot_center_y"),
            )
        with hm_right:
            render_spot_heatmap(
                "ボルト締結後",
                bolt_hits,
                sim_bolt.get("spot_center_x"),
                sim_bolt.get("spot_center_y"),
            )

        st.subheader("カメラ像")
        rcam_w = int(camera_cfg.get("pixel_w", 640))
        rcam_h = int(camera_cfg.get("pixel_h", 480))
        rcam_pitch = float(camera_cfg.get("pixel_pitch_um", 5.3))
        rcam_sigma = float(camera_cfg.get("gaussian_sigma_px", 3.0))
        st.caption(
            f"カメラ設定: {rcam_w}×{rcam_h} px, "
            f"ピッチ {rcam_pitch} um, σ {rcam_sigma} px"
        )

        cam_left, cam_right = st.columns(2)
        with cam_left:
            render_camera_image(
                "位置調整後 (カメラ像)",
                pos_hits,
                pixel_w=rcam_w,
                pixel_h=rcam_h,
                pixel_pitch_um=rcam_pitch,
                gaussian_sigma_px=rcam_sigma,
                spot_center_x=sim_pos.get("spot_center_x"),
                spot_center_y=sim_pos.get("spot_center_y"),
            )
        with cam_right:
            render_camera_image(
                "ボルト締結後 (カメラ像)",
                bolt_hits,
                pixel_w=rcam_w,
                pixel_h=rcam_h,
                pixel_pitch_um=rcam_pitch,
                gaussian_sigma_px=rcam_sigma,
                spot_center_x=sim_bolt.get("spot_center_x"),
                spot_center_y=sim_bolt.get("spot_center_y"),
            )
    else:
        st.info(
            "このステップには ray_hits が保存されていません。"
            "手動操作画面から実行した新しいステップにはスポット像が表示されます。"
        )

    st.subheader("ステップ詳細データ")
    st.json(step_detail)

    with st.expander("光路図を取得（optics-sim 再計算）"):
        phase = st.radio(
            "phase",
            options=["after_position", "after_bolt"],
            horizontal=True,
            key="results_image_phase",
        )

        if st.button("光路図を取得"):
            images = api_client.get_step_images(
                experiment_id,
                selected_trial_id,
                selected_step_index,
                phase,
            )
            if images is not None:
                ray_path = _decode_image(images.get("ray_path_image"))
                if ray_path:
                    st.image(ray_path, caption=f"光路図 ({phase})", use_container_width=True)
                else:
                    st.info("光路図を取得できませんでした")
