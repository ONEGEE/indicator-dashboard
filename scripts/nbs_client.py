#!/usr/bin/env python3
"""国家统计局新 SPA 接口客户端（需 Playwright 过 WAF）。

参考：data.stats.gov.cn/dg/website/publicrelease/web/external/
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import pandas as pd

API_BASE = "https://data.stats.gov.cn/dg/website/publicrelease/web/external"
ROOT_MONTHLY = "fc982599aa684be7969d7b90b1bd0e84"

# 商品住宅销售：累计面积 / 累计销售额
NBS_CN_HOUSING = {
    "area_ytd": {
        "cid": "e9bb62c29eaa49f0b6e88548fc3924aa",
        "indicator_id": "d324a9c4f1a34dd2b38a85e979a54554",
        "name": "商品住宅销售面积累计值",
        "unit": "万平方米",
    },
    "sales_ytd": {
        "cid": "9756d668012e4c96807ef1ea1749319c",
        "indicator_id": "375ffa7283dd458c9a3bcb1f4929537e",
        "name": "商品住宅销售额累计值",
        "unit": "亿元",
    },
}


def _parse_series(payload: dict[str, Any]) -> pd.Series:
    records: dict[pd.Timestamp, float] = {}
    for block in payload.get("data") or []:
        code = block.get("code", "")
        date_str = re.sub(r"[A-Za-z]+$", "", code)
        if len(date_str) < 6:
            continue
        dt = pd.Timestamp(year=int(date_str[:4]), month=int(date_str[4:6]), day=1)
        for val_entry in block.get("values") or []:
            raw = val_entry.get("value")
            if raw not in (None, ""):
                records[dt] = float(raw)
    return pd.Series(records, dtype="float64").sort_index()


async def _fetch_one_async(cid: str, indicator_id: str, dts: str) -> pd.Series:
    from playwright.async_api import async_playwright

    body = {
        "cid": cid,
        "indicatorIds": [indicator_id],
        "daCatalogId": "",
        "das": [{"text": "全国", "value": "000000000000"}],
        "showType": "1",
        "dts": [dts],
        "rootId": ROOT_MONTHLY,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(
            "https://data.stats.gov.cn/dg/website/page.html#/pc/national/monthData",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        await page.wait_for_timeout(4000)
        payload = await page.evaluate(
            """async ({url, body}) => {
                const resp = await fetch(url, {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Accept': 'application/json',
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(body)
                });
                return await resp.json();
            }""",
            {"url": f"{API_BASE}/stream/esData", "body": body},
        )
        await browser.close()

    if not isinstance(payload, dict) or payload.get("state") != 20000:
        raise RuntimeError(f"NBS 拉取失败: {payload}")
    series = _parse_series(payload)
    if series.empty:
        raise RuntimeError(f"NBS 无数据: cid={cid} indicator={indicator_id}")
    return series


def fetch_nbs_monthly(cid: str, indicator_id: str, dts: str = "200001MM-203012MM") -> pd.Series:
    return asyncio.run(_fetch_one_async(cid, indicator_id, dts))


async def _fetch_housing_pair_async(dts: str) -> tuple[pd.Series, pd.Series]:
    """同一次浏览器会话拉取面积 + 销售额。"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(
            "https://data.stats.gov.cn/dg/website/page.html#/pc/national/monthData",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        await page.wait_for_timeout(4000)

        async def one(key: str) -> pd.Series:
            cfg = NBS_CN_HOUSING[key]
            body = {
                "cid": cfg["cid"],
                "indicatorIds": [cfg["indicator_id"]],
                "daCatalogId": "",
                "das": [{"text": "全国", "value": "000000000000"}],
                "showType": "1",
                "dts": [dts],
                "rootId": ROOT_MONTHLY,
            }
            payload = await page.evaluate(
                """async ({url, body}) => {
                    const resp = await fetch(url, {
                        method: 'POST',
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json',
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(body)
                    });
                    return await resp.json();
                }""",
                {"url": f"{API_BASE}/stream/esData", "body": body},
            )
            if not isinstance(payload, dict) or payload.get("state") != 20000:
                raise RuntimeError(f"NBS {key} 失败: {payload}")
            return _parse_series(payload)

        area = await one("area_ytd")
        sales = await one("sales_ytd")
        await browser.close()
    return area, sales


def fetch_cn_residential_sales_ytd(
    dts: str = "200001MM-203012MM",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (面积累计, 销售额累计) 两个 DataFrame：date, value。"""
    area, sales = asyncio.run(_fetch_housing_pair_async(dts))
    area_df = pd.DataFrame({"date": area.index, "value": area.values})
    sales_df = pd.DataFrame({"date": sales.index, "value": sales.values})
    return area_df, sales_df
