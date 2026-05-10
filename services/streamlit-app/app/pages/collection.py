from __future__ import annotations

from typing import Any

import streamlit as st

from app.api_client import RecipeApiClient


def render(api_client: RecipeApiClient) -> None:
    st.header("📊 データ収集")
    st.warning("🚧 この機能はまだ実装中です (stub)")
    
    st.info(
        "DNNトレーニング用のデータ収集ジョブを管理します。\n\n"
        "このページでは以下の機能が実装予定です:\n"
        "- 収集ジョブの作成\n"
        "- ジョブの進行状況監視\n"
        "- 収集されたデータの統計\n"
        "- トレーニングデータセット管理"
    )
    
    st.divider()
    st.subheader("機能予定")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **ジョブ管理**
        - 新規収集ジョブの作成
        - 既存ジョブの一覧表示
        - ジョブステータス追跡
        - ジョブのキャンセル機能
        """)
    
    with col2:
        st.markdown("""
        **データ統計**
        - 収集されたステップ数
        - パラメータ範囲情報
        - エラー率の監視
        - 品質チェック機能
        """)
    
    st.divider()
    st.subheader("ジョブ一覧")
    
    # Stub: Show empty state
    try:
        jobs = api_client.get_collection_jobs()
        if jobs:
            st.dataframe(jobs, width="stretch", hide_index=True)
        else:
            st.info("実行中のジョブはありません")
    except Exception as e:
        st.error(f"ジョブ一覧の取得に失敗しました: {e}")
