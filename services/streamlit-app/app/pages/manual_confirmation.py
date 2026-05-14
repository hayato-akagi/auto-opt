"""
Manual Confirmation Screen (Screen 2)

Combined manual stepping + baseline controller runs.
Allows users to:
1. Manually verify baseline behavior step-by-step
2. Run full baseline control loops for reference
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from app.api_client import RecipeApiClient
from app.components.charts import render_camera_image, render_sim_metrics, render_spot_heatmap
from app.components.inputs import slider_number_input


def _select_experiment(api_client: RecipeApiClient) -> str | None:
    """Select or load experiment from context"""
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
        "実験選択",
        options=experiment_ids,
        index=index,
        key="manual_conf_experiment_select",
        format_func=lambda exp_id: (
            f"{exp_id} | {id_to_experiment[exp_id]['name']} "
            f"({id_to_experiment[exp_id].get('engine_type', 'KrakenOS')})"
        ),
    )
    st.session_state["selected_experiment_id"] = selected_id
    return selected_id


def _format_trial(item: dict[str, Any]) -> str:
    status = "完了" if item.get("completed") else "実行中"
    return (
        f"{item.get('trial_id')} | モード={item.get('mode')} | "
        f"ステップ数={item.get('total_steps')} | {status}"
    )


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _render_manual_stepping(
    api_client: RecipeApiClient,
    experiment_id: str,
    experiment_detail: dict[str, Any],
) -> None:
    """Render manual stepping interface"""
    st.subheader("📍 手動確認")
    st.caption("ベースライン コントローラーの動作を手動で確認します")

    trials = api_client.list_trials(experiment_id)
    if trials is None:
        trials = []

    # Trial management
    col1, col2 = st.columns(2)
    with col1:
        if st.button("新規試行を開始", type="primary", key="manual_new_trial"):
            created = api_client.create_trial(experiment_id, mode="manual", control=None)
            if created is not None:
                st.session_state["selected_trial_id"] = created.get("trial_id")
                st.success(f"試行を開始しました: {created.get('trial_id')}")
                st.rerun()
    with col2:
        if st.button("試行一覧を更新", key="manual_refresh"):
            st.rerun()

    # Show active trials
    if trials:
        st.caption(f"アクティブな試行: {len(trials)}")
        st.dataframe(trials, width="stretch", hide_index=True, use_container_width=True)

    selected_trial_id: str | None = None
    if trials:
        trial_ids = [item["trial_id"] for item in trials]
        default_trial_id = st.session_state.get("selected_trial_id")
        if default_trial_id not in trial_ids:
            default_trial_id = trial_ids[-1]
        index = trial_ids.index(default_trial_id)

        trial_map = {item["trial_id"]: item for item in trials}
        selected_trial_id = st.selectbox(
            "対象試行",
            options=trial_ids,
            index=index,
            key="manual_trial_select",
            format_func=lambda trial_id: _format_trial(trial_map[trial_id]),
        )
        st.session_state["selected_trial_id"] = selected_trial_id

    st.divider()

    # Manual step control
    st.markdown("#### ステップ入力")
    step_col1, step_col2 = st.columns(2)
    
    with step_col1:
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
    with step_col2:
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

    run_col, complete_col = st.columns(2)
    with run_col:
        if st.button("ステップを実行", type="primary", disabled=selected_trial_id is None):
            result = api_client.execute_step(
                experiment_id,
                selected_trial_id or "",
                coll_x=coll_x,
                coll_y=coll_y,
                return_ray_hits=True,
                return_images=False,
            )
            if result is not None:
                st.session_state["manual_last_step_result"] = result
                st.session_state["manual_last_step_trial_id"] = selected_trial_id
                st.success(f"ステップ {result.get('step_index')} を実行しました")

    with complete_col:
        if st.button("試行を完了", disabled=selected_trial_id is None):
            summary = api_client.complete_trial(experiment_id, selected_trial_id or "")
            if summary is not None:
                st.success(
                    f"試行を完了しました: 計{summary.get('total_steps')}ステップ"
                )
                st.session_state.pop("manual_last_step_result", None)
                st.rerun()

    # Display last step result
    last_result = st.session_state.get("manual_last_step_result")
    last_trial_id = st.session_state.get("manual_last_step_trial_id")

    if last_result and selected_trial_id and selected_trial_id == last_trial_id:
        st.divider()
        st.markdown("#### ステップ実行結果")

        # Metrics
        left_col, right_col = st.columns(2)
        with left_col:
            render_sim_metrics("位置調整後", last_result.get("sim_after_position", {}))
        with right_col:
            render_sim_metrics("ボルト締結後", last_result.get("sim_after_bolt", {}))

        # Bolt shift metrics
        bolt_shift = last_result.get("bolt_shift", {})
        st.markdown("**ボルトずれ情報**")
        b1, b2, b3 = st.columns(3)
        b1.metric("delta_x (mm)", f"{bolt_shift.get('delta_x', 0.0):.6f}")
        b2.metric("delta_y (mm)", f"{bolt_shift.get('delta_y', 0.0):.6f}")
        norm = (bolt_shift.get('delta_x', 0.0) ** 2 + bolt_shift.get('delta_y', 0.0) ** 2) ** 0.5
        b3.metric("norm (mm)", f"{norm:.6f}")

        st.divider()
        st.markdown("#### スポット像")
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

        # Camera rendering
        camera_cfg = (experiment_detail or {}).get("camera") or {}
        cam_w = int(camera_cfg.get("pixel_w", 640))
        cam_h = int(camera_cfg.get("pixel_h", 480))
        cam_pitch = float(camera_cfg.get("pixel_pitch_um", 5.3))
        cam_sigma = float(camera_cfg.get("gaussian_sigma_px", 3.0))

        st.divider()
        st.markdown("#### カメラ像")
        st.caption(
            f"設定: {cam_w}×{cam_h} px, ピッチ {cam_pitch} um, σ {cam_sigma} px"
        )

        cam_left, cam_right = st.columns(2)
        with cam_left:
            render_camera_image(
                "位置調整後",
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
                "ボルト締結後",
                sim_bolt.get("ray_hits"),
                pixel_w=cam_w,
                pixel_h=cam_h,
                pixel_pitch_um=cam_pitch,
                gaussian_sigma_px=cam_sigma,
                spot_center_x=sim_bolt.get("spot_center_x"),
                spot_center_y=sim_bolt.get("spot_center_y"),
            )


def _render_baseline_controller(
    api_client: RecipeApiClient,
    experiment_id: str,
    experiment_detail: dict[str, Any],
) -> None:
    """Render baseline controller run interface"""
    st.subheader("📈 ベースラインコントローラー実行")
    st.caption("自動制御ループを実行してベースラインの性能を検証します")

    # Get target and tolerance from experiment
    config = (experiment_detail or {}).get("optical_config") or {}
    target_x = _safe_float(config.get("target_x")) or 0.0
    target_y = _safe_float(config.get("target_y")) or 0.0
    
    st.markdown("#### 制御パラメータ")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        target_x = float(
            slider_number_input(
                label="Target X (mm)",
                key="baseline_target_x",
                min_value=-0.5,
                max_value=0.5,
                default=target_x,
                step=0.01,
                value_type="float",
                slider_format="%.2f",
            )
        )
    with col2:
        target_y = float(
            slider_number_input(
                label="Target Y (mm)",
                key="baseline_target_y",
                min_value=-0.5,
                max_value=0.5,
                default=target_y,
                step=0.01,
                value_type="float",
                slider_format="%.2f",
            )
        )
    with col3:
        tolerance = float(
            slider_number_input(
                label="Tolerance (mm)",
                key="baseline_tolerance",
                min_value=0.001,
                max_value=0.5,
                default=0.05,
                step=0.01,
                value_type="float",
                slider_format="%.3f",
            )
        )
    with col4:
        max_steps = int(
            slider_number_input(
                label="Max Steps",
                key="baseline_max_steps",
                min_value=1,
                max_value=100,
                default=10,
                step=1,
                value_type="int",
                slider_format="%d",
            )
        )

    st.markdown("#### クリップ/扰乱")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        delta_clip_x = float(
            slider_number_input(
                label="delta_clip_x",
                key="baseline_delta_clip_x",
                min_value=0.01,
                max_value=0.5,
                default=0.1,
                step=0.01,
                value_type="float",
                slider_format="%.3f",
            )
        )
    with col2:
        delta_clip_y = float(
            slider_number_input(
                label="delta_clip_y",
                key="baseline_delta_clip_y",
                min_value=0.01,
                max_value=0.5,
                default=0.1,
                step=0.01,
                value_type="float",
                slider_format="%.3f",
            )
        )
    with col3:
        release_std_x = float(
            slider_number_input(
                label="release_std_x",
                key="baseline_release_std_x",
                min_value=0.0,
                max_value=0.1,
                default=0.0,
                step=0.001,
                value_type="float",
                slider_format="%.3f",
            )
        )
    with col4:
        release_std_y = float(
            slider_number_input(
                label="release_std_y",
                key="baseline_release_std_y",
                min_value=0.0,
                max_value=0.1,
                default=0.0,
                step=0.001,
                value_type="float",
                slider_format="%.3f",
            )
        )

    st.markdown("#### 初期位置")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        initial_coll_x = float(
            slider_number_input(
                label="initial_coll_x (mm)",
                key="baseline_initial_coll_x",
                min_value=-0.5,
                max_value=0.5,
                default=0.0,
                step=0.01,
                value_type="float",
                slider_format="%.3f",
            )
        )
    with col2:
        initial_coll_y = float(
            slider_number_input(
                label="initial_coll_y (mm)",
                key="baseline_initial_coll_y",
                min_value=-0.5,
                max_value=0.5,
                default=0.0,
                step=0.01,
                value_type="float",
                slider_format="%.3f",
            )
        )
    with col3:
        random_seed = int(
            slider_number_input(
                label="random_seed",
                key="baseline_random_seed",
                min_value=0,
                max_value=999999,
                default=42,
                step=1,
                value_type="int",
                slider_format="%d",
            )
        )

    if st.button("ベースラインを実行", type="primary", key="run_baseline"):
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
            st.session_state["baseline_last_result"] = result
            st.success("ベースラインを実行しました")

    last_result = st.session_state.get("baseline_last_result")
    if last_result:
        st.divider()
        st.markdown("#### 実行結果")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("trial_id", last_result.get("trial_id"))
        r2.metric("converged", "✅" if last_result.get("converged") else "❌")
        r3.metric("steps", last_result.get("steps"))
        r4.metric("final_distance (um)", f"{last_result.get('final_distance', 0.0) * 1000.0:.1f}")
        
        trial_id = str(last_result.get("trial_id", ""))
        if trial_id:
            st.caption(f"詳細: [結果比較]画面で詳細な軌跡を表示します")


def render(api_client: RecipeApiClient) -> None:
    """Main render function for manual confirmation screen"""
    st.header("2️⃣ 手動確認")
    st.caption("ベースラインコントローラーの動作を手動および自動で確認します")

    experiment_id = _select_experiment(api_client)
    if experiment_id is None:
        st.info("最初に実験を作成してください")
        return

    # Update global context
    st.session_state["selected_experiment_id"] = experiment_id

    experiment_detail = api_client.get_experiment(experiment_id)
    if experiment_detail is None:
        st.error(f"実験の詳細を取得できません: {experiment_id}")
        return

    # Two tabs: manual stepping and baseline controller
    tab1, tab2 = st.tabs(["📍 手動確認", "📈 ベースライン実行"])
    
    with tab1:
        _render_manual_stepping(api_client, experiment_id, experiment_detail)
    
    with tab2:
        _render_baseline_controller(api_client, experiment_id, experiment_detail)
