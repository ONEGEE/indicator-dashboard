"""Indicator Dashboard — Streamlit Community Cloud 入口。

前端为 Vite 构建的 React SPA，静态文件由 Streamlit 托管于 /app/static/。
本地构建：cd web && npm ci && npm run build
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

STATIC_INDEX = Path(__file__).resolve().parent / "static" / "index.html"
# Streamlit 静态资源路径（相对应用根）。勿用 st.iframe(..., scrolling=...)，新 API 不支持。
STATIC_URL = "/app/static/index.html"

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
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .block-container {
        padding-top: 1rem;
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

st.markdown(
    f"""
### 全球大类资产配置数据台

若下方一直转圈，请直接打开静态页面：[{STATIC_URL}]({STATIC_URL})
"""
)

# 用 components.html 跳转到顶层（突破 Streamlit 壳），并保留可点击链接
components.html(
    f"""
    <div style="font-family: system-ui, sans-serif; padding: 4px 0;">
      <a href="{STATIC_URL}" target="_top"
         style="display:inline-block;padding:10px 16px;background:#0f5c4c;color:#fff;
                text-decoration:none;border-radius:8px;font-weight:600;">
        进入数据台
      </a>
    </div>
    <script>
      // 自动跳到完整 SPA（避免卡在 Streamlit 壳的 iframe 里）
      try {{ window.top.location.replace("{STATIC_URL}"); }} catch (e) {{}}
    </script>
    """,
    height=64,
)
