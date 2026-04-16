from __future__ import annotations

from typing import Any

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from scipy.ndimage import gaussian_filter


def _lens_shape(
    cx: float, half_h: float, bulge_left: float, bulge_right: float, n_pts: int = 40
) -> tuple[np.ndarray, np.ndarray]:
    """Return x, y arrays for a symmetric lens outline (parabolic arcs)."""
    t = np.linspace(-1, 1, n_pts)
    left_x = cx - bulge_left * (1 - t**2)
    left_y = half_h * t
    right_x = cx + bulge_right * (1 - t**2)
    right_y = half_h * t
    x = np.concatenate([left_x, right_x[::-1]])
    y = np.concatenate([left_y, right_y[::-1]])
    return x, y


def _arrow_annotation(
    fig: go.Figure,
    x0: float, x1: float, y: float,
    label: str,
    color: str = "#555",
    font_size: int = 10,
) -> None:
    """Draw a horizontal double-arrow with a centered label below the axis."""
    mid = (x0 + x1) / 2
    fig.add_annotation(
        x=x1, y=y, ax=x0, ay=y,
        xref="x", yref="y", axref="x", ayref="y",
        showarrow=True,
        arrowhead=2, arrowsize=1, arrowwidth=1.5, arrowcolor=color,
    )
    fig.add_annotation(
        x=x0, y=y, ax=x1, ay=y,
        xref="x", yref="y", axref="x", ayref="y",
        showarrow=True,
        arrowhead=2, arrowsize=1, arrowwidth=1.5, arrowcolor=color,
    )
    fig.add_annotation(
        x=mid, y=y - 1.8,
        text=f"<b>{label}</b>",
        showarrow=False,
        font=dict(size=font_size, color=color),
    )


def _render_simple_schematic() -> go.Figure:
    """Simpleエンジン用の簡略化した光学系図を描画。
    
    必要なパラメータのみ表示：
    - ld_emit_w, ld_emit_h: LD発光面サイズ
    - ld_tilt: LD傾き
    - 50x倍率の概念図
    """
    fig = go.Figure()
    
    # ── 光軸 ──
    fig.add_shape(
        type="line", x0=0, y0=0, x1=90, y1=0,
        line=dict(color="#bbb", width=1, dash="dot"),
    )
    
    # ── LD（レーザーダイオード）──
    ld_x, ld_y = 10, 0
    ld_w, ld_h = 4, 8  # 表示用サイズ（実際のld_emit_w/hとは縮尺が異なる）
    
    # LD矩形（直立状態）
    fig.add_shape(
        type="rect",
        x0=ld_x - ld_w/2, y0=ld_y - ld_h/2,
        x1=ld_x + ld_w/2, y1=ld_y + ld_h/2,
        fillcolor="rgba(255,80,80,0.35)",
        line=dict(color="#d32f2f", width=2),
    )
    
    # LD発光面サイズの寸法線（横）
    fig.add_annotation(
        x=ld_x + ld_w/2, y=ld_y - ld_h/2 - 2,
        ax=ld_x - ld_w/2, ay=ld_y - ld_h/2 - 2,
        xref="x", yref="y", axref="x", ayref="y",
        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1, arrowcolor="#d32f2f",
    )
    fig.add_annotation(
        x=ld_x - ld_w/2, y=ld_y - ld_h/2 - 2,
        ax=ld_x + ld_w/2, ay=ld_y - ld_h/2 - 2,
        xref="x", yref="y", axref="x", ayref="y",
        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1, arrowcolor="#d32f2f",
    )
    fig.add_annotation(
        x=ld_x, y=ld_y - ld_h/2 - 4,
        text="<b>ld_emit_w</b><br>(Slow軸)",
        showarrow=False,
        font=dict(size=10, color="#d32f2f"),
    )
    
    # LD発光面サイズの寸法線（縦）
    fig.add_annotation(
        x=ld_x + ld_w/2 + 2, y=ld_y + ld_h/2,
        ax=ld_x + ld_w/2 + 2, ay=ld_y - ld_h/2,
        xref="x", yref="y", axref="x", ayref="y",
        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1, arrowcolor="#d32f2f",
    )
    fig.add_annotation(
        x=ld_x + ld_w/2 + 2, y=ld_y - ld_h/2,
        ax=ld_x + ld_w/2 + 2, ay=ld_y + ld_h/2,
        xref="x", yref="y", axref="x", ayref="y",
        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1, arrowcolor="#d32f2f",
    )
    fig.add_annotation(
        x=ld_x + ld_w/2 + 5, y=ld_y,
        text="<b>ld_emit_h</b><br>(Fast軸)",
        showarrow=False,
        font=dict(size=10, color="#d32f2f"),
    )
    
    # LD傾き角の表示
    tilt_angle = 15  # 表示用の角度
    tilt_radius = 6
    fig.add_shape(
        type="path",
        path=f"M {ld_x},{ld_y} L {ld_x + tilt_radius},{ld_y} A {tilt_radius},{tilt_radius} 0 0,1 {ld_x + tilt_radius*np.cos(np.radians(tilt_angle))},{ld_y + tilt_radius*np.sin(np.radians(tilt_angle))} Z",
        fillcolor="rgba(255,165,0,0.2)",
        line=dict(color="orange", width=1.5),
    )
    fig.add_annotation(
        x=ld_x + 8, y=ld_y + 2,
        text="<b>ld_tilt</b>",
        showarrow=False,
        font=dict(size=10, color="orange"),
    )
    
    # ── 光学系の簡略図（ブラックボックス） ──
    optics_x = 45
    optics_w, optics_h = 15, 16
    fig.add_shape(
        type="rect",
        x0=optics_x - optics_w/2, y0=-optics_h/2,
        x1=optics_x + optics_w/2, y1=optics_h/2,
        fillcolor="rgba(100,150,250,0.15)",
        line=dict(color="#1565c0", width=2, dash="dash"),
    )
    fig.add_annotation(
        x=optics_x, y=0,
        text="<b>光学系</b><br>(コリメータ+対物)<br><br>倍率: <b>50x</b>",
        showarrow=False,
        font=dict(size=11, color="#1565c0"),
    )
    
    # ── カメラセンサ ──
    sensor_x = 75
    sensor_h = 14
    fig.add_shape(
        type="rect",
        x0=sensor_x - 0.5, y0=-sensor_h/2,
        x1=sensor_x + 0.5, y1=sensor_h/2,
        fillcolor="rgba(100,100,100,0.5)",
        line=dict(color="#333", width=2),
    )
    fig.add_annotation(
        x=sensor_x, y=sensor_h/2 + 3,
        text="<b>カメラ</b>",
        showarrow=False,
        font=dict(size=11, color="#333"),
    )
    
    # ── 光線の流れ（簡略） ──
    for dy in [-3, 0, 3]:
        # LD → 光学系
        fig.add_trace(go.Scatter(
            x=[ld_x + ld_w/2, optics_x - optics_w/2],
            y=[dy*0.3, dy*0.8],
            mode="lines",
            line=dict(color="rgba(255,0,0,0.25)", width=1.5),
            showlegend=False, hoverinfo="skip",
        ))
        # 光学系 → センサ
        fig.add_trace(go.Scatter(
            x=[optics_x + optics_w/2, sensor_x],
            y=[dy*0.8, dy*0.2],
            mode="lines",
            line=dict(color="rgba(255,0,0,0.25)", width=1.5),
            showlegend=False, hoverinfo="skip",
        ))
    
    # ── パラメータ説明ボックス ──
    param_text = (
        "<b>Simpleモードの必須パラメータ</b><br><br>"
        "<b>ld_emit_w</b> (μm) — LD発光幅 (Slow軸)<br>"
        "<b>ld_emit_h</b> (μm) — LD発光高さ (Fast軸)<br>"
        "<b>ld_tilt</b> (deg) — LD傾き角<br><br>"
        "⚡ その他のパラメータは自動設定されます"
    )
    fig.add_annotation(
        x=45, y=22,
        text=param_text,
        showarrow=False,
        font=dict(size=10, color="#333"),
        align="left",
        xanchor="center",
        yanchor="bottom",
        bordercolor="#666",
        borderwidth=2,
        borderpad=8,
        bgcolor="rgba(255,255,220,0.95)",
    )
    
    # ── 倍率説明 ──
    mag_text = (
        "💡 <b>倍率 50x</b><br>"
        "コリメータ移動 1mm → スポット移動 50mm"
    )
    fig.add_annotation(
        x=45, y=-15,
        text=mag_text,
        showarrow=False,
        font=dict(size=10, color="#1565c0"),
        align="center",
        bordercolor="#1565c0",
        borderwidth=1,
        borderpad=6,
        bgcolor="rgba(240,248,255,0.9)",
    )
    
    # ── レイアウト ──
    fig.update_layout(
        height=450,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(
            visible=False, range=[-5, 90],
            scaleanchor="y", scaleratio=1,
        ),
        yaxis=dict(visible=False, range=[-20, 35]),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    
    return fig


def render_optical_schematic(engine_type: str = "KrakenOS") -> go.Figure:
    """光学系の模式図を描画し、各パラメータが対応する箇所を示す。
    
    Args:
        engine_type: "Simple" or "KrakenOS". Simpleの場合は簡略版を表示。
    """
    
    if engine_type == "Simple":
        return _render_simple_schematic()
    
    fig = go.Figure()

    # ── element positions (schematic, not to scale) ──
    ld_x = 8
    coll_x = 28
    obj_x = 68
    sensor_x = 88

    # ── optical axis ──
    fig.add_shape(
        type="line", x0=0, y0=0, x1=96, y1=0,
        line=dict(color="#bbb", width=1, dash="dot"),
    )

    # ── LD (laser diode) ──
    ld_hw, ld_hh = 1.8, 3.5
    fig.add_shape(
        type="rect",
        x0=ld_x - ld_hw, y0=-ld_hh, x1=ld_x + ld_hw, y1=ld_hh,
        fillcolor="rgba(255,80,80,0.35)", line=dict(color="#d32f2f", width=2),
    )
    # diverging rays
    for dy_frac in [-0.7, -0.35, 0, 0.35, 0.7]:
        fig.add_trace(go.Scatter(
            x=[ld_x + ld_hw, coll_x - 3],
            y=[0, dy_frac * 10],
            mode="lines",
            line=dict(color="rgba(255,0,0,0.25)", width=1),
            showlegend=False, hoverinfo="skip",
        ))

    # ── Collimate lens ──
    lx, ly = _lens_shape(coll_x, half_h=10, bulge_left=2.5, bulge_right=1.5)
    fig.add_trace(go.Scatter(
        x=lx, y=ly, fill="toself",
        fillcolor="rgba(66,133,244,0.2)",
        line=dict(color="#1565c0", width=2),
        showlegend=False, hoverinfo="skip",
    ))
    # coll_t brace (thickness at center)
    fig.add_annotation(
        x=coll_x + 1.5, y=-11, ax=coll_x - 2.5, ay=-11,
        xref="x", yref="y", axref="x", ayref="y",
        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1, arrowcolor="#1565c0",
    )
    fig.add_annotation(
        x=coll_x - 2.5, y=-11, ax=coll_x + 1.5, ay=-11,
        xref="x", yref="y", axref="x", ayref="y",
        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1, arrowcolor="#1565c0",
    )
    fig.add_annotation(
        x=coll_x, y=-13,
        text="coll_t", showarrow=False,
        font=dict(size=9, color="#1565c0"),
    )

    # parallel rays between coll and obj
    for dy in [-3, 0, 3]:
        fig.add_trace(go.Scatter(
            x=[coll_x + 3, obj_x - 2],
            y=[dy, dy],
            mode="lines",
            line=dict(color="rgba(255,0,0,0.2)", width=1),
            showlegend=False, hoverinfo="skip",
        ))

    # ── Objective lens (thin lens symbol) ──
    obj_hh = 9
    fig.add_shape(
        type="line", x0=obj_x, y0=-obj_hh, x1=obj_x, y1=obj_hh,
        line=dict(color="#2e7d32", width=2.5),
    )
    # arrowheads at tips (inward-pointing = converging lens)
    for sign, y_tip in [(-1, -obj_hh), (1, obj_hh)]:
        fig.add_trace(go.Scatter(
            x=[obj_x - 1.5, obj_x, obj_x + 1.5],
            y=[y_tip + sign * 2.5, y_tip, y_tip + sign * 2.5],
            mode="lines",
            line=dict(color="#2e7d32", width=2),
            showlegend=False, hoverinfo="skip",
        ))

    # converging rays obj → sensor
    for dy in [-3, 0, 3]:
        fig.add_trace(go.Scatter(
            x=[obj_x + 1, sensor_x],
            y=[dy, 0],
            mode="lines",
            line=dict(color="rgba(255,0,0,0.2)", width=1),
            showlegend=False, hoverinfo="skip",
        ))

    # ── Sensor ──
    fig.add_shape(
        type="rect",
        x0=sensor_x - 0.5, y0=-8, x1=sensor_x + 0.5, y1=8,
        fillcolor="rgba(100,100,100,0.5)", line=dict(color="#333", width=2),
    )

    # ── Element labels (above) ──
    for x, label, color in [
        (ld_x, "LD<br>(Laser Diode)", "#d32f2f"),
        (coll_x, "コリメートレンズ", "#1565c0"),
        (obj_x, "対物レンズ", "#2e7d32"),
        (sensor_x, "センサ面", "#333"),
    ]:
        fig.add_annotation(
            x=x, y=13,
            text=f"<b>{label}</b>",
            showarrow=False,
            font=dict(size=11, color=color),
        )

    # ── Distance arrows (below axis) ──
    arrow_y = -17
    _arrow_annotation(fig, ld_x, coll_x, arrow_y, "dist_ld_coll", "#666")
    _arrow_annotation(fig, coll_x, obj_x, arrow_y, "dist_coll_obj", "#666")
    _arrow_annotation(fig, obj_x, sensor_x, arrow_y, "sensor_pos", "#666")

    # ── Parameter annotations (grouped near each element) ──
    ld_params = (
        "<b>LD パラメータ</b><br>"
        "wavelength — 波長<br>"
        "ld_tilt — 傾き角<br>"
        "ld_div_fast / slow — 発散角<br>"
        "ld_div_fast_err / slow_err — 発散角誤差<br>"
        "ld_emit_w × h — 発光面サイズ<br>"
        "num_rays — レイ本数"
    )
    coll_params = (
        "<b>コリメートレンズ</b><br>"
        "coll_r1 — 左面 曲率半径<br>"
        "coll_r2 — 右面 曲率半径<br>"
        "coll_k1 — 左面 コニック係数<br>"
        "coll_k2 — 右面 コニック係数<br>"
        "coll_t — 中心厚<br>"
        "coll_n — 屈折率"
    )
    obj_params = (
        "<b>対物レンズ</b><br>"
        "obj_f — 焦点距離"
    )

    # Place parameter boxes above the diagram
    param_y = 25
    for x, text, color, xanchor in [
        (ld_x, ld_params, "#d32f2f", "left"),
        (coll_x + 5, coll_params, "#1565c0", "left"),
        (obj_x + 3, obj_params, "#2e7d32", "left"),
    ]:
        fig.add_annotation(
            x=x, y=param_y,
            text=text,
            showarrow=False,
            font=dict(size=9, color=color),
            align="left",
            xanchor=xanchor,
            yanchor="bottom",
            bordercolor=color,
            borderwidth=1,
            borderpad=4,
            bgcolor="rgba(255,255,255,0.9)",
        )

    # ── R1/R2 labels on lens surfaces ──
    fig.add_annotation(
        x=coll_x - 3.5, y=6, text="R1", showarrow=True,
        ax=coll_x - 2.5, ay=5,
        font=dict(size=9, color="#1565c0"),
        arrowhead=2, arrowsize=0.8, arrowwidth=1, arrowcolor="#1565c0",
    )
    fig.add_annotation(
        x=coll_x + 3.5, y=6, text="R2", showarrow=True,
        ax=coll_x + 1.5, ay=5,
        font=dict(size=9, color="#1565c0"),
        arrowhead=2, arrowsize=0.8, arrowwidth=1, arrowcolor="#1565c0",
    )

    # ── Layout ──
    fig.update_layout(
        height=520,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(
            visible=False, range=[-2, 100],
            scaleanchor="y", scaleratio=1,
        ),
        yaxis=dict(visible=False, range=[-22, 48]),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )

    return fig


def _extract_metric(sim: dict[str, Any], key: str) -> float | None:
    value = sim.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def render_sim_metrics(title: str, sim: dict[str, Any]) -> None:
    st.markdown(f"### {title}")
    c1, c2 = st.columns(2)
    c1.metric("spot_center_x", _extract_metric(sim, "spot_center_x"))
    c2.metric("spot_center_y", _extract_metric(sim, "spot_center_y"))

    c3, c4 = st.columns(2)
    c3.metric("spot_rms_radius", _extract_metric(sim, "spot_rms_radius"))
    c4.metric("vignetting_ratio", _extract_metric(sim, "vignetting_ratio"))


def plot_sweep_charts(results: list[dict[str, Any]], sweep_param: str) -> None:
    if not results:
        st.info("スイープ結果がありません")
        return

    x_values: list[float] = []
    pos_cx: list[float | None] = []
    pos_cy: list[float | None] = []
    bolt_cx: list[float | None] = []
    bolt_cy: list[float | None] = []
    pos_rms: list[float | None] = []
    bolt_rms: list[float | None] = []
    pos_vig: list[float | None] = []
    bolt_vig: list[float | None] = []

    for item in results:
        x_values.append(float(item.get("param_value", 0.0)))
        sim_pos = item.get("sim_after_position", {})
        sim_bolt = item.get("sim_after_bolt", {})

        pos_cx.append(_extract_metric(sim_pos, "spot_center_x"))
        pos_cy.append(_extract_metric(sim_pos, "spot_center_y"))
        bolt_cx.append(_extract_metric(sim_bolt, "spot_center_x"))
        bolt_cy.append(_extract_metric(sim_bolt, "spot_center_y"))

        pos_rms.append(_extract_metric(sim_pos, "spot_rms_radius"))
        bolt_rms.append(_extract_metric(sim_bolt, "spot_rms_radius"))

        pos_vig.append(_extract_metric(sim_pos, "vignetting_ratio"))
        bolt_vig.append(_extract_metric(sim_bolt, "vignetting_ratio"))

    center_fig = go.Figure()
    center_fig.add_trace(
        go.Scatter(
            x=x_values,
            y=pos_cx,
            mode="lines+markers",
            name="after_position center_x",
        )
    )
    center_fig.add_trace(
        go.Scatter(
            x=x_values,
            y=pos_cy,
            mode="lines+markers",
            name="after_position center_y",
        )
    )
    center_fig.add_trace(
        go.Scatter(
            x=x_values,
            y=bolt_cx,
            mode="lines+markers",
            name="after_bolt center_x",
        )
    )
    center_fig.add_trace(
        go.Scatter(
            x=x_values,
            y=bolt_cy,
            mode="lines+markers",
            name="after_bolt center_y",
        )
    )
    center_fig.update_layout(
        title=f"{sweep_param} vs spot_center_x / spot_center_y",
        xaxis_title=sweep_param,
        yaxis_title="spot center",
        legend_title="series",
    )
    st.plotly_chart(center_fig, use_container_width=True)

    radius_fig = go.Figure()
    radius_fig.add_trace(
        go.Scatter(
            x=x_values,
            y=pos_rms,
            mode="lines+markers",
            name="after_position spot_rms_radius",
        )
    )
    radius_fig.add_trace(
        go.Scatter(
            x=x_values,
            y=bolt_rms,
            mode="lines+markers",
            name="after_bolt spot_rms_radius",
        )
    )
    radius_fig.update_layout(
        title=f"{sweep_param} vs spot_rms_radius",
        xaxis_title=sweep_param,
        yaxis_title="spot_rms_radius",
        legend_title="series",
    )
    st.plotly_chart(radius_fig, use_container_width=True)

    has_vignetting = any(v is not None for v in pos_vig + bolt_vig)
    if not has_vignetting:
        st.info(
            "現在の Recipe Service のスイープレスポンスには vignetting_ratio が含まれないため、"
            "vignetting グラフは表示できません"
        )
        return

    vignetting_fig = go.Figure()
    vignetting_fig.add_trace(
        go.Scatter(
            x=x_values,
            y=pos_vig,
            mode="lines+markers",
            name="after_position vignetting_ratio",
        )
    )
    vignetting_fig.add_trace(
        go.Scatter(
            x=x_values,
            y=bolt_vig,
            mode="lines+markers",
            name="after_bolt vignetting_ratio",
        )
    )
    vignetting_fig.update_layout(
        title=f"{sweep_param} vs vignetting_ratio",
        xaxis_title=sweep_param,
        yaxis_title="vignetting_ratio",
        legend_title="series",
    )
    st.plotly_chart(vignetting_fig, use_container_width=True)


def plot_trial_step_charts(steps: list[dict[str, Any]]) -> None:
    if not steps:
        st.info("ステップデータがありません")
        return

    x_steps: list[int] = []
    pos_cx: list[float | None] = []
    pos_cy: list[float | None] = []
    bolt_cx: list[float | None] = []
    bolt_cy: list[float | None] = []
    pos_rms: list[float | None] = []
    bolt_rms: list[float | None] = []

    for item in steps:
        x_steps.append(int(item.get("step_index", 0)))
        sim_pos = item.get("sim_after_position", {})
        sim_bolt = item.get("sim_after_bolt", {})

        pos_cx.append(_extract_metric(sim_pos, "spot_center_x"))
        pos_cy.append(_extract_metric(sim_pos, "spot_center_y"))
        bolt_cx.append(_extract_metric(sim_bolt, "spot_center_x"))
        bolt_cy.append(_extract_metric(sim_bolt, "spot_center_y"))
        pos_rms.append(_extract_metric(sim_pos, "spot_rms_radius"))
        bolt_rms.append(_extract_metric(sim_bolt, "spot_rms_radius"))

    center_fig = go.Figure()
    center_fig.add_trace(
        go.Scatter(
            x=x_steps,
            y=pos_cx,
            mode="lines+markers",
            name="after_position center_x",
        )
    )
    center_fig.add_trace(
        go.Scatter(
            x=x_steps,
            y=pos_cy,
            mode="lines+markers",
            name="after_position center_y",
        )
    )
    center_fig.add_trace(
        go.Scatter(
            x=x_steps,
            y=bolt_cx,
            mode="lines+markers",
            name="after_bolt center_x",
        )
    )
    center_fig.add_trace(
        go.Scatter(
            x=x_steps,
            y=bolt_cy,
            mode="lines+markers",
            name="after_bolt center_y",
        )
    )
    center_fig.update_layout(
        title="step_index vs spot_center_x / spot_center_y",
        xaxis_title="step_index",
        yaxis_title="spot center",
        legend_title="series",
    )
    st.plotly_chart(center_fig, use_container_width=True)

    rms_fig = go.Figure()
    rms_fig.add_trace(
        go.Scatter(
            x=x_steps,
            y=pos_rms,
            mode="lines+markers",
            name="after_position spot_rms_radius",
        )
    )
    rms_fig.add_trace(
        go.Scatter(
            x=x_steps,
            y=bolt_rms,
            mode="lines+markers",
            name="after_bolt spot_rms_radius",
        )
    )
    rms_fig.update_layout(
        title="step_index vs spot_rms_radius",
        xaxis_title="step_index",
        yaxis_title="spot_rms_radius",
        legend_title="series",
    )
    st.plotly_chart(rms_fig, use_container_width=True)


def render_spot_heatmap(
    title: str,
    ray_hits: list[dict[str, Any]] | None,
    spot_center_x: float | None = None,
    spot_center_y: float | None = None,
) -> None:
    """ray_hits の 2D 密度ヒートマップを描画し、spot_center を星マーカーで重ねる。"""
    if not ray_hits:
        st.info(f"{title}: ray_hits データなし")
        return

    xs = [float(h["x"]) for h in ray_hits]
    ys = [float(h["y"]) for h in ray_hits]

    fig = go.Figure()

    fig.add_trace(
        go.Histogram2dContour(
            x=xs,
            y=ys,
            colorscale="Hot",
            reversescale=True,
            ncontours=20,
            contours=dict(coloring="fill", showlines=False),
            showscale=True,
            colorbar=dict(title="density"),
            hoverinfo="skip",
            name="ray density",
        )
    )

    # 薄く散布点も重ねて分布の端を見やすくする
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            marker=dict(size=1.5, color="rgba(255,255,255,0.3)"),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    if spot_center_x is not None and spot_center_y is not None:
        fig.add_trace(
            go.Scatter(
                x=[spot_center_x],
                y=[spot_center_y],
                mode="markers",
                marker=dict(
                    symbol="star",
                    size=16,
                    color="cyan",
                    line=dict(width=1.5, color="black"),
                ),
                name="spot_center",
            )
        )

    # マージン付き自動スケール
    margin = 0.1  # 10% padding
    x_range = max(xs) - min(xs) if len(xs) > 1 else 0.01
    y_range = max(ys) - min(ys) if len(ys) > 1 else 0.01
    pad_x = x_range * margin
    pad_y = y_range * margin

    fig.update_layout(
        title=title,
        xaxis_title="X (mm) — Slow axis",
        yaxis_title="Y (mm) — Fast axis",
        xaxis=dict(
            range=[min(xs) - pad_x, max(xs) + pad_x],
            scaleanchor="y",
            scaleratio=1,
        ),
        yaxis=dict(range=[min(ys) - pad_y, max(ys) + pad_y]),
        height=420,
        margin=dict(l=50, r=50, t=40, b=50),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_camera_image(
    title: str,
    ray_hits: list[dict[str, Any]] | None,
    pixel_w: int,
    pixel_h: int,
    pixel_pitch_um: float,
    gaussian_sigma_px: float,
    spot_center_x: float | None = None,
    spot_center_y: float | None = None,
) -> None:
    """ray_hits をカメラセンサー上にビニングしてグレースケール画像として描画する。

    Parameters
    ----------
    pixel_w, pixel_h : センサーの解像度（ピクセル数）
    pixel_pitch_um : 1ピクセルの物理サイズ (um)
    gaussian_sigma_px : PSFガウシアンぼかしの σ (ピクセル単位、0=ぼかしなし)
    spot_center_x/y : 星マーカーで重ねるスポット中心 (mm)
    """
    if not ray_hits:
        st.info(f"{title}: ray_hits データなし")
        return

    xs = np.array([float(h["x"]) for h in ray_hits])
    ys = np.array([float(h["y"]) for h in ray_hits])

    # ピクセルピッチ → mm
    pitch_mm = pixel_pitch_um / 1000.0
    sensor_w_mm = pixel_w * pitch_mm
    sensor_h_mm = pixel_h * pitch_mm

    # 重心を中心にセンサーを配置
    cx = float(np.mean(xs))
    cy = float(np.mean(ys))
    x_min = cx - sensor_w_mm / 2
    x_max = cx + sensor_w_mm / 2
    y_min = cy - sensor_h_mm / 2
    y_max = cy + sensor_h_mm / 2

    # 2D ヒストグラムでビニング
    img, _ye, _xe = np.histogram2d(
        ys, xs,
        bins=[pixel_h, pixel_w],
        range=[[y_min, y_max], [x_min, x_max]],
    )

    # ガウシアンぼかし
    if gaussian_sigma_px > 0:
        img = gaussian_filter(img, sigma=gaussian_sigma_px)

    # 正規化 (0-255)
    img_max = img.max()
    if img_max > 0:
        img_norm = (img / img_max * 255).astype(np.uint8)
    else:
        img_norm = np.zeros((pixel_h, pixel_w), dtype=np.uint8)

    # plotly Heatmap でグレースケール表示（原点左下）
    fig = go.Figure()
    fig.add_trace(
        go.Heatmap(
            z=img_norm,
            x0=x_min,
            dx=pitch_mm,
            y0=y_min,
            dy=pitch_mm,
            colorscale="Gray",
            reversescale=False,
            showscale=False,
            hovertemplate="X: %{x:.4f} mm<br>Y: %{y:.4f} mm<br>intensity: %{z}<extra></extra>",
        )
    )

    if spot_center_x is not None and spot_center_y is not None:
        fig.add_trace(
            go.Scatter(
                x=[spot_center_x],
                y=[spot_center_y],
                mode="markers",
                marker=dict(
                    symbol="star",
                    size=14,
                    color="red",
                    line=dict(width=1.5, color="white"),
                ),
                name="spot_center",
                hovertemplate="spot_center<br>X: %{x:.4f} mm<br>Y: %{y:.4f} mm<extra></extra>",
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="X (mm) — Slow axis",
        yaxis_title="Y (mm) — Fast axis",
        xaxis=dict(scaleanchor="y", scaleratio=1),
        yaxis=dict(autorange=True),
        height=450,
        margin=dict(l=50, r=50, t=40, b=50),
    )
    st.plotly_chart(fig, use_container_width=True)

    # センサー外の光線数を報告
    in_sensor = np.sum((xs >= x_min) & (xs <= x_max) & (ys >= y_min) & (ys <= y_max))
    total = len(xs)
    if in_sensor < total:
        st.caption(
            f"センサー範囲外の光線: {total - in_sensor}/{total} "
            f"(センサー {sensor_w_mm:.3f} × {sensor_h_mm:.3f} mm)"
        )


def render_bolt_response_graph(
    bolt_params: dict[str, float],
    position_max: float,
    title: str,
) -> go.Figure:
    """Render bolt response graph showing displacement vs initial position.
    
    Shows deterministic displacement (Δx = a_x×x0^b_x, Δy = a_y×y0^b_y) as lines
    and noise ranges (±σ(|x0|)) as shaded bands.
    
    Args:
        bolt_params: Dictionary containing a_x, b_x, a_y, b_y, noise_base_x/y, noise_prop_x/y
        position_max: Maximum position for x-axis (mm)
        title: Graph title
    
    Returns:
        Plotly Figure object
    """
    # Extract parameters
    a_x = bolt_params.get("a_x", 0.0)
    b_x = bolt_params.get("b_x", 1.0)
    a_y = bolt_params.get("a_y", 0.0)
    b_y = bolt_params.get("b_y", 1.0)
    noise_base_x = bolt_params.get("noise_base_x", 0.0)
    noise_prop_x = bolt_params.get("noise_prop_x", 0.0)
    noise_base_y = bolt_params.get("noise_base_y", 0.0)
    noise_prop_y = bolt_params.get("noise_prop_y", 0.0)
    
    # Generate position values (symmetric around zero)
    pos = np.linspace(-position_max, position_max, 200)
    
    # Calculate deterministic displacements
    # Handle power function for negative values
    delta_x = np.sign(pos) * a_x * (np.abs(pos) ** b_x)
    delta_y = np.sign(pos) * a_y * (np.abs(pos) ** b_y)
    
    # Calculate position-dependent noise std (using absolute value for symmetry)
    sigma_x = np.maximum(0, noise_base_x + noise_prop_x * np.abs(pos))
    sigma_y = np.maximum(0, noise_base_y + noise_prop_y * np.abs(pos))
    
    # Create figure
    fig = go.Figure()
    
    # Add Δx line and noise band
    fig.add_trace(go.Scatter(
        x=pos, y=delta_x,
        mode="lines",
        name="Δx",
        line=dict(color="blue", width=2),
        hovertemplate="x0=%{x:.3f} mm<br>Δx=%{y:.5f} mm<extra></extra>",
    ))
    
    # Δx noise band (±σ_x)
    fig.add_trace(go.Scatter(
        x=np.concatenate([pos, pos[::-1]]),
        y=np.concatenate([delta_x + sigma_x, (delta_x - sigma_x)[::-1]]),
        fill="toself",
        fillcolor="rgba(0,0,255,0.2)",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))
    
    # Add Δy line and noise band
    fig.add_trace(go.Scatter(
        x=pos, y=delta_y,
        mode="lines",
        name="Δy",
        line=dict(color="red", width=2),
        hovertemplate="x0=%{x:.3f} mm<br>Δy=%{y:.5f} mm<extra></extra>",
    ))
    
    # Δy noise band (±σ_y)
    fig.add_trace(go.Scatter(
        x=np.concatenate([pos, pos[::-1]]),
        y=np.concatenate([delta_y + sigma_y, (delta_y - sigma_y)[::-1]]),
        fill="toself",
        fillcolor="rgba(255,0,0,0.2)",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))
    
    # Layout
    fig.update_layout(
        title=title,
        xaxis_title="初期位置 x0 (mm)",
        yaxis_title="変位 (mm)",
        height=350,
        margin=dict(l=50, r=20, t=40, b=50),
        legend=dict(x=0.02, y=0.98, bgcolor="rgba(255,255,255,0.8)"),
        hovermode="x unified",
    )
    
    return fig
