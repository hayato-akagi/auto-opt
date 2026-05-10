from __future__ import annotations

from typing import Any

import streamlit as st

from app.api_client import RecipeApiClient


def render(api_client: RecipeApiClient) -> None:
    st.header("🏪 モデルストア")
    st.warning("🚧 この機能はまだ実装中です (stub)")
    
    st.info(
        "学習済みDNNモデルを管理・プロモートします。\n\n"
        "このページでは以下の機能が実装予定です:\n"
        "- モデルバージョン一覧\n"
        "- ベンチマーク結果の確認\n"
        "- モデルのプロモーション（本番環境への昇格）\n"
        "- バージョン比較"
    )
    
    st.divider()
    st.subheader("機能予定")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **モデル管理**
        - モデルバージョン一覧表示
        - ベンチマーク詳細の表示
        - メタデータ確認
        - ダウンロード機能
        """)
    
    with col2:
        st.markdown("""
        **プロモーション**
        - ステージング環境へのプロモート
        - 本番環境へのプロモート
        - ロールバック機能
        - プロモート履歴
        """)
    
    st.divider()
    st.subheader("モデルバージョン")
    
    # Stub: Show empty state
    try:
        models = api_client.get_models()
        if models:
            st.dataframe(models, width="stretch", hide_index=True)
            
            # Model detail selection stub
            model_version = st.selectbox(
                "詳細確認するモデルを選択",
                [str(m.get("version", "?")) for m in models]
            )
            if model_version:
                model_detail = api_client.get_model(model_version)
                if model_detail:
                    st.json(model_detail)
        else:
            st.info("モデルはまだ登録されていません")
    except Exception as e:
        st.error(f"モデル一覧の取得に失敗しました: {e}")
