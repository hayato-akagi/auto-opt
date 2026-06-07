"""ページ2: 世代交代パイプライン

collection-orchestrator の /experiments/pipeline を呼んで世代交代学習を実行し、
ポーリングで進捗を可視化する。
"""

from __future__ import annotations

import math
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.api_client import RecipeApiClient

st.set_page_config(
    page_title="世代交代パイプライン",
    page_icon="🧬",
    layout="wide",
)

st.title("🧬 世代交代パイプライン")


def _client() -> RecipeApiClient:
    if "api_client" not in st.session_state:
        st.session_state["api_client"] = RecipeApiClient()
    return st.session_state["api_client"]


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

st.session_state.setdefault("pipeline_id", None)
st.session_state.setdefault("pipeline_status", None)
st.session_state.setdefault("pipeline_auto_refresh", True)


# ---------------------------------------------------------------------------
# Sidebar — pipeline settings
# ---------------------------------------------------------------------------

is_running = bool(
    st.session_state["pipeline_status"]
    and st.session_state["pipeline_status"].get("status") == "running"
)

with st.sidebar:
    st.markdown("## 🎯 対象実験")
    default_exp = st.session_state.get("last_experiment_id", "")
    experiment_id = st.text_input(
        "experiment_id",
        value=default_exp,
        help="🌍 環境設定ページで作成した実験 ID を貼り付けてください",
        disabled=is_running,
    )

    st.markdown("### 🎯 目標スポット (mm)")
    target_x = st.number_input("target X", value=0.0, step=0.05, format="%.3f", disabled=is_running)
    target_y = st.number_input("target Y", value=0.0, step=0.05, format="%.3f", disabled=is_running)

    st.markdown("---")
    st.markdown("## 📦 データ収集")
    n_parallel_envs = st.slider("並列環境数", 1, 200, 10, disabled=is_running)
    trials_per_env = st.slider("環境あたり試行数", 1, 10, 1, disabled=is_running)
    max_steps = st.slider("最大ステップ", 1, 50, 10, disabled=is_running)
    tolerance = st.number_input("収束許容 (mm)", value=0.001, min_value=0.0001, step=0.0001, format="%.4f", disabled=is_running)

    st.markdown("### 🤖 Gen0 コントローラー")
    gen0_controller = st.radio(
        "Gen0 に使うコントローラー",
        options=["simple-controller", "adaptive-controller"],
        index=0,
        disabled=is_running,
        help=(
            "**simple-controller**: 比例制御のみ（デフォルト）\n\n"
            "**adaptive-controller**: Step0の観測からbolt_shiftを推定して即座に補正。"
            "収束が速く、質の高いGen0データが得られる可能性がある。"
        ),
    )
    adaptive_alpha = 1.0
    if gen0_controller == "adaptive-controller":
        adaptive_alpha = st.slider(
            "bolt_shift 推定の更新率 (alpha)",
            min_value=0.1, max_value=1.0, value=1.0, step=0.1,
            disabled=is_running,
            help="1.0 = 最新観測のみ使用（線形ボルト向け）。小さいほど過去の推定を重視（非線形ボルト向け）。",
        )

    st.markdown("### 🎲 初期位置・緩めノイズ")
    initial_coll_range = st.slider(
        "初期コリメータ位置ランダム幅 (mm)",
        min_value=0.0, max_value=0.3, value=0.05, step=0.01,
        disabled=is_running,
        help="各試行の初期レンズ位置を ±range でランダムサンプリング。0 = 全試行が (0,0) スタート。",
    )
    release_std = st.slider(
        "ボルト緩め観測ノイズ std (mm)",
        min_value=0.0, max_value=0.05, value=0.01, step=0.001,
        format="%.3f",
        disabled=is_running,
        help="ボルト緩め後に制御器が見るスポット位置にガウスノイズを加算。実機の緩め時観測誤差を模倣。",
    )

    st.markdown("---")
    st.markdown("## 🧠 モデル設定")
    gen1plus_controller = st.radio(
        "Gen1+ コントローラー (学習モデルを使用)",
        options=["ai-controller (MLP)", "lstm-controller (LSTM)"],
        index=0,
        disabled=is_running,
        help=(
            "**ai-controller**: 固定幅ウィンドウ入力 MLP（デフォルト）\n\n"
            "**lstm-controller**: ステップを順次処理する LSTM。"
            "試行内で隠れ状態が更新されるため、環境への動的適応が期待できる。"
        ),
    )
    use_lstm = gen1plus_controller.startswith("lstm")
    gen1plus_controller_key = "lstm-controller" if use_lstm else "ai-controller"

    n_history = st.slider(
        "履歴ステップ N",
        1, 10, 3,
        disabled=is_running or use_lstm,
        help="LSTM では固定窓を使わないため無効",
    )
    hidden_dim = st.selectbox("隠れ層サイズ", [64, 128, 256, 512], index=1, disabled=is_running)
    num_layers = 2
    if use_lstm:
        num_layers = st.slider("LSTM 層数", 1, 4, 2, disabled=is_running)
    epochs = st.slider("エポック数", 1, 100, 20, disabled=is_running)
    only_converged = st.checkbox("収束したtrialのみ学習", value=False, disabled=is_running)
    warm_start = st.checkbox(
        "累積学習 (前世代の重みから warm-start)",
        value=True,
        disabled=is_running,
        help="前世代のモデルを初期重みとして学習を継続します。アーキテクチャが一致しない場合は自動的にスクラッチから学習。",
    )

    st.markdown("---")
    st.markdown("## 📚 追加学習データ")
    extra_exp_ids_raw = st.text_area(
        "過去パイプラインの experiment_id（1行1件）",
        value="",
        height=80,
        disabled=is_running,
        help="別パイプラインで収集したデータを今回の学習にも使いたい場合に指定。現在のパイプラインのデータと合算して学習します。",
    )
    extra_experiment_ids = [e.strip() for e in extra_exp_ids_raw.splitlines() if e.strip()]

    st.markdown("---")
    st.markdown("## 🌐 環境分布 (bolt_model variation)")
    use_bolt_dist = st.checkbox(
        "環境ごとに bolt_model をサンプル",
        value=False,
        disabled=is_running,
        help="各並列環境に対し、以下の範囲から独立に bolt_model パラメータをサンプルします。",
    )
    bolt_dist_payload: dict | None = None
    if use_bolt_dist:
        bolt_seed = st.number_input("サンプリング seed", value=0, step=1, disabled=is_running)
        st.caption("各パラメータの [min, max] を指定。min==max なら固定値。")
        with st.expander("🔩 Upper bolt 範囲", expanded=True):
            up_bx = st.slider("x0_bias_x", -0.2, 0.2, (0.0, 0.1), step=0.01, disabled=is_running)
            up_by = st.slider("x0_bias_y", -0.2, 0.2, (0.0, 0.0), step=0.01, disabled=is_running)
            up_ax = st.slider("a_x", -0.1, 0.1, (0.01, 0.05), step=0.005, disabled=is_running)
            up_ay = st.slider("a_y", -0.1, 0.1, (0.0, 0.0), step=0.005, disabled=is_running)
            up_bbx = st.slider("b_x", 0.5, 2.0, (0.9, 1.1), step=0.05, disabled=is_running)
            up_bby = st.slider("b_y", 0.5, 2.0, (1.0, 1.0), step=0.05, disabled=is_running)
        with st.expander("🔩 Lower bolt 範囲", expanded=False):
            lo_bx = st.slider("L: x0_bias_x", -0.2, 0.2, (0.0, 0.0), step=0.01, disabled=is_running)
            lo_by = st.slider("L: x0_bias_y", -0.2, 0.2, (0.0, 0.0), step=0.01, disabled=is_running)
            lo_ax = st.slider("L: a_x", -0.1, 0.1, (0.0, 0.0), step=0.005, disabled=is_running)
            lo_ay = st.slider("L: a_y", -0.1, 0.1, (0.0, 0.0), step=0.005, disabled=is_running)
            lo_bbx = st.slider("L: b_x", 0.5, 2.0, (1.0, 1.0), step=0.05, disabled=is_running)
            lo_bby = st.slider("L: b_y", 0.5, 2.0, (1.0, 1.0), step=0.05, disabled=is_running)
        bolt_dist_payload = {
            "upper": {
                "x0_bias_x": list(up_bx), "x0_bias_y": list(up_by),
                "a_x": list(up_ax), "b_x": list(up_bbx),
                "a_y": list(up_ay), "b_y": list(up_bby),
                "noise_ratio_min_x": 0.01, "noise_ratio_max_x": 0.05,
                "noise_ratio_min_y": 0.01, "noise_ratio_max_y": 0.05,
            },
            "lower": {
                "x0_bias_x": list(lo_bx), "x0_bias_y": list(lo_by),
                "a_x": list(lo_ax), "b_x": list(lo_bbx),
                "a_y": list(lo_ay), "b_y": list(lo_bby),
                "noise_ratio_min_x": 0.01, "noise_ratio_max_x": 0.05,
                "noise_ratio_min_y": 0.01, "noise_ratio_max_y": 0.05,
            },
            "seed": int(bolt_seed),
        }

    st.markdown("---")
    st.markdown("## ⏱ タイムアウト設定")
    train_timeout_sec = st.slider(
        "学習タイムアウト (秒)",
        min_value=300, max_value=7200, value=1800, step=300,
        disabled=is_running,
        help="1世代あたりの学習最大待機時間。LSTMは長めに設定してください。",
    )

    st.markdown("---")
    st.markdown("## 🔁 世代交代")
    n_generations = st.slider("総世代数", 1, 30, 5, disabled=is_running)
    target_success_rate = st.slider("目標合格率 (%)", 50, 100, 95, disabled=is_running) / 100
    early_stopping_patience = st.slider("早期停止 patience", 1, 10, 3, disabled=is_running)

    st.markdown("---")
    st.session_state["pipeline_auto_refresh"] = st.checkbox(
        "自動更新（2秒）", value=st.session_state["pipeline_auto_refresh"]
    )


# ---------------------------------------------------------------------------
# Control panel
# ---------------------------------------------------------------------------

col_a, col_b, col_c = st.columns([1, 1, 3])

with col_a:
    start_disabled = is_running or not experiment_id.strip()
    if st.button("▶️ パイプライン開始", type="primary", disabled=start_disabled, use_container_width=True):
        payload = {
            "experiment_id": experiment_id.strip(),
            "config": {
                "gen0_controller": gen0_controller,
                "gen1plus_controller": gen1plus_controller_key,
                "adaptive_alpha": float(adaptive_alpha),
                "n_parallel_envs": int(n_parallel_envs),
                "trials_per_env": int(trials_per_env),
                "n_generations": int(n_generations),
                "max_steps": int(max_steps),
                "tolerance": float(tolerance),
                "controller_config": {
                    "release_perturbation": {
                        "std_x": float(release_std),
                        "std_y": float(release_std),
                    },
                },
                "initial_coll_range_x": float(initial_coll_range),
                "initial_coll_range_y": float(initial_coll_range),
                "target": {"spot_center_x": float(target_x), "spot_center_y": float(target_y)},
                "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
                "model_config_train": {
                    "n_history": int(n_history),
                    "hidden_dim": int(hidden_dim),
                    "num_layers": int(num_layers),
                    "epochs": int(epochs),
                    "batch_size": 32,
                    "learning_rate": 1e-3,
                    "only_converged": bool(only_converged),
                    "warm_start": bool(warm_start),
                },
                "stopping": {
                    "target_success_rate": float(target_success_rate),
                    "early_stopping_patience": int(early_stopping_patience),
                },
                "extra_experiment_ids": extra_experiment_ids,
                "bolt_distribution": bolt_dist_payload,
                "poll_interval_sec": 2.0,
                "train_timeout_sec": float(train_timeout_sec),
            },
        }
        created = _client().start_pipeline(payload)
        if created and "pipeline_id" in created:
            st.session_state["pipeline_id"] = created["pipeline_id"]
            st.session_state["pipeline_status"] = {"status": "running"}
            st.success(f"✅ pipeline_id = {created['pipeline_id']}")
            time.sleep(0.3)
            st.rerun()

with col_b:
    if st.button("🔄 状態取得", use_container_width=True, disabled=not st.session_state["pipeline_id"]):
        st.rerun()

with col_c:
    if st.session_state["pipeline_id"]:
        st.code(f"pipeline_id = {st.session_state['pipeline_id']}", language="text")
    elif not experiment_id.strip():
        st.warning("⚠️ experiment_id を入力してください")


st.markdown("---")

# ---------------------------------------------------------------------------
# Polling & status display
# ---------------------------------------------------------------------------

pipeline_id = st.session_state["pipeline_id"]
status: dict | None = None
if pipeline_id:
    status = _client().get_pipeline_status(pipeline_id)
    if status:
        st.session_state["pipeline_status"] = status

if status:
    st.subheader("📊 パイプライン進捗")
    top1, top2, top3, top4 = st.columns(4)
    with top1:
        st.metric("ステータス", status.get("status", "?"))
    with top2:
        st.metric("世代", f"{status.get('current_generation', 0)} / {status.get('total_generations', 0)}")
    with top3:
        st.metric("進捗", f"{status.get('progress', 0.0) * 100:.1f}%")
    with top4:
        st.metric("開始", str(status.get("started_at", ""))[:19])

    st.progress(float(status.get("progress", 0.0) or 0.0))

    if status.get("error"):
        st.error(f"パイプラインエラー: {status['error']}")

    # 世代ごとの学習エラーを展開表示
    for g in status.get("generations", []):
        if g.get("status") == "failed" and g.get("error"):
            with st.expander(f"🔴 Gen{g['gen_id']} エラー詳細", expanded=True):
                st.code(g["error"], language="text")

    generations = status.get("generations", [])
    if generations:
        df = pd.DataFrame(generations)
        if "final_train_loss" in df.columns:
            df["rmse_um"] = df["final_train_loss"].apply(
                lambda v: round(math.sqrt(max(v, 0)) * 1000, 3) if v is not None else None
            )
        cols = [
            "gen_id", "status", "controller",
            "total_trials", "converged_trials", "success_rate",
            "rmse_um", "train_job_id", "model_path",
            "started_at", "finished_at", "error",
        ]
        df = df[[c for c in cols if c in df.columns]]
        st.dataframe(df, use_container_width=True, hide_index=True)

        # success rate over generations
        if "success_rate" in df.columns and df["success_rate"].notna().any():
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=df["gen_id"],
                    y=df["success_rate"] * 100,
                    mode="lines+markers",
                    name="合格率 (%)",
                    line=dict(color="blue", width=3),
                )
            )
            if "final_train_loss" in df.columns and df["final_train_loss"].notna().any():
                fig.add_trace(
                    go.Scatter(
                        x=df["gen_id"],
                        y=df["final_train_loss"].apply(lambda v: math.sqrt(max(v, 0)) * 1000 if v is not None else None),
                        mode="lines+markers",
                        name="RMSE (μm)",
                        yaxis="y2",
                        line=dict(color="red", width=2, dash="dot"),
                    )
                )
            fig.update_layout(
                title="世代ごとの合格率と学習ロス",
                xaxis_title="世代",
                yaxis=dict(title="合格率 (%)", side="left", range=[0, 100]),
                yaxis2=dict(title="RMSE (μm)", overlaying="y", side="right"),
                hovermode="x unified",
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)

        # --- Detailed per-generation metrics ---
        st.markdown("#### 🔬 世代別 詳細メトリクス")
        gens_with_data = [
            g for g in generations
            if g.get("steps_per_trial") or g.get("final_distances") or g.get("epoch_losses")
        ]
        if gens_with_data:
            gen_ids = [g["gen_id"] for g in gens_with_data]

            # Steps per trial box plot
            box_fig = go.Figure()
            for g in gens_with_data:
                steps = g.get("steps_per_trial") or []
                if steps:
                    box_fig.add_trace(go.Box(y=steps, name=f"gen{g['gen_id']}", boxmean=True))
            if box_fig.data:
                box_fig.update_layout(
                    title="trial 収束ステップ数の分布",
                    yaxis_title="steps",
                    xaxis_title="世代",
                    height=350,
                )
                st.plotly_chart(box_fig, use_container_width=True)

            # Final distance histogram
            dist_fig = go.Figure()
            for g in gens_with_data:
                dists = g.get("final_distances") or []
                if dists:
                    dist_fig.add_trace(
                        go.Histogram(
                            x=dists,
                            name=f"gen{g['gen_id']}",
                            opacity=0.6,
                            nbinsx=30,
                        )
                    )
            if dist_fig.data:
                dist_fig.update_layout(
                    title="最終距離の分布 (mm)",
                    xaxis_title="final_distance (mm)",
                    yaxis_title="trial 数",
                    barmode="overlay",
                    height=350,
                )
                st.plotly_chart(dist_fig, use_container_width=True)

            # Epoch loss curves (RMSE in μm) — interactive controls
            gens_with_loss = [g for g in gens_with_data if g.get("epoch_losses")]
            if gens_with_loss:
                st.markdown("##### 📉 エポック毎の学習ロス (RMSE)")
                ctrl_col1, ctrl_col2 = st.columns([3, 1])
                with ctrl_col1:
                    all_gen_ids = [g["gen_id"] for g in gens_with_loss]
                    selected_gen_ids = st.multiselect(
                        "表示する世代",
                        options=all_gen_ids,
                        default=all_gen_ids,
                        format_func=lambda g: f"Gen {g}",
                        key="loss_curve_gen_select",
                    )
                with ctrl_col2:
                    y_scale = st.radio(
                        "Y軸スケール",
                        options=["対数", "線形"],
                        index=0,
                        horizontal=True,
                        key="loss_curve_scale",
                    )

                loss_fig = go.Figure()
                for g in gens_with_loss:
                    if g["gen_id"] not in selected_gen_ids:
                        continue
                    losses = g.get("epoch_losses") or []
                    rmse_um = [math.sqrt(max(l, 0)) * 1000 for l in losses]
                    loss_fig.add_trace(
                        go.Scatter(
                            x=list(range(1, len(rmse_um) + 1)),
                            y=rmse_um,
                            mode="lines",
                            name=f"Gen {g['gen_id']}",
                        )
                    )
                if loss_fig.data:
                    loss_fig.add_hline(
                        y=1.0,
                        line_dash="dash",
                        line_color="green",
                        annotation_text="目標: 1 μm",
                        annotation_position="bottom right",
                    )
                    loss_fig.update_layout(
                        xaxis_title="epoch",
                        yaxis_title="RMSE (μm)",
                        yaxis_type="log" if y_scale == "対数" else "linear",
                        hovermode="x unified",
                        height=380,
                        margin=dict(t=20),
                    )
                    st.plotly_chart(loss_fig, use_container_width=True)
    else:
        st.info("まだ世代結果がありません。")

    # -----------------------------------------------------------------------
    # Trajectory viewer
    # -----------------------------------------------------------------------
    st.markdown("---")
    st.markdown("#### 🔍 軌跡ビューア")
    st.caption("○: ボルト締め前スポット（位置決め後）　■: ボルト締め後スポット　実線: 締め動作　点線: 緩め→再調整")

    exp_id_for_traj = status.get("experiment_id") if status else None
    gens_with_trials = [
        g for g in (status.get("generations") or []) if g.get("trial_ids")
    ] if status else []

    if not gens_with_trials:
        st.info("trial_ids がまだ記録されていません。次回パイプライン実行から自動収集されます。")
    else:
        traj_col1, traj_col2, traj_col3 = st.columns([2, 1, 1])
        with traj_col1:
            traj_gen_id = st.selectbox(
                "世代",
                options=[g["gen_id"] for g in gens_with_trials],
                format_func=lambda g: f"Gen {g}  ({next(x['controller'] for x in gens_with_trials if x['gen_id']==g)})",
                key="traj_gen_select",
            )
        with traj_col2:
            traj_target_x = st.number_input("目標X (mm)", value=0.0, format="%.4f", key="traj_tx")
        with traj_col3:
            traj_target_y = st.number_input("目標Y (mm)", value=0.0, format="%.4f", key="traj_ty")

        gen_data = next(g for g in gens_with_trials if g["gen_id"] == traj_gen_id)
        all_trial_ids = gen_data.get("trial_ids", [])

        selected_trial_ids = st.multiselect(
            f"試行を選択（全 {len(all_trial_ids)} 件）",
            options=all_trial_ids,
            default=all_trial_ids[:min(5, len(all_trial_ids))],
            format_func=lambda t: f"…{t[-12:]}",
            key="traj_trial_select",
        )

        cache_key = f"traj_steps_{exp_id_for_traj}_{'_'.join(selected_trial_ids)}"
        fetch_btn = st.button("📥 ステップデータを取得", key="traj_fetch", disabled=not selected_trial_ids)

        if fetch_btn and selected_trial_ids:
            with st.spinner(f"{len(selected_trial_ids)} 試行のステップデータを取得中..."):
                fetched: dict = {}
                for tid in selected_trial_ids:
                    steps = _client().list_steps(exp_id_for_traj, tid)
                    if steps:
                        fetched[tid] = steps
                st.session_state[cache_key] = fetched

        trials_steps: dict = st.session_state.get(cache_key, {})

        if trials_steps:
            _TRAJ_COLORS = [
                "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
            ]

            def _build_traj_fig(t_steps: dict, space: str, tgt_x: float, tgt_y: float) -> go.Figure:
                fig = go.Figure()

                def _pts(step: dict) -> tuple[float, float, float, float]:
                    if space == "spot":
                        pre = step.get("sim_after_position") or {}
                        pst = step.get("sim_after_bolt") or {}
                        return (
                            float(pre.get("spot_center_x", 0)),
                            float(pre.get("spot_center_y", 0)),
                            float(pst.get("spot_center_x", 0)),
                            float(pst.get("spot_center_y", 0)),
                        )
                    else:
                        pre = step.get("after_position") or {}
                        pst = step.get("after_bolt") or {}
                        return (
                            float(pre.get("actual_x", 0)),
                            float(pre.get("actual_y", 0)),
                            float(pst.get("final_x", 0)),
                            float(pst.get("final_y", 0)),
                        )

                for i, (tid, steps) in enumerate(t_steps.items()):
                    if not steps:
                        continue
                    color = _TRAJ_COLORS[i % len(_TRAJ_COLORS)]
                    label = f"…{tid[-10:]}"

                    pxs, pys, qxs, qys = [], [], [], []
                    for s in steps:
                        px, py, qx, qy = _pts(s)
                        pxs.append(px); pys.append(py)
                        qxs.append(qx); qys.append(qy)

                    # Solid lines: pre→post (bolt tightening)
                    sx, sy = [], []
                    for n in range(len(steps)):
                        sx += [pxs[n], qxs[n], None]
                        sy += [pys[n], qys[n], None]
                    fig.add_trace(go.Scatter(
                        x=sx, y=sy, mode="lines",
                        line=dict(color=color, width=2.5),
                        name=label, legendgroup=tid, showlegend=True,
                    ))

                    # Dashed lines: post[n]→pre[n+1] (bolt loosening + reposition)
                    if len(steps) > 1:
                        dx, dy = [], []
                        for n in range(len(steps) - 1):
                            dx += [qxs[n], pxs[n + 1], None]
                            dy += [qys[n], pys[n + 1], None]
                        fig.add_trace(go.Scatter(
                            x=dx, y=dy, mode="lines",
                            line=dict(color=color, width=1.5, dash="dash"),
                            legendgroup=tid, showlegend=False,
                        ))

                    # Pre-bolt markers (circle-open)
                    fig.add_trace(go.Scatter(
                        x=pxs, y=pys, mode="markers",
                        marker=dict(symbol="circle-open", size=9, color=color, line=dict(width=2)),
                        hovertext=[f"{label} Step {s.get('step_index','?')} 位置決め後<br>({px:.4f}, {py:.4f})"
                                   for s, px, py in zip(steps, pxs, pys)],
                        hoverinfo="text",
                        legendgroup=tid, showlegend=False,
                    ))

                    # Post-bolt markers (filled square)
                    fig.add_trace(go.Scatter(
                        x=qxs, y=qys, mode="markers",
                        marker=dict(symbol="square", size=7, color=color),
                        hovertext=[f"{label} Step {s.get('step_index','?')} ボルト締め後<br>({qx:.4f}, {qy:.4f})"
                                   for s, qx, qy in zip(steps, qxs, qys)],
                        hoverinfo="text",
                        legendgroup=tid, showlegend=False,
                    ))

                    # Start marker (larger circle)
                    fig.add_trace(go.Scatter(
                        x=[pxs[0]], y=[pys[0]], mode="markers",
                        marker=dict(symbol="circle", size=13, color=color,
                                    line=dict(color="white", width=2)),
                        hovertext=f"{label} START ({pxs[0]:.4f}, {pys[0]:.4f})",
                        hoverinfo="text",
                        legendgroup=tid, showlegend=False,
                    ))

                # Target
                fig.add_trace(go.Scatter(
                    x=[tgt_x], y=[tgt_y], mode="markers",
                    marker=dict(symbol="cross", size=18, color="red",
                                line=dict(color="red", width=3)),
                    name="目標", showlegend=True,
                ))

                ax_label = "スポット位置 (mm)" if space == "spot" else "コリメータ位置 (mm)"
                fig.update_layout(
                    xaxis_title=f"X {ax_label}",
                    yaxis_title=f"Y {ax_label}",
                    yaxis_scaleanchor="x",
                    yaxis_scaleratio=1,
                    hovermode="closest",
                    height=520,
                    legend=dict(orientation="v"),
                    margin=dict(t=10),
                )
                return fig

            tab_spot, tab_coll = st.tabs(["📍 スポット空間", "🔧 コリメータ空間"])
            with tab_spot:
                st.plotly_chart(
                    _build_traj_fig(trials_steps, "spot", traj_target_x, traj_target_y),
                    use_container_width=True,
                )
            with tab_coll:
                st.plotly_chart(
                    _build_traj_fig(trials_steps, "coll", traj_target_x, traj_target_y),
                    use_container_width=True,
                )
        elif selected_trial_ids:
            st.info("「📥 ステップデータを取得」を押してください。")

    # auto refresh
    if status.get("status") == "running" and st.session_state["pipeline_auto_refresh"]:
        time.sleep(2.0)
        st.rerun()
elif pipeline_id:
    st.warning("パイプライン情報を取得できませんでした。")
else:
    st.info("パイプラインはまだ開始されていません。サイドバーで設定してから ▶️ で開始してください。")
