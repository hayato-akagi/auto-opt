from __future__ import annotations

from typing import Any

import streamlit as st

from app.api_client import RecipeApiClient


def render(api_client: RecipeApiClient) -> None:
    st.header("🧠 トレーニング")
    st.warning("🚧 この機能はまだ実装中です (stub)")
    
    st.info(
        "DNN モデルのトレーニングを管理します。\n\n"
        "このページでは以下の機能が実装予定です:\n"
        "- トレーニングジョブの開始\n"
        "- 実行中のジョブの監視\n"
        "- 学習曲線（loss, metrics）の可視化\n"
        "- ジョブ結果の確認"
    )
    
    st.divider()
    st.subheader("機能予定")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **トレーニング設定**
        - トレーニングデータセット選択
        - ハイパーパラメータ設定
        - バリデーション設定
        - チェックポイント保存設定
        """)
    
    with col2:
        st.markdown("""
        **監視・可視化**
        - リアルタイム学習曲線
        - バリデーション精度
        - ベンチマーク結果
        - ジョブログビューア
        """)
    
    st.divider()
    st.subheader("トレーニングジョブ")
    
    # Stub: Show empty state
    try:
        jobs = api_client.get_training_jobs()
        if jobs:
            st.dataframe(jobs, width="stretch", hide_index=True)
            
            # Job detail selection stub
            job_id = st.selectbox("詳細確認するジョブを選択", [str(j.get("job_id", "?")) for j in jobs])
            if job_id:
                job_detail = api_client.get_training_job_status(job_id)
                if job_detail:
                    st.json(job_detail)
        else:
            st.info("トレーニングジョブはまだ実行されていません")
    except Exception as e:
        st.error(f"ジョブ一覧の取得に失敗しました: {e}")
