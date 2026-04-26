from __future__ import annotations

from typing import Any

import streamlit as st

from app.api_client import RecipeApiClient
from app.components.charts import render_optical_schematic, render_bolt_response_graph
from app.components.inputs import slider_number_input


OpticalSpec = tuple[str, str, float | int, float | int, float | int, float | int, str, str]
BoltSpec = tuple[str, float, float, float, float, str]

OPTICAL_SPECS: list[OpticalSpec] = [
    ("wavelength", "wavelength (nm)", 300.0, 2000.0, 780.0, 1.0, "%.1f", "float"),
    ("ld_tilt", "ld_tilt (deg)", -30.0, 30.0, 0.0, 0.1, "%.2f", "float"),
    ("ld_div_fast", "ld_div_fast (deg)", 0.1, 80.0, 25.0, 0.1, "%.2f", "float"),
    ("ld_div_slow", "ld_div_slow (deg)", 0.1, 40.0, 8.0, 0.1, "%.2f", "float"),
    ("ld_div_fast_err", "ld_div_fast_err (deg)", -10.0, 10.0, 0.0, 0.01, "%.2f", "float"),
    ("ld_div_slow_err", "ld_div_slow_err (deg)", -10.0, 10.0, 0.0, 0.01, "%.2f", "float"),
    ("ld_emit_w", "ld_emit_w (μm)", 0.1, 20.0, 3.0, 0.1, "%.3f", "float"),
    ("ld_emit_h", "ld_emit_h (μm)", 0.1, 20.0, 1.0, 0.1, "%.3f", "float"),
    ("num_rays", "num_rays", 100, 200000, 5000, 100, "%d", "int"),
    ("coll_r1", "coll_r1", -100.0, 100.0, -3.5, 0.1, "%.3f", "float"),
    ("coll_r2", "coll_r2", -100.0, 100.0, -15.0, 0.1, "%.3f", "float"),
    ("coll_k1", "coll_k1", -5.0, 5.0, -1.0, 0.01, "%.3f", "float"),
    ("coll_k2", "coll_k2", -5.0, 5.0, 0.0, 0.01, "%.3f", "float"),
    ("coll_t", "coll_t", 0.1, 20.0, 2.0, 0.1, "%.3f", "float"),
    ("coll_n", "coll_n", 1.001, 3.0, 1.517, 0.001, "%.4f", "float"),
    ("dist_ld_coll", "dist_ld_coll", 0.1, 100.0, 4.0, 0.1, "%.3f", "float"),
    ("obj_f", "obj_f", 0.1, 100.0, 4.0, 0.1, "%.3f", "float"),
    ("dist_coll_obj", "dist_coll_obj", 0.1, 200.0, 50.0, 0.1, "%.3f", "float"),
    ("sensor_pos", "sensor_pos", 0.1, 50.0, 4.0, 0.1, "%.3f", "float"),
]

BOLT_SPECS: list[BoltSpec] = [
    # Initial-position bias (evaluated before power-law)
    ("x0_bias_x", -0.2, 0.2, 0.0, 0.001, "%.4f"),
    ("x0_bias_y", -0.2, 0.2, 0.0, 0.001, "%.4f"),
    # X direction power-law coefficients
    ("a_x", -0.5, 0.5, 0.02, 0.001, "%.3f"),
    ("b_x", 0.01, 2.0, 1.0, 0.01, "%.2f"),
    # Y direction power-law coefficients
    ("a_y", -0.5, 0.5, 0.02, 0.001, "%.3f"),
    ("b_y", 0.01, 2.0, 1.0, 0.01, "%.2f"),
    # Relative noise ratio (deterministic displacement ±[min,max]%)
    ("noise_ratio_min_x", 0.0, 0.2, 0.01, 0.001, "%.3f"),
    ("noise_ratio_max_x", 0.0, 0.2, 0.05, 0.001, "%.3f"),
    ("noise_ratio_min_y", 0.0, 0.2, 0.01, 0.001, "%.3f"),
    ("noise_ratio_max_y", 0.0, 0.2, 0.05, 0.001, "%.3f"),
]

BOLT_LOWER_DEFAULTS = {
    "x0_bias_x": 0.0,
    "x0_bias_y": 0.0,
    "a_x": 0.02,
    "b_x": 1.0,
    "a_y": 0.02,
    "b_y": 1.0,
    "noise_ratio_min_x": 0.01,
    "noise_ratio_max_x": 0.05,
    "noise_ratio_min_y": 0.01,
    "noise_ratio_max_y": 0.05,
}

CameraSpec = tuple[str, str, float | int, float | int, float | int, float | int, str, str]

CAMERA_SPECS: list[CameraSpec] = [
    ("pixel_w", "幅 (px)", 64, 4096, 640, 64, "%d", "int"),
    ("pixel_h", "高さ (px)", 64, 4096, 480, 64, "%d", "int"),
    ("pixel_pitch_um", "ピクセルピッチ (um)", 0.1, 100.0, 5.3, 0.1, "%.1f", "float"),
    ("gaussian_sigma_px", "ガウシアン σ (px)", 0.0, 50.0, 3.0, 0.5, "%.1f", "float"),
    ("fov_width_mm", "視野幅 (mm)", 0.1, 10.0, 1.0, 0.1, "%.2f", "float"),
    ("fov_height_mm", "視野高さ (mm)", 0.1, 10.0, 1.0, 0.1, "%.2f", "float"),
]


def _format_experiment(experiment: dict[str, Any]) -> str:
    engine = experiment.get('engine_type', 'KrakenOS')
    engine_icon = "⚡" if engine == "Simple" else "🔬"
    return f"{engine_icon} {experiment['experiment_id']} | {experiment['name']} ({engine})"


def _render_experiment_selector(experiments: list[dict[str, Any]]) -> None:
    if not experiments:
        st.info("実験がまだ作成されていません")
        st.session_state["selected_experiment_id"] = None
        return

    experiment_ids = [item["experiment_id"] for item in experiments]
    selected_id = st.session_state.get("selected_experiment_id")
    if selected_id not in experiment_ids:
        selected_id = experiment_ids[0]

    id_to_experiment = {item["experiment_id"]: item for item in experiments}
    index = experiment_ids.index(selected_id)

    selected_id = st.selectbox(
        "操作対象の実験",
        options=experiment_ids,
        index=index,
        key="experiment_selected_id_widget",
        format_func=lambda exp_id: _format_experiment(id_to_experiment[exp_id]),
    )
    st.session_state["selected_experiment_id"] = selected_id


def _collect_optical_system(engine_type: str = "Simple") -> dict[str, Any]:
    """Collect optical system parameters based on engine type."""
    # Simple engine only uses: ld_emit_w, ld_emit_h, ld_tilt
    # Other parameters get default values but are not shown to user
    simple_required_params = {"ld_emit_w", "ld_emit_h", "ld_tilt"}
    
    values: dict[str, Any] = {}
    for name, label, min_v, max_v, default, step, fmt, value_type in OPTICAL_SPECS:
        # For Simple engine, only show required parameters
        if engine_type == "Simple" and name not in simple_required_params:
            # Use default value without showing UI
            values[name] = default
        else:
            values[name] = slider_number_input(
                label=label,
                key=f"exp_opt_{name}",
                min_value=min_v,
                max_value=max_v,
                default=default,
                step=step,
                value_type=value_type,
                slider_format=fmt,
            )
    return values


def _collect_bolt_model() -> dict[str, dict[str, float]]:
    """Collect bolt model parameters (v3.0: position-dependent power-law)."""
    
    # Position range setting (at the top)
    st.markdown("#### 位置範囲設定（グラフ表示用）")
    position_max = st.slider(
        "最大位置 (mm)",
        min_value=0.1,
        max_value=1.5,
        value=1.0,
        step=0.05,
        key="exp_bolt_position_max",
        help="グラフのX軸最大値を設定"
    )
    
    # Initialize parameter dictionaries with defaults for initial graph display
    upper: dict[str, float] = {}
    lower: dict[str, float] = {}
    
    # Parameter labels with descriptions
    param_labels = {
        "x0_bias_x": "x0_bias_x — X初期位置バイアス (mm)",
        "x0_bias_y": "x0_bias_y — Y初期位置バイアス (mm)",
        "a_x": "a_x — X方向係数 (無次元)",
        "b_x": "b_x — X方向べき指数 (1=線形, <1=飽和, >1=加速)",
        "a_y": "a_y — Y方向係数 (無次元)",
        "b_y": "b_y — Y方向べき指数 (1=線形, <1=飽和, >1=加速)",
        "noise_ratio_min_x": "noise_ratio_min_x — Xノイズ最小割合 (例: 0.01=1%)",
        "noise_ratio_max_x": "noise_ratio_max_x — Xノイズ最大割合 (例: 0.05=5%)",
        "noise_ratio_min_y": "noise_ratio_min_y — Yノイズ最小割合 (例: 0.01=1%)",
        "noise_ratio_max_y": "noise_ratio_max_y — Yノイズ最大割合 (例: 0.05=5%)",
    }

    # Collect upper parameters
    st.markdown("#### upper ボルト パラメータ")
    st.caption("x_eff = x0 + x0_bias_x,  Δx_det = sign(x_eff) × a_x × |x_eff|^b_x,  Δx = Δx_det × (1 + r_x), r_x ∈ ±[min,max]")
    for name, min_v, max_v, default, step, fmt in BOLT_SPECS:
        label = param_labels.get(name, name)
        upper[name] = float(
            slider_number_input(
                label=label,
                key=f"exp_bolt_upper_{name}",
                min_value=min_v,
                max_value=max_v,
                default=default,
                step=step,
                value_type="float",
                slider_format=fmt,
            )
        )

    # Display upper graph immediately after parameters
    st.markdown("##### Upper ボルト応答")
    fig_upper = render_bolt_response_graph(upper, position_max, "Upper ボルト応答")
    st.plotly_chart(fig_upper, width="stretch")

    st.markdown("---")

    # Collect lower parameters
    st.markdown("#### lower ボルト パラメータ")
    st.caption("y_eff = y0 + x0_bias_y,  Δy_det = sign(y_eff) × a_y × |y_eff|^b_y,  Δy = Δy_det × (1 + r_y), r_y ∈ ±[min,max]")
    for name, min_v, max_v, default, step, fmt in BOLT_SPECS:
        label = param_labels.get(name, name)
        lower_default = BOLT_LOWER_DEFAULTS.get(name, default)
        lower[name] = float(
            slider_number_input(
                label=label,
                key=f"exp_bolt_lower_{name}",
                min_value=min_v,
                max_value=max_v,
                default=lower_default,
                step=step,
                value_type="float",
                slider_format=fmt,
            )
        )

    # Display lower graph immediately after parameters
    st.markdown("##### Lower ボルト応答")
    fig_lower = render_bolt_response_graph(lower, position_max, "Lower ボルト応答")
    st.plotly_chart(fig_lower, width="stretch")

    return {
        "upper": upper,
        "lower": lower,
    }


def _collect_camera_settings() -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name, label, min_v, max_v, default, step, fmt, value_type in CAMERA_SPECS:
        values[name] = slider_number_input(
            label=label,
            key=f"exp_cam_{name}",
            min_value=min_v,
            max_value=max_v,
            default=default,
            step=step,
            value_type=value_type,
            slider_format=fmt,
        )
    return values


def render(api_client: RecipeApiClient) -> None:
    st.header("実験管理")

    refresh_col, spacer_col = st.columns([1, 4])
    with refresh_col:
        if st.button("実験一覧を更新"):
            st.rerun()
    with spacer_col:
        st.caption("GET /experiments で取得")

    experiments = api_client.list_experiments()
    if experiments is None:
        experiments = []

    if experiments:
        # 表示用にengine_typeカラムを追加
        display_experiments = [
            {
                **exp,
                "engine": exp.get("engine_type", "KrakenOS")
            }
            for exp in experiments
        ]
        st.dataframe(display_experiments, width="stretch", hide_index=True)
    else:
        st.info("表示できる実験がありません")

    _render_experiment_selector(experiments)

    st.divider()
    st.subheader("新規実験作成")

    default_name = st.session_state.get("new_experiment_name", "baseline_780nm")
    experiment_name = st.text_input("実験名", value=default_name, key="new_experiment_name")
    
    st.markdown("### シミュレーションエンジン")
    engine_type = st.selectbox(
        "エンジン種別",
        ["Simple", "KrakenOS"],
        index=0,
        help="Simple: 高速ガウシアンモデル（推奨） / KrakenOS: 精密な光線追跡",
        key="new_experiment_engine_type"
    )
    
    if engine_type == "Simple":
        st.info("✨ Simpleモードでは必要最小限のパラメータ（LD発光サイズ、LD傾き）のみで高速シミュレーションが可能です")
    else:
        st.warning("🔬 KrakenOSモードでは全パラメータの入力が必要です（計算時間が長くなります）")
    
    with st.expander("光学系パラメータ", expanded=True):
        st.plotly_chart(render_optical_schematic(engine_type), width="stretch")
        optical_system = _collect_optical_system(engine_type)

    with st.expander("ボルトモデルパラメータ", expanded=False):
        bolt_model = _collect_bolt_model()

    with st.expander("カメラ設定", expanded=False):
        camera = _collect_camera_settings()

    if st.button("実験を作成", type="primary"):
        name = experiment_name.strip()
        if not name:
            st.warning("実験名を入力してください")
            return

        payload = {
            "name": name,
            "engine_type": engine_type,
            "optical_system": optical_system,
            "bolt_model": bolt_model,
            "camera": camera,
        }
        created = api_client.create_experiment(payload)
        if created is None:
            return

        experiment_id = str(created.get("experiment_id", ""))
        created_engine = created.get("engine_type", "KrakenOS")
        if experiment_id:
            st.session_state["selected_experiment_id"] = experiment_id
        st.success(f"✅ 実験を作成しました: {experiment_id} (エンジン: {created_engine})")
        st.rerun()
