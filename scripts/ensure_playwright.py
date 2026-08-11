#!/usr/bin/env python3
"""确保 Playwright Chromium 已安装（国家统计局 cn_housing 需要）。"""

from __future__ import annotations

import subprocess
import sys


def chromium_ready() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception as exc:
        msg = str(exc)
        return not (
            "Executable doesn't exist" in msg
            or "playwright install" in msg
            or "chrome-headless-shell" in msg
        )


def ensure_chromium() -> None:
    if chromium_ready():
        print("✓ Playwright Chromium 可用")
        return
    print("正在安装 Playwright Chromium（仅首次或浏览器缺失时需要）…")
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
    )
    if not chromium_ready():
        raise RuntimeError("Playwright Chromium 安装后仍无法启动")
    print("✓ Playwright Chromium 安装完成")


if __name__ == "__main__":
    ensure_chromium()
