"""Indicator Dashboard — Streamlit Community Cloud 入口。

前端为 Vite 构建的 React SPA，静态文件由 Streamlit 托管于 /app/static/。
本地构建：cd web && npm ci && npm run build
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

STATIC_INDEX = Path(__file__).resolve().parent / "static" / "index.html"

st.set_page_config(
    page_title="全球大类资产配置数据台",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    header[data-testid="stHeader"] { background: transparent; }
    .block-container {
        padding-top: 0.25rem;
        padding-bottom: 0;
        max-width: 100%;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if not STATIC_INDEX.is_file():
    st.error("未找到 static/index.html。请先构建前端：cd web && npm ci && npm run build")
    st.stop()

st.iframe("/app/static/index.html", height=980, scrolling=True)
