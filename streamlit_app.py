"""Indicator Dashboard — Streamlit Community Cloud 入口。

React SPA 部署在 GitHub Pages（Streamlit 静态目录对 .html/.js 常以 text/plain
返回，浏览器会拒绝执行脚本，导致一直转圈/白屏）。
"""

from __future__ import annotations

import streamlit as st

# 与 vite.config.ts 的 base、仓库名保持一致
PAGES_URL = "https://onegee.github.io/indicator-dashboard/"

st.set_page_config(
    page_title="全球大类资产配置数据台",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("全球大类资产配置数据台")
st.write(
    "前端看板托管在 GitHub Pages。"
    "Streamlit Community Cloud 的静态文件服务不适合直接跑 Vite SPA，"
    "因此这里提供跳转入口。"
)

st.link_button("打开数据台", PAGES_URL, type="primary", use_container_width=True)
st.caption(f"直达链接：{PAGES_URL}")

st.info(
    "若 GitHub Pages 尚未启用：仓库 Settings → Pages → Source 选 "
    "GitHub Actions，等待首次 workflow 成功后再打开。"
)
