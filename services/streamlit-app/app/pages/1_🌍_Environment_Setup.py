"""ページ1: 環境設定 & 実験作成

ボルト締めズレ特性を可視化し、recipe-service に実験を登録する。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.api_client import RecipeApiClient

st.set_page_config(
    page_title="環境設定",
    page_icon="🌍",
    layout="wide",
)

st.title("🌍 環境設定 & 実験作成")

st.markdown(
    """
このページで **実験 (experiment)** を作成します。作成した experiment_id を **🧬 世代交代パイプライン** ページで入力し、学習を実行します。

**手順**:
1. サイドバーで実験名と ボルトモデル (upper) を設定
2. 以下の **光学系 / カメラ パラメータ** を必要に応じて調整（デフォルトのままでもOK）
3. **🚀 実験を作成** ボタンを押す
4. 取得した experiment_id を 🧬 パイプラインページにコピー
"""
)


def _client() -> RecipeApiClient:
    if "api_client" not in st.session_state:
        st.session_state["api_client"] = RecipeApiClient()
    return st.session_state["api_client"]


def _power_law_shift(positions: np.ndarray, a: float, b: float, bias: float) -> np.ndarray:
    eff = positions + bias
    return np.sign(eff) * a * np.abs(eff) ** b


with st.sidebar:
    st.markdown("## 📝 実験メタデータ")
    exp_name = st.text_input("実験名", value="exp-ui")
    engine_type = st.selectbox("シミュレーターエンジン", options=["Simple", "KrakenOS"], index=0)

    st.markdown("---")
    st.markdown("## 🔩 ボルトモデル (upper)")
    upper_bias_x = st.number_input("x0_bias_x", value=0.05, step=0.01, format="%.4f")
    upper_bias_y = st.number_input("x0_bias_y", value=0.0, step=0.01, format="%.4f")
    upper_a_x = st.number_input("a_x", value=0.02, min_value=-0.5, max_value=0.5, step=0.01, format="%.4f")
    upper_b_x = st.number_input("b_x", value=1.0, min_value=0.1, max_value=2.0, step=0.1, format="%.2f")
    upper_a_y = st.number_input("a_y", value=0.02, min_value=-0.5, max_value=0.5, step=0.01, format="%.4f")
    upper_b_y = st.number_input("b_y", value=1.0, min_value=0.1, max_value=2.0, step=0.1, format="%.2f")

    st.markdown("---")
    grid_n = st.slider("可視化グリッド", min_value=5, max_value=20, value=10)


bolt_upper = {
    "x0_bias_x": upper_bias_x,
    "x0_bias_y": upper_bias_y,
    "a_x": upper_a_x,
    "b_x": upper_b_x,
    "a_y": upper_a_y,
    "b_y": upper_b_y,
    "noise_ratio_min_x": 0.01,
    "noise_ratio_max_x": 0.05,
    "noise_ratio_min_y": 0.01,
    "noise_ratio_max_y": 0.05,
}
bolt_lower = {
    "x0_bias_x": 0.0,
    "x0_bias_y": 0.0,
    "a_x": 0.0,
    "b_x": 1.0,
    "a_y": 0.0,
    "b_y": 1.0,
    "noise_ratio_min_x": 0.01,
    "noise_ratio_max_x": 0.05,
    "noise_ratio_min_y": 0.01,
    "noise_ratio_max_y": 0.05,
}


st.subheader("🗺️ ボルト締めズレ特性マップ")

col_graph, col_info = st.columns([2, 1])

with col_graph:
    x = np.linspace(-0.5, 0.5, grid_n)
    y = np.linspace(-0.5, 0.5, grid_n)
    X, Y = np.meshgrid(x, y)
    U = _power_law_shift(X, upper_a_x, upper_b_x, upper_bias_x)
    V = _power_law_shift(Y, upper_a_y, upper_b_y, upper_bias_y)

    fig = go.Figure()
    for i in range(len(x)):
        for j in range(len(y)):
            fig.add_trace(go.Scatter(
                x=[X[j, i], X[j, i] + U[j, i]],
                y=[Y[j, i], Y[j, i] + V[j, i]],
                mode="lines",
                line=dict(color="blue", width=2),
                showlegend=False, hoverinfo="skip",
            ))
            fig.add_trace(go.Scatter(
                x=[X[j, i] + U[j, i]], y=[Y[j, i] + V[j, i]],
                mode="markers",
                marker=dict(size=6, color="blue", symbol="triangle-up"),
                showlegend=False,
                hovertemplate=(
                    f"位置: ({X[j, i]:.2f}, {Y[j, i]:.2f})<br>"
                    f"Δ: ({U[j, i]:.3f}, {V[j, i]:.3f})<extra></extra>"
                ),
            ))
    fig.update_layout(
        title="upper ボルトのズレベクトル場",
        xaxis_title="ボルト締め前 X (mm)",
        yaxis_title="ボルト締め前 Y (mm)",
        width=600, height=600,
        xaxis=dict(range=[-0.6, 0.6]),
        yaxis=dict(range=[-0.6, 0.6], scaleanchor="x", scaleratio=1),
    )
    st.plotly_chart(fig, use_container_width=True)

with col_info:
    mag = np.sqrt(U ** 2 + V ** 2)
    st.markdown("### 📊 統計")
    st.metric("平均シフト", f"{mag.mean():.3f} mm")
    st.metric("最大シフト", f"{mag.max():.3f} mm")
    st.metric("最小シフト", f"{mag.min():.3f} mm")
    st.info(
        "Δx = sign(x+bias) · a_x · |x+bias|^b_x\n\n"
        "b_x>1 で非線形、a_x の符号で方向が反転します。"
    )

st.markdown("---")
st.subheader("📝 実験を登録")

with st.expander("🔬 光学系パラメータ（高度設定・デフォルトでOK）", expanded=False):
    opt_c1, opt_c2, opt_c3 = st.columns(3)
    with opt_c1:
        st.markdown("**💡 光源 (LD)**")
        wavelength = st.number_input("wavelength (nm)", value=780.0, min_value=200.0, max_value=2000.0, step=10.0)
        ld_div_fast = st.number_input("ld_div_fast (deg)", value=30.0, min_value=1.0, max_value=60.0, step=1.0)
        ld_div_slow = st.number_input("ld_div_slow (deg)", value=10.0, min_value=1.0, max_value=60.0, step=1.0)
        ld_emit_w = st.number_input("ld_emit_w (um)", value=2.0, min_value=0.1, step=0.1)
        ld_emit_h = st.number_input("ld_emit_h (um)", value=1.0, min_value=0.1, step=0.1)
        num_rays = st.number_input("num_rays", value=10000, min_value=100, max_value=200000, step=1000)
    with opt_c2:
        st.markdown("**🔍 コリメートレンズ**")
        coll_r1 = st.number_input("coll_r1 (mm)", value=0.0, step=0.5, format="%.3f")
        coll_r2 = st.number_input("coll_r2 (mm)", value=-10.0, step=0.5, format="%.3f")
        coll_k1 = st.number_input("coll_k1", value=1.0, step=0.1, format="%.3f")
        coll_k2 = st.number_input("coll_k2", value=1.0, step=0.1, format="%.3f")
        coll_t = st.number_input("coll_t (mm)", value=5.0, min_value=0.1, step=0.5)
        coll_n = st.number_input("coll_n (refractive index)", value=1.5, min_value=1.0, max_value=3.0, step=0.05)
    with opt_c3:
        st.markdown("**📐 距離 / センサー**")
        dist_ld_coll = st.number_input("dist_ld_coll (mm)", value=50.0, min_value=1.0, step=1.0)
        obj_f = st.number_input("obj_f (mm)", value=50.0, min_value=1.0, step=1.0)
        dist_coll_obj = st.number_input("dist_coll_obj (mm)", value=100.0, min_value=1.0, step=1.0)
        sensor_pos = st.number_input("sensor_pos (mm)", value=160.0, min_value=1.0, step=1.0)
        pixel_w = st.number_input("pixel_w", value=640, min_value=64, max_value=4096, step=32)
        pixel_h = st.number_input("pixel_h", value=480, min_value=64, max_value=4096, step=32)
        pixel_pitch_um = st.number_input("pixel_pitch_um", value=5.3, min_value=0.5, step=0.1)
        gaussian_sigma_px = st.number_input("gaussian_sigma_px", value=3.0, min_value=0.1, step=0.1)

if st.button("🚀 実験を作成", type="primary"):
    payload = {
        "name": exp_name,
        "engine_type": engine_type,
        "optical_system": {
            "wavelength": float(wavelength), "ld_tilt": 0.0,
            "ld_div_fast": float(ld_div_fast), "ld_div_slow": float(ld_div_slow),
            "ld_div_fast_err": 0.0, "ld_div_slow_err": 0.0,
            "ld_emit_w": float(ld_emit_w), "ld_emit_h": float(ld_emit_h),
            "num_rays": int(num_rays),
            "coll_r1": float(coll_r1), "coll_r2": float(coll_r2),
            "coll_k1": float(coll_k1), "coll_k2": float(coll_k2),
            "coll_t": float(coll_t), "coll_n": float(coll_n),
            "dist_ld_coll": float(dist_ld_coll),
            "obj_f": float(obj_f), "dist_coll_obj": float(dist_coll_obj),
            "sensor_pos": float(sensor_pos),
        },
        "camera": {
            "pixel_w": int(pixel_w), "pixel_h": int(pixel_h),
            "pixel_pitch_um": float(pixel_pitch_um),
            "gaussian_sigma_px": float(gaussian_sigma_px),
        },
        "bolt_model": {"upper": bolt_upper, "lower": bolt_lower},
    }
    created = _client().create_experiment(payload)
    if created and "experiment_id" in created:
        st.success(f"✅ 実験作成成功: {created['experiment_id']}")
        st.info("👉 この experiment_id をコピーし、左サイドバーの **🧬 世代交代パイプライン** ページで入力してください。")
        st.session_state["last_experiment_id"] = created["experiment_id"]
        st.session_state.pop("_experiments_cache", None)
    else:
        st.error("実験作成に失敗しました")

st.markdown("---")
st.subheader("📚 登録済みの実験")

if st.button("🔄 実験一覧を更新"):
    st.session_state.pop("_experiments_cache", None)

experiments = st.session_state.get("_experiments_cache")
if experiments is None:
    experiments = _client().list_experiments() or []
    st.session_state["_experiments_cache"] = experiments

if experiments:
    df = pd.DataFrame(experiments)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("💡 `experiment_id` を **🧬 世代交代パイプライン** ページで使用してください。")
else:
    st.info("実験はまだ登録されていません。")
