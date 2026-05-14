"""
Result Comparison Screen (Screen 4)

Compare performance of different controllers (baseline vs AI) across multiple trials.
Display metrics: convergence rate, median error, p95 error, average steps.
"""

from __future__ import annotations

import math
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from app.api_client import RecipeApiClient


def _select_experiment(api_client: RecipeApiClient) -> str | None:
    """Select experiment for comparison"""
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
        "対象実験",
        options=experiment_ids,
        index=index,
        key="comparison_experiment_select",
        format_func=lambda exp_id: (
            f"{exp_id} | {id_to_experiment[exp_id]['name']} "
            f"({id_to_experiment[exp_id].get('engine_type', 'KrakenOS')})"
        ),
    )
    st.session_state["selected_experiment_id"] = selected_id
    return selected_id


def _compute_trial_metrics(
    api_client: RecipeApiClient,
    experiment_id: str,
    trial_id: str,
) -> dict[str, Any] | None:
    """Compute metrics for a single trial: convergence, final distance, step count"""
    steps = api_client.list_steps(experiment_id, trial_id)
    if steps is None or not steps:
        return None

    # Compute final position error (distance from target)
    final_step = steps[-1]
    sim_after_bolt = final_step.get("sim_after_bolt", {})
    final_x = sim_after_bolt.get("spot_center_x", 0.0)
    final_y = sim_after_bolt.get("spot_center_y", 0.0)
    final_distance = math.sqrt(final_x**2 + final_y**2)

    return {
        "trial_id": trial_id,
        "step_count": len(steps),
        "final_distance_mm": final_distance,
    }


def _compute_controller_stats(
    api_client: RecipeApiClient,
    experiment_id: str,
    algorithm: str,
) -> dict[str, Any] | None:
    """Compute aggregated statistics for all trials with given algorithm"""
    trials = api_client.list_trials(experiment_id)
    if trials is None:
        return None

    # Filter trials by control algorithm
    matching_trials = [
        t for t in trials
        if t.get("control", {}).get("algorithm") == algorithm
    ]

    if not matching_trials:
        return None

    # Compute metrics for each trial
    metrics_list = []
    for trial in matching_trials:
        trial_id = trial.get("trial_id")
        if not trial_id:
            continue
        metrics = _compute_trial_metrics(api_client, experiment_id, trial_id)
        if metrics:
            metrics_list.append(metrics)

    if not metrics_list:
        return None

    # Aggregate statistics
    final_distances = [m["final_distance_mm"] for m in metrics_list]
    step_counts = [m["step_count"] for m in metrics_list]

    tolerance = 0.05  # mm, standard tolerance
    converged = sum(1 for d in final_distances if d <= tolerance)
    convergence_rate = converged / len(final_distances)

    final_distances.sort()
    n = len(final_distances)
    median_error = final_distances[n // 2] if n > 0 else 0.0
    p95_error = final_distances[int(n * 0.95)] if n > 1 else final_distances[0]
    avg_steps = sum(step_counts) / len(step_counts) if step_counts else 0.0

    return {
        "algorithm": algorithm,
        "trial_count": len(final_distances),
        "convergence_rate": convergence_rate,
        "median_error_mm": median_error,
        "p95_error_mm": p95_error,
        "avg_steps": avg_steps,
        "min_error_mm": min(final_distances),
        "max_error_mm": max(final_distances),
        "all_distances": final_distances,
        "all_steps": step_counts,
    }


def render(api_client: RecipeApiClient) -> None:
    """Main render function for result comparison screen"""
    st.header("4️⃣ 結果比較")
    st.caption("複数のコントローラー性能を比較します")

    experiment_id = _select_experiment(api_client)
    if experiment_id is None:
        st.info("最初に実験を作成してください")
        return

    # Update global context
    st.session_state["selected_experiment_id"] = experiment_id

    st.divider()
    st.subheader("コントローラー選択")

    col1, col2 = st.columns(2)
    with col1:
        compare_baseline = st.checkbox("ベースライン (simple-controller)", value=True, key="compare_baseline")
    with col2:
        compare_ai = st.checkbox("AI コントローラー (ai-controller)", value=True, key="compare_ai")

    if not (compare_baseline or compare_ai):
        st.warning("少なくとも1つのコントローラーを選択してください")
        return

    # Compute statistics
    algorithms_to_compare = []
    if compare_baseline:
        algorithms_to_compare.append("simple-controller")
    if compare_ai:
        algorithms_to_compare.append("ai-controller")

    st.divider()
    st.markdown("#### 比較結果")

    stats_dict: dict[str, dict[str, Any]] = {}
    for algo in algorithms_to_compare:
        stats = _compute_controller_stats(api_client, experiment_id, algo)
        if stats:
            stats_dict[algo] = stats
        else:
            st.warning(f"{algo}: 該当する試行がありません")

    if not stats_dict:
        st.info("比較対象のデータがまだありません。先にデータを収集してください")
        return

    # Display metrics table
    st.markdown("**メトリクス一覧**")
    rows = []
    for algo, stats in stats_dict.items():
        rows.append({
            "コントローラー": algo,
            "試行数": stats["trial_count"],
            "収束率": f"{stats['convergence_rate']*100:.1f}%",
            "中央値誤差 (mm)": f"{stats['median_error_mm']:.4f}",
            "95%ile誤差 (mm)": f"{stats['p95_error_mm']:.4f}",
            "平均ステップ数": f"{stats['avg_steps']:.1f}",
            "最小誤差 (mm)": f"{stats['min_error_mm']:.4f}",
            "最大誤差 (mm)": f"{stats['max_error_mm']:.4f}",
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # Display bar charts for key metrics
    st.divider()
    st.markdown("**メトリクス比較グラフ**")

    labels = list(stats_dict.keys())
    convergence_rates = [stats_dict[algo]["convergence_rate"] * 100 for algo in labels]
    median_errors = [stats_dict[algo]["median_error_mm"] for algo in labels]
    p95_errors = [stats_dict[algo]["p95_error_mm"] for algo in labels]
    avg_steps = [stats_dict[algo]["avg_steps"] for algo in labels]

    # Metric 1: Convergence Rate
    fig1 = go.Figure()
    fig1.add_trace(go.Bar(x=labels, y=convergence_rates, marker_color="#2ca02c", text=[f"{v:.1f}%" for v in convergence_rates], textposition="outside"))
    fig1.update_layout(
        title="収束率",
        yaxis_title="収束率 (%)",
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig1, use_container_width=True)

    # Metric 2: Errors (median + p95)
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=labels, y=median_errors, name="中央値誤差 (mm)", marker_color="#1f77b4"))
    fig2.add_trace(go.Bar(x=labels, y=p95_errors, name="95%ile誤差 (mm)", marker_color="#ff7f0e"))
    fig2.update_layout(
        title="最終位置誤差",
        yaxis_title="誤差 (mm)",
        barmode="group",
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig2, use_container_width=True)

    # Metric 3: Average Steps
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=labels, y=avg_steps, marker_color="#9467bd", text=[f"{v:.1f}" for v in avg_steps], textposition="outside"))
    fig3.update_layout(
        title="平均ステップ数",
        yaxis_title="ステップ数",
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig3, use_container_width=True)

    # Distribution plots
    st.divider()
    st.markdown("**誤差分布**")

    fig4 = go.Figure()
    colors = ["#2ca02c", "#ff7f0e", "#d62728"]
    for idx, (algo, stats) in enumerate(stats_dict.items()):
        distances = stats["all_distances"]
        fig4.add_trace(go.Histogram(
            x=distances,
            name=algo,
            opacity=0.7,
            marker_color=colors[idx % len(colors)],
        ))
    fig4.update_layout(
        title="最終位置誤差分布",
        xaxis_title="誤差 (mm)",
        yaxis_title="試行数",
        barmode="overlay",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig4, use_container_width=True)

    # Trials detail
    st.divider()
    st.markdown("**試行詳細**")

    for algo, stats in stats_dict.items():
        with st.expander(f"{algo} - 全試行データ"):
            trial_rows = []
            for i, (distance, steps) in enumerate(zip(stats["all_distances"], stats["all_steps"]), 1):
                tolerance = 0.05
                converged = "✅" if distance <= tolerance else "❌"
                trial_rows.append({
                    "試行#": i,
                    "収束": converged,
                    "最終誤差 (mm)": f"{distance:.4f}",
                    "ステップ数": steps,
                })
            st.dataframe(trial_rows, use_container_width=True, hide_index=True)

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
        st.dataframe(_build_step_rows(steps), width="stretch", hide_index=True)
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
                    st.image(ray_path, caption=f"光路図 ({phase})", width="stretch")
                else:
                    st.info("光路図を取得できませんでした")
