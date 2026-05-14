"""
Model Creation Screen (Screen 3) - 3-Step Wizard

Step 1: Model Selection - Choose model type and configure name
Step 2: Data Collection - Configure collection parameters and trigger collection job
Step 3: Training & Learning - Train the model and monitor results

This consolidates model creation (ai_control), data collection (collection), and training (training).
"""

from __future__ import annotations

from typing import Any

import math
import plotly.graph_objects as go
import streamlit as st

from app.api_client import RecipeApiClient


def _select_experiment(api_client: RecipeApiClient) -> str | None:
    """Select experiment for model training"""
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
        key="model_creation_experiment_select",
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


def _render_step1_model_selection(api_client: RecipeApiClient) -> dict[str, Any] | None:
    """Step 1: Model selection and configuration"""
    st.subheader("1️⃣ モデルタイプ選択")
    st.caption("学習するモデルのタイプと名前を指定します")

    wizard_state = st.session_state.get("model_creation_wizard", {})

    with st.form("model_selection_form"):
        model_type = st.radio(
            "モデルタイプ",
            ["mlp", "baseline_only"],
            captions=["DNN残差モデル (推奨)", "ベースラインのみ（検証用）"],
            index=0,
            key="model_type_radio",
        )

        model_name = st.text_input(
            "モデル名",
            value=wizard_state.get("model_name", f"model_{model_type}_001"),
            key="model_name_input",
        )

        st.markdown("#### トレーニングパラメータ")
        col1, col2 = st.columns(2)
        with col1:
            epochs = st.number_input(
                "エポック数",
                min_value=1,
                max_value=500,
                value=wizard_state.get("epochs", 50),
                step=10,
                key="model_epochs",
            )
        with col2:
            batch_size = st.number_input(
                "バッチサイズ",
                min_value=1,
                max_value=256,
                value=wizard_state.get("batch_size", 32),
                step=8,
                key="model_batch_size",
            )

        step1_submit = st.form_submit_button("次へ: データ収集 →", type="primary")

    if step1_submit:
        # Save state
        wizard_state.update({
            "model_type": model_type,
            "model_name": model_name,
            "epochs": int(epochs),
            "batch_size": int(batch_size),
            "step1_complete": True,
        })
        st.session_state["model_creation_wizard"] = wizard_state
        return wizard_state

    return None


def _render_step2_data_collection(api_client: RecipeApiClient, experiment_id: str) -> dict[str, Any] | None:
    """Step 2: Data collection configuration"""
    st.subheader("2️⃣ データ収集")
    st.caption("ベースラインコントローラーを複数の初期条件で実行してデータを収集します")

    wizard_state = st.session_state.get("model_creation_wizard", {})
    if not wizard_state.get("step1_complete"):
        st.info("先にStep 1でモデルタイプを選択してください")
        return None

    # Check collection service health
    h_collection, _, err_collection = api_client.get_service_health("collection_orchestrator")
    h_simple, _, err_simple = api_client.get_service_health("simple_controller")
    
    if not (h_collection and h_simple):
        st.error("Collection / Simple Controller サービスが利用できません")
        st.caption(f"Collection: {err_collection if not h_collection else 'ok'}")
        st.caption(f"Simple Controller: {err_simple if not h_simple else 'ok'}")
        return None

    with st.form("data_collection_form"):
        st.markdown("#### 収集パラメータ")
        col1, col2 = st.columns(2)
        
        with col1:
            seeds_text = st.text_input(
                "ランダムシード (カンマ区切り)",
                value=wizard_state.get("seeds_text", "1,2,3,4,5"),
                key="collection_seeds_input",
            )
        with col2:
            max_workers = st.number_input(
                "並列ワーカー数",
                min_value=1,
                max_value=32,
                value=wizard_state.get("max_workers", 4),
                step=1,
                key="collection_max_workers",
            )

        st.markdown("#### 制御ループパラメータ")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            max_steps = st.number_input(
                "最大ステップ数",
                min_value=1,
                max_value=100,
                value=wizard_state.get("max_steps", 10),
                step=1,
                key="collection_max_steps",
            )
        with col2:
            tolerance = st.number_input(
                "許容値 (mm)",
                min_value=0.001,
                max_value=0.5,
                value=wizard_state.get("tolerance", 0.05),
                step=0.01,
                format="%.4f",
                key="collection_tolerance",
            )
        with col3:
            delta_clip = st.number_input(
                "Delta クリップ",
                min_value=0.01,
                max_value=0.5,
                value=wizard_state.get("delta_clip", 0.1),
                step=0.01,
                format="%.3f",
                key="collection_delta_clip",
            )

        st.markdown("#### 掃引範囲拡張 (オプション)")
        expand_enabled = st.checkbox(
            "掃引範囲を各ラウンド毎に拡張",
            value=wizard_state.get("expand_enabled", False),
            key="expand_enabled",
        )
        
        if expand_enabled:
            expand_ratio = st.number_input(
                "拡張率 (%)",
                min_value=1,
                max_value=100,
                value=wizard_state.get("expand_ratio", 20),
                step=5,
                key="expand_ratio",
            )
        else:
            expand_ratio = None

        step2_submit = st.form_submit_button("収集を開始", type="primary")

    if step2_submit:
        raw_seeds = [x.strip() for x in seeds_text.split(",") if x.strip()]
        try:
            seeds = [int(x) for x in raw_seeds]
        except ValueError:
            st.error("seedsは整数のカンマ区切りで指定してください")
            return None

        if not seeds:
            st.warning("1つ以上のseedを指定してください")
            return None

        # Create collection job
        job_payload = {
            "algorithm": "simple-controller",
            "controller_config": {
                "spot_to_coll_scale_x": 50.0,
                "spot_to_coll_scale_y": 50.0,
                "delta_clip_x": delta_clip,
                "delta_clip_y": delta_clip,
                "coll_x_min": -0.5,
                "coll_x_max": 0.5,
                "coll_y_min": -0.5,
                "coll_y_max": 0.5,
            },
            "target": {"spot_center_x": 0.0, "spot_center_y": 0.0},
            "initial_coll": {"coll_x": 0.0, "coll_y": 0.0},
            "max_steps": int(max_steps),
            "tolerance": float(tolerance),
            "tasks": [{"experiment_id": experiment_id, "seeds": seeds}],
            "max_workers": int(max_workers),
        }

        created = api_client.start_collection_job(job_payload)
        if created:
            wizard_state.update({
                "step2_complete": True,
                "collection_job_id": created.get("job_id"),
                "seeds_text": seeds_text,
                "max_workers": int(max_workers),
                "max_steps": int(max_steps),
                "tolerance": float(tolerance),
                "delta_clip": float(delta_clip),
                "expand_enabled": expand_enabled,
                "expand_ratio": expand_ratio,
            })
            st.session_state["model_creation_wizard"] = wizard_state
            st.success(f"データ収集ジョブを開始しました: {created.get('job_id')}")
            return wizard_state

    return None


def _render_step2_monitor(api_client: RecipeApiClient) -> None:
    """Monitor step 2 data collection progress"""
    wizard_state = st.session_state.get("model_creation_wizard", {})
    if not wizard_state.get("step2_complete"):
        return

    job_id = wizard_state.get("collection_job_id")
    if not job_id:
        return

    st.markdown("#### 収集進捗")
    detail = api_client.get_collection_job_status(job_id)
    if detail:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("ステータス", detail.get("status", "-"))
        with c2:
            st.metric("完了タスク", detail.get("completed_tasks", 0))
        with c3:
            st.metric("失敗タスク", detail.get("failed_tasks", 0))
        with c4:
            total = detail.get("total_tasks", 0)
            completed = detail.get("completed_tasks", 0)
            progress = (completed / total * 100) if total > 0 else 0
            st.metric("進捗率", f"{progress:.0f}%")

        if st.button("進捗を更新", key="refresh_collection_progress"):
            st.rerun()

        if detail.get("status") == "completed" or detail.get("completed_tasks", 0) > 0:
            if st.button("次へ: トレーニング →", type="primary", key="proceed_to_training"):
                st.success("トレーニングステップに進みます")
                st.rerun()

            with st.expander("収集結果の詳細"):
                st.json(detail)


def _render_step3_training(api_client: RecipeApiClient, experiment_id: str) -> None:
    """Step 3: Training and learning"""
    st.subheader("3️⃣ トレーニング")
    st.caption("収集したデータでモデルを学習します")

    wizard_state = st.session_state.get("model_creation_wizard", {})
    if not wizard_state.get("step2_complete"):
        st.info("先にStep 2でデータ収集を完了してください")
        return

    # Check trainer health
    health_ok, _, health_err = api_client.get_service_health("trainer")
    if not health_ok:
        st.error(f"Trainer Service に接続できません: {health_err}")
        return

    model_type = wizard_state.get("model_type", "mlp")
    model_name = wizard_state.get("model_name", "unknown")
    epochs = wizard_state.get("epochs", 50)
    batch_size = wizard_state.get("batch_size", 32)

    with st.form("training_start_form"):
        st.markdown(f"**モデル**: {model_name} ({model_type})")
        st.markdown(f"**トレーニング設定**: {epochs}エポック, バッチサイズ{batch_size}")

        learning_rate = st.number_input(
            "学習率",
            min_value=0.0001,
            max_value=0.1,
            value=0.001,
            format="%.5f",
            key="training_learning_rate",
        )

        submit_training = st.form_submit_button("トレーニング開始", type="primary")

    if submit_training:
        response = api_client.start_training(
            {
                "experiment_ids": [experiment_id],
                "model_type": model_type,
                "epochs": epochs,
                "batch_size": batch_size,
                "learning_rate": learning_rate,
            }
        )
        if response:
            wizard_state.update({
                "step3_complete": True,
                "training_result": response,
            })
            st.session_state["model_creation_wizard"] = wizard_state
            st.success("トレーニングを開始しました")
            st.session_state["current_model_version"] = model_name
            st.rerun()

    # Display training results
    training_result = wizard_state.get("training_result")
    if training_result:
        st.divider()
        st.markdown("#### トレーニング完了")

        # Training metrics
        train_metrics = training_result.get("train_metrics")
        if train_metrics:
            st.markdown("**学習進行**")
            epoch_losses = train_metrics.get("epoch_losses") or []
            final_loss = train_metrics.get("final_train_loss")
            epochs_trained = train_metrics.get("epochs")

            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("エポック数", f"{epochs_trained}" if epochs_trained is not None else "-")
            with c2:
                st.metric("最終ロス", f"{float(final_loss):.6f}" if final_loss is not None else "-")
            with c3:
                st.metric("ロスポイント数", len(epoch_losses))

            if epoch_losses:
                fig = go.Figure()
                fig.add_trace(
                    go.Scatter(
                        x=list(range(1, len(epoch_losses) + 1)),
                        y=epoch_losses,
                        mode="lines+markers",
                        name="train_loss",
                        line=dict(color="#1f77b4", width=2),
                    )
                )
                fig.update_layout(
                    title="学習損失推移",
                    xaxis_title="Epoch",
                    yaxis_title="Loss",
                    height=300,
                    margin=dict(l=20, r=20, t=40, b=20),
                )
                st.plotly_chart(fig, use_container_width=True)

        # Benchmark results
        benchmark_results = training_result.get("benchmark_results")
        if benchmark_results:
            st.markdown("**ベンチマーク結果**")
            new_model = benchmark_results.get("new_model") or {}
            current_model = benchmark_results.get("current_model") or {}

            rows = [
                {
                    "指標": "中央値エラー (mm)",
                    "新モデル": f"{new_model.get('median_final_error_mm', 0.0):.4f}",
                    "現在のモデル": f"{current_model.get('median_final_error_mm', 0.0):.4f}",
                },
                {
                    "指標": "95パーセンタイルエラー (mm)",
                    "新モデル": f"{new_model.get('p95_final_error_mm', 0.0):.4f}",
                    "現在のモデル": f"{current_model.get('p95_final_error_mm', 0.0):.4f}",
                },
                {
                    "指標": "収束率",
                    "新モデル": f"{new_model.get('converge_rate', 0.0):.2%}",
                    "現在のモデル": f"{current_model.get('converge_rate', 0.0):.2%}",
                },
            ]
            st.dataframe(rows, width="stretch", hide_index=True, use_container_width=True)

            fig = go.Figure()
            labels = ["median_error_mm", "p95_error_mm", "converge_rate"]
            fig.add_trace(
                go.Bar(
                    name="新モデル",
                    x=labels,
                    y=[
                        new_model.get("median_final_error_mm", 0.0),
                        new_model.get("p95_final_error_mm", 0.0),
                        new_model.get("converge_rate", 0.0),
                    ],
                    marker_color="#2ca02c",
                )
            )
            fig.add_trace(
                go.Bar(
                    name="現在のモデル",
                    x=labels,
                    y=[
                        current_model.get("median_final_error_mm", 0.0),
                        current_model.get("p95_final_error_mm", 0.0),
                        current_model.get("converge_rate", 0.0),
                    ],
                    marker_color="#ff7f0e",
                )
            )
            fig.update_layout(
                barmode="group",
                title="ベンチマーク比較",
                height=320,
                margin=dict(l=20, r=20, t=40, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)

            st.success("✅ モデルの学習が完了しました")
            if st.button("次へ: 結果比較 →", key="finish_wizard"):
                st.info("結果比較画面に進んでください")


def render(api_client: RecipeApiClient) -> None:
    """Main render function for model creation wizard"""
    st.header("3️⃣ モデル学習")
    st.caption("3段階のウィザードでモデルを学習します")

    experiment_id = _select_experiment(api_client)
    if experiment_id is None:
        st.info("最初に実験を作成してください")
        return

    # Update global context
    st.session_state["selected_experiment_id"] = experiment_id

    # Progress indicator
    wizard_state = st.session_state.get("model_creation_wizard", {})
    step1_done = wizard_state.get("step1_complete", False)
    step2_done = wizard_state.get("step2_complete", False)
    step3_done = wizard_state.get("step3_complete", False)

    progress_text = f"進捗: Step1 {'✅' if step1_done else '⏳'} → Step2 {'✅' if step2_done else '⏳'} → Step3 {'✅' if step3_done else '⏳'}"
    st.caption(progress_text)
    st.divider()

    # Step 1: Model selection
    step1_result = _render_step1_model_selection(api_client)
    if step1_result is None:
        return

    st.divider()

    # Step 2: Data collection
    if step1_done:
        step2_result = _render_step2_data_collection(api_client, experiment_id)
        if step2_result is None and not step2_done:
            return

        if step2_done:
            _render_step2_monitor(api_client)
            st.divider()

            # Step 3: Training
            if step2_done:
                _render_step3_training(api_client, experiment_id)
