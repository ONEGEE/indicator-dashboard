#!/usr/bin/env python3
"""拉取全球资产轮动：月度回报 + 市值/存量，含交叉验证。

配置：data/manifest_rotation.json

用法：
  python scripts/fetch_rotation.py
  python scripts/fetch_rotation.py --validate-only
  python scripts/fetch_rotation.py --id us_equity btc
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.data_lib import (  # noqa: E402
    DATA_DIR,
    finalize_marketcap,
    finalize_simple,
    last_complete_month_start,
    project_marketcap_with_return,
    save_marketcap,
    save_simple,
    scale_annual_to_monthly,
    scale_from_anchor,
    to_monthly_last,
)

MANIFEST_PATH = DATA_DIR / "manifest_rotation.json"
COMPONENT_DIR = DATA_DIR / "csv/rotation/marketcap/_components"
VALIDATE_DIR = DATA_DIR / "csv/validate"
UA = {"User-Agent": "Mozilla/5.0 (compatible; databoard-rotation/1.0)"}

TROY_OZ_PER_TONNE = 32150.7466


def load_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def get_fred():
    load_dotenv(ROOT / ".env")
    key = os.getenv("FRED_API_KEY")
    if not key or key.startswith("your_"):
        raise RuntimeError("请在 .env 中设置 FRED_API_KEY")
    from fredapi import Fred

    return Fred(api_key=key)


def fetch_yfinance_monthly(symbol: str, start: str = "1990-01-01") -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    raw = ticker.history(start=start, auto_adjust=True)
    if raw.empty:
        raise RuntimeError(f"yfinance 无数据: {symbol}")
    close = raw["Close"] if "Close" in raw.columns else raw.iloc[:, 0]
    monthly = to_monthly_last(close)
    return finalize_simple(
        pd.DataFrame({"date": monthly.index, "value": monthly.values})
    )


def fetch_fred_monthly(series_id: str) -> pd.DataFrame:
    fred = get_fred()
    s = fred.get_series(series_id).dropna()
    if s.empty:
        raise RuntimeError(f"FRED 无数据: {series_id}")
    monthly = to_monthly_last(s)
    return finalize_simple(
        pd.DataFrame({"date": monthly.index, "value": monthly.values})
    )


def fetch_worldbank_annual(country: str, indicator: str) -> pd.DataFrame:
    url = (
        "https://api.worldbank.org/v2/country/"
        f"{country}/indicator/{indicator}"
        "?format=json&per_page=500&date=1960:2030"
    )
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode())
    rows = payload[1] if len(payload) > 1 and payload[1] else []
    records = []
    for row in rows:
        if row.get("value") is None:
            continue
        records.append(
            {
                "date": f"{int(row['date'])}-12-31",
                "value": float(row["value"]),
            }
        )
    if not records:
        raise RuntimeError(f"World Bank 无数据: {country}/{indicator}")
    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)


def fetch_worldbank_sum_annual(countries: list[str], indicator: str) -> pd.DataFrame:
    frames = []
    for c in countries:
        try:
            frames.append(fetch_worldbank_annual(c, indicator))
        except Exception as exc:
            print(f"  警告: WB {c} 跳过: {exc}", file=sys.stderr)
    if not frames:
        raise RuntimeError(f"World Bank 汇总失败: {countries}")
    merged = frames[0].rename(columns={"value": "v0"})
    for i, df in enumerate(frames[1:], start=1):
        merged = merged.merge(
            df.rename(columns={"value": f"v{i}"}),
            on="date",
            how="outer",
        )
    val_cols = [c for c in merged.columns if c.startswith("v")]
    merged["value"] = merged[val_cols].sum(axis=1, skipna=True)
    return merged[["date", "value"]].dropna().sort_values("date").reset_index(drop=True)


def fetch_blockchain_btc_mcap() -> pd.DataFrame:
    url = "https://api.blockchain.info/charts/market-cap?timespan=all&format=json"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode())
    values = payload.get("values") or []
    if not values:
        raise RuntimeError("Blockchain.com 无 BTC 市值")
    df = pd.DataFrame(values)
    df["date"] = pd.to_datetime(df["x"], unit="s")
    df["value_usd"] = pd.to_numeric(df["y"], errors="coerce")
    monthly = df.set_index("date")["value_usd"].resample("MS").last().dropna()
    out = monthly.reset_index()
    out.columns = ["date", "value_usd"]
    return finalize_marketcap(out)


def fetch_akshare_index_monthly(symbol: str) -> pd.DataFrame:
    import akshare as ak

    try:
        raw = ak.index_zh_a_hist(symbol=symbol, period="monthly")
        out = pd.DataFrame(
            {
                "date": pd.to_datetime(raw["日期"]),
                "value": pd.to_numeric(raw["收盘"], errors="coerce"),
            }
        )
        return finalize_simple(out)
    except Exception:
        # AkShare 不稳定时回退 yfinance 或本地已拉指数
        local = DATA_DIR / "csv/cn_csi300.csv"
        if symbol == "000300" and local.exists():
            df = pd.read_csv(local)
            df["date"] = pd.to_datetime(df["date"])
            monthly = df.set_index("date")["close"].resample("MS").last().dropna()
            return finalize_simple(
                pd.DataFrame({"date": monthly.index, "value": monthly.values})
            )
        return fetch_yfinance_monthly("000300.SS")


def fetch_owid_world_oil_mbpd() -> pd.DataFrame:
    """Our World in Data 全球石油消费（年→月）：TWh → 百万桶/日。"""
    url = "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = pd.read_csv(resp)
    world = raw[raw["country"] == "World"][["year", "oil_consumption"]].dropna()
    world["oil_consumption"] = pd.to_numeric(world["oil_consumption"], errors="coerce")
    world = world.dropna()
    # OWID oil_consumption 单位为 TWh；约 1.7 MWh/桶 = 1.7e-6 TWh/桶
    twh_per_bbl = 1.7e-6
    world["mbpd"] = (world["oil_consumption"] / twh_per_bbl) / 365.0 / 1_000_000.0
    # 年值放在 12 月，再前向填充到月度
    annual = pd.DataFrame(
        {
            "date": pd.to_datetime(world["year"].astype(int).astype(str) + "-12-01"),
            "value": world["mbpd"].values,
        }
    ).sort_values("date")
    if annual.empty:
        raise RuntimeError("OWID 全球石油消费为空")
    start = annual["date"].iloc[0].replace(month=1, day=1)
    end = pd.Timestamp.today().normalize().replace(day=1)
    idx = pd.date_range(start, end, freq="MS")
    s = annual.set_index("date")["value"].reindex(idx).ffill().bfill()
    return pd.DataFrame({"date": s.index, "value": s.values})


def fetch_eia_steo_monthly(series_id: str, length: int = 5000) -> pd.DataFrame:
    """EIA STEO 月度序列（百万桶/日等）。优先 EIA_API_KEY，否则 DEMO_KEY；含重试与本地缓存回退。"""
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("EIA_API_KEY") or "DEMO_KEY"
    cache_path = COMPONENT_DIR / f"eia_steo_{series_id.lower()}.csv"
    url = "https://api.eia.gov/v2/steo/data/"
    params = [
        ("api_key", api_key),
        ("frequency", "monthly"),
        ("data[0]", "value"),
        ("facets[seriesId][]", series_id),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "asc"),
        ("length", str(length)),
    ]
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url + "?" + urllib.parse.urlencode(params),
                headers={**UA, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode())
            if "error" in payload:
                raise RuntimeError(str(payload["error"]))
            rows = (payload.get("response") or {}).get("data") or []
            if not rows:
                raise RuntimeError("empty")
            records = []
            today = pd.Timestamp.today().normalize()
            for row in rows:
                period = row.get("period")
                val = row.get("value")
                if period is None or val in (None, ""):
                    continue
                dt = (
                    pd.Timestamp(str(period) + "-01")
                    if len(str(period)) == 7
                    else pd.Timestamp(period)
                )
                if dt > today:
                    continue
                records.append({"date": dt, "value": float(val)})
            out = pd.DataFrame(records).drop_duplicates("date").sort_values("date")
            if out.empty:
                raise RuntimeError("filtered empty")
            COMPONENT_DIR.mkdir(parents=True, exist_ok=True)
            out.assign(date=lambda d: pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")).to_csv(
                cache_path, index=False, float_format="%.6f"
            )
            return out
        except Exception as exc:
            last_err = exc
            time.sleep(3 * (attempt + 1))

    if cache_path.exists():
        cached = pd.read_csv(cache_path)
        cached["date"] = pd.to_datetime(cached["date"])
        cached["value"] = pd.to_numeric(cached["value"], errors="coerce")
        cached = cached.dropna().sort_values("date")
        if not cached.empty:
            print(f"  警告: EIA {series_id} 拉取失败，使用本地缓存 {cache_path.name}")
            return cached[["date", "value"]]

    # 最终回退：OWID 年消费量月度化
    if series_id.upper() == "PATC_WORLD":
        print("  警告: EIA 不可用，回退 OWID 全球石油消费（年→月）")
        return fetch_owid_world_oil_mbpd()

    raise RuntimeError(f"EIA STEO {series_id} 拉取失败: {last_err}")


def fetch_oil_trade_usd_monthly(mc: dict[str, Any]) -> pd.DataFrame:
    """原油月度美元交易额代理 = 全球液体燃料消费量 × 天数 × (WTI/Brent 加权均价)。

    保留原始分量：消费量(百万桶/日)、WTI、Brent、加权价、月交易额。
    """
    cons_id = mc.get("eia_consumption_series", "PATC_WORLD")
    wti_w = float(mc.get("wti_weight", 0.5))
    brent_w = float(mc.get("brent_weight", 0.5))
    w_sum = wti_w + brent_w
    if w_sum <= 0:
        raise RuntimeError("oil_trade_usd：权重之和须 > 0")
    wti_w, brent_w = wti_w / w_sum, brent_w / w_sum

    cons = fetch_eia_steo_monthly(cons_id)  # million barrels per day
    fred = get_fred()
    wti = fred.get_series("MCOILWTICO").dropna()
    brent = fred.get_series("MCOILBRENTEU").dropna()
    wti = to_monthly_last(wti)
    brent = to_monthly_last(brent)

    cons = cons.set_index("date")["value"]
    aligned = pd.concat(
        [cons, wti, brent],
        axis=1,
        keys=["mbpd", "wti", "brent"],
    ).dropna()
    if aligned.empty:
        raise RuntimeError("oil_trade_usd：消费量与油价对齐后为空")

    aligned["price"] = aligned["wti"] * wti_w + aligned["brent"] * brent_w
    days = aligned.index.to_series().dt.days_in_month.astype(float)
    aligned["barrels"] = aligned["mbpd"] * 1_000_000.0 * days.values
    aligned["value_usd"] = aligned["barrels"] * aligned["price"]

    COMPONENT_DIR.mkdir(parents=True, exist_ok=True)
    detail = pd.DataFrame(
        {
            "date": aligned.index.strftime("%Y-%m-%d"),
            "consumption_mbpd": aligned["mbpd"].values,
            "wti_usd_bbl": aligned["wti"].values,
            "brent_usd_bbl": aligned["brent"].values,
            "weighted_price_usd_bbl": aligned["price"].values,
            "days_in_month": days.values,
            "barrels": aligned["barrels"].values,
            "value_usd": aligned["value_usd"].values,
        }
    )
    detail.to_csv(COMPONENT_DIR / "oil_trade_usd_detail.csv", index=False, float_format="%.4f")
    cons.reset_index().rename(columns={"value": "mbpd"}).assign(
        date=lambda d: pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
    ).to_csv(COMPONENT_DIR / "oil_eia_patc_world.csv", index=False, float_format="%.6f")

    out = pd.DataFrame({"date": aligned.index, "value_usd": aligned["value_usd"].values})
    return finalize_marketcap(out)


def fetch_akshare_house_index() -> pd.DataFrame:
    """70城新建商品住宅价格指数：用环比（上年同月=100口径下的环比指数）链式合成水平指数。

    NBS/东财环比字段为定基指数形式，例如 101.1 = 较上月 +1.1%，故乘以 mom/100。
    """
    import akshare as ak

    raw = ak.macro_china_new_house_price()
    raw["date"] = pd.to_datetime(raw["日期"])
    raw["mom"] = pd.to_numeric(raw["新建商品住宅价格指数-环比"], errors="coerce")
    avg = raw.groupby("date", as_index=False)["mom"].mean().sort_values("date")
    level = [100.0]
    dates = [avg["date"].iloc[0]]
    for i in range(1, len(avg)):
        mom = avg["mom"].iloc[i]
        if pd.isna(mom) or mom <= 0:
            level.append(level[-1])
        else:
            level.append(level[-1] * float(mom) / 100.0)
        dates.append(avg["date"].iloc[i])
    out = pd.DataFrame({"date": dates, "value": level})
    return finalize_simple(out)


def fetch_usdcny_monthly() -> pd.Series:
    """CNY per USD（月度），用于人民币市值换算美元。"""
    try:
        fred = get_fred()
        s = fred.get_series("DEXCHUS").dropna()
        if not s.empty:
            return to_monthly_last(s)
    except Exception:
        pass
    fx = fetch_yfinance_monthly("CNY=X")
    fx["date"] = pd.to_datetime(fx["date"])
    return fx.set_index("date")["value"].astype(float)


def ytd_to_monthly_flow(ytd: pd.Series) -> pd.Series:
    """年初累计值 → 当月发生额。NBS 常缺 1 月，2 月读数为 1–2 月合计。"""
    ytd = ytd.dropna().sort_index()
    rows: list[tuple[pd.Timestamp, float]] = []
    for year, g in ytd.groupby(ytd.index.year):
        g = g.sort_index()
        prev = 0.0
        for dt, val in g.items():
            flow = float(val) - prev
            if flow < 0:
                flow = float(val) if dt.month <= 2 else 0.0
            rows.append((dt, flow))
            prev = float(val)
    return pd.Series({d: v for d, v in rows}).sort_index()


def fetch_cn_housing_zero_dep_marketcap(mc: dict[str, Any]) -> pd.DataFrame:
    """中信建投口径「零折旧市场法」：

    存量面积（商品住宅累计销售面积，不折旧）× 当期销售均价，
    并用报告 2024 年末约 395.6 万亿元人民币作水平锚点，校准样本起点前的存量基数。
    结果换算为美元。
    """
    from scripts.nbs_client import fetch_cn_residential_sales_ytd

    area_df, sales_df = fetch_cn_residential_sales_ytd()
    COMPONENT_DIR.mkdir(parents=True, exist_ok=True)
    area_df.to_csv(COMPONENT_DIR / "cn_housing_area_ytd.csv", index=False, float_format="%.4f")
    sales_df.to_csv(COMPONENT_DIR / "cn_housing_sales_ytd.csv", index=False, float_format="%.4f")

    area = area_df.set_index(pd.to_datetime(area_df["date"]))["value"].astype(float)
    sales = sales_df.set_index(pd.to_datetime(sales_df["date"]))["value"].astype(float)
    merged = pd.concat([area, sales], axis=1, keys=["area_ytd", "sales_ytd"]).dropna()
    if merged.empty:
        raise RuntimeError("cn_housing_zero_dep：面积/销售额对齐后为空")

    flow = ytd_to_monthly_flow(merged["area_ytd"])
    stock_commodity = flow.cumsum()  # 万平方米（样本期内累计）
    price = (merged["sales_ytd"] / merged["area_ytd"]) * 10000.0  # 元/平方米
    common = stock_commodity.index.intersection(price.index)
    flow = flow.reindex(common)
    stock_commodity = stock_commodity.loc[common]
    price = price.loc[common]

    # 锚点：2024-12 中国居民住宅总资产 ≈ 395.6 万亿元（中信建投零折旧市场法）
    anchor_year = int(mc.get("anchor_year", 2024))
    anchor_month = int(mc.get("anchor_month", 12))
    anchor_cny = float(mc.get("anchor_value_cny", 395.6e12))
    anchor_dt = pd.Timestamp(year=anchor_year, month=anchor_month, day=1)
    if anchor_dt not in stock_commodity.index:
        year_idx = stock_commodity.index[stock_commodity.index.year == anchor_year]
        if year_idx.empty:
            raise RuntimeError(f"cn_housing_zero_dep：缺少锚点年 {anchor_year} 数据")
        anchor_dt = year_idx[-1]

    # value = (initial + stock) * 10000 * price  → 元
    p_a = float(price.loc[anchor_dt])
    s_a = float(stock_commodity.loc[anchor_dt])
    if p_a <= 0:
        raise RuntimeError("cn_housing_zero_dep：锚点月均价无效")
    initial = anchor_cny / (p_a * 10000.0) - s_a
    if initial < 0:
        initial = 0.0

    stock = initial + stock_commodity
    value_cny = stock * 10000.0 * price

    fx = fetch_usdcny_monthly()  # CNY per USD
    aligned = pd.concat([value_cny, fx], axis=1, keys=["value_cny", "usdcny"]).dropna()
    if aligned.empty:
        raise RuntimeError("cn_housing_zero_dep：与汇率对齐后为空")
    value_usd = aligned["value_cny"] / aligned["usdcny"]

    # NBS 不单列 1 月（1–2 月合并发布），存量缺 1 月会令占比池突然少掉中国住房、
    # 其余资产占比虚高。对完整月度日历前向填充，用上月存量承接 1 月。
    full_idx = pd.date_range(value_usd.index.min(), value_usd.index.max(), freq="MS")
    value_usd = value_usd.reindex(full_idx).ffill()

    detail = pd.DataFrame(
        {
            "date": stock.index.strftime("%Y-%m-%d"),
            "area_flow_wan_sqm": flow.values,
            "stock_commodity_wan_sqm": stock_commodity.values,
            "initial_stock_wan_sqm": initial,
            "stock_total_wan_sqm": stock.values,
            "price_cny_per_sqm": price.values,
            "value_cny": value_cny.values,
        }
    )
    detail.to_csv(COMPONENT_DIR / "cn_housing_zero_dep_detail.csv", index=False, float_format="%.4f")

    out = pd.DataFrame({"date": value_usd.index, "value_usd": value_usd.values})
    return finalize_marketcap(out)


def fetch_yield_csv_price_proxy(rel_path: str, duration_years: float) -> pd.DataFrame:
    """用收益率近似构造短债价格代理（指数型，不做真实定价）。

    逻辑：把年化收益率 y(%) 转为贴现因子，取 price_proxy = (1 + y)^(-duration)。
    """
    import pandas as pd

    df = pd.read_csv(DATA_DIR / rel_path)
    if df.empty or "date" not in df.columns:
        raise RuntimeError(f"yield csv 缺少 date 列: {rel_path}")
    value_col = None
    if "close" in df.columns:
        value_col = "close"
    elif "value" in df.columns:
        value_col = "value"
    else:
        raise RuntimeError(f"yield csv 缺少 close/value 列: {rel_path}")
    df["date"] = pd.to_datetime(df["date"])
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df.dropna(subset=["date", value_col]).sort_values("date")

    monthly_yield = df.set_index("date")[value_col].resample("MS").last().dropna()
    # y = percent -> fraction
    y = monthly_yield / 100.0
    # avoid negative / invalid 1+y
    base = (1.0 + y).where((1.0 + y) > 0)
    price_proxy = base.pow(-float(duration_years))
    out = pd.DataFrame({"date": price_proxy.index, "value": price_proxy.values})
    return finalize_simple(out)


def fetch_futures_notional_proxy_monthly(
    symbol: str,
    contract_multiplier: float,
    price_floor: float = 0.0,
    start: str = "1990-01-01",
) -> pd.DataFrame:
    """期货名义规模代理（用于月度跟踪，而非真实现货市值）。

    notional_usd(month) = sum(Volume_contracts) * contract_multiplier * last(Close_price)
    """
    ticker = yf.Ticker(symbol)
    raw = ticker.history(start=start, auto_adjust=False)
    if raw.empty:
        raise RuntimeError(f"yfinance 无数据: {symbol}")
    if "Volume" not in raw.columns or "Close" not in raw.columns:
        raise RuntimeError(f"期货数据缺少 Volume/Close: {symbol}")

    raw = raw.dropna(subset=["Volume", "Close"])
    monthly_vol = raw["Volume"].resample("MS").sum().dropna()
    monthly_price = raw["Close"].resample("MS").last().dropna()
    monthly_price = monthly_price.clip(lower=price_floor)

    aligned = pd.concat([monthly_price, monthly_vol], axis=1, keys=["price", "vol"]).dropna()
    if aligned.empty:
        raise RuntimeError(f"名义规模代理：无对齐月度数据: {symbol}")

    out = pd.DataFrame(
        {
            "date": aligned.index,
            "value_usd": aligned["price"].astype(float).values
            * aligned["vol"].astype(float).values
            * float(contract_multiplier),
        }
    )
    return finalize_marketcap(out)


def read_monthly_index_from_return_csv(rel: str) -> pd.DataFrame:
    return finalize_simple(pd.read_csv(DATA_DIR / rel))


def fetch_return_series(spec: dict[str, Any]) -> pd.DataFrame:
    src = spec["source"]
    symbol = spec.get("symbol")
    if src == "yfinance":
        return fetch_yfinance_monthly(symbol)
    if src == "fred":
        return fetch_fred_monthly(symbol)
    if src == "akshare_index":
        return fetch_akshare_index_monthly(symbol)
    if src == "akshare_house":
        return fetch_akshare_house_index()
    if src == "yield_csv":
        rel_path = spec["rel_path"]
        duration_years = float(spec.get("duration_years", 1.0))
        return fetch_yield_csv_price_proxy(rel_path, duration_years)
    raise ValueError(f"未知回报数据源: {src}")


def fetch_marketcap_series(
    asset: dict[str, Any],
    return_df: pd.DataFrame | None = None,
) -> pd.DataFrame | None:
    mc = asset.get("marketcap") or {}
    method = mc.get("method")
    if method in (None, "na"):
        return None

    asset_id = asset["id"]

    if method == "worldbank_scaled":
        wb = mc["worldbank"]
        annual = fetch_worldbank_annual(wb["country"], wb["indicator"])
        comp_path = COMPONENT_DIR / f"{asset_id}_wb_annual.csv"
        comp_path.parent.mkdir(parents=True, exist_ok=True)
        annual.to_csv(comp_path, index=False, float_format="%.2f")
        if return_df is not None and not return_df.empty:
            index_df = return_df.copy()
        else:
            index_df = fetch_yfinance_monthly(mc["scale_symbol"])
        return scale_annual_to_monthly(annual, index_df)

    if method == "worldbank_sum_scaled":
        annual = fetch_worldbank_sum_annual(
            mc["worldbank_countries"], "CM.MKT.LCAP.CD"
        )
        comp_path = COMPONENT_DIR / f"{asset_id}_wb_annual.csv"
        comp_path.parent.mkdir(parents=True, exist_ok=True)
        annual.to_csv(comp_path, index=False, float_format="%.2f")
        if return_df is not None and not return_df.empty:
            index_df = return_df.copy()
        else:
            index_df = fetch_yfinance_monthly(mc["scale_symbol"])
        return scale_annual_to_monthly(annual, index_df)

    if method == "fred_direct":
        fred = get_fred()
        s = fred.get_series(mc["fred"]).dropna()
        multiplier = float(mc.get("unit_multiplier", 1.0))
        s = s.astype(float) * multiplier
        s.index = pd.to_datetime(s.index)
        # 季度/年度序列：取月末观测并前向填充为月度
        monthly = s.resample("MS").last().ffill().dropna()
        comp_path = COMPONENT_DIR / f"{asset_id}_fred_raw.csv"
        comp_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            {"date": monthly.index.strftime("%Y-%m-%d"), "value": monthly.values}
        ).to_csv(comp_path, index=False, float_format="%.2f")
        out = pd.DataFrame({"date": monthly.index, "value_usd": monthly.values})
        out = finalize_marketcap(out)
        if mc.get("project_with_return") and return_df is not None and not return_df.empty:
            projected, extra = project_marketcap_with_return(out, return_df)
            if not extra.empty:
                comp_path = COMPONENT_DIR / f"{asset_id}_projected.csv"
                comp_path.parent.mkdir(parents=True, exist_ok=True)
                finalize_marketcap(extra).to_csv(comp_path, index=False, float_format="%.2f")
                out = finalize_marketcap(projected)
        return out

    if method == "fred_scaled":
        fred = get_fred()
        s = fred.get_series(mc["fred"]).dropna()
        annual = pd.DataFrame(
            {
                "date": s.resample("YS").last().index.strftime("%Y-12-31"),
                "value": s.resample("YS").last().values,
            }
        )
        index_df = fetch_yfinance_monthly(mc["scale_symbol"])
        out = scale_annual_to_monthly(annual, index_df)
        factor = mc.get("scale_factor", 1.0)
        if factor != 1.0:
            out["value_usd"] *= factor
        return out

    if method == "blockchain_info":
        return fetch_blockchain_btc_mcap()

    if method == "coingecko":
        return fetch_blockchain_btc_mcap()

    if method == "gold_stock_value":
        price_df = fetch_yfinance_monthly(mc["price_symbol"])
        tonnes = float(mc["tonnes"])
        oz = tonnes * TROY_OZ_PER_TONNE
        out = price_df.copy()
        out["value_usd"] = out["value"] * oz
        out = out[["date", "value_usd"]]
        # GLD 代理组件（验证用）
        try:
            gld = fetch_yfinance_monthly("GLD")
            gld_shares = 400_000_000  # 粗略代理
            proxy = gld.copy()
            proxy["value"] = proxy["value"] * gld_shares
            save_simple(proxy, "csv/rotation/marketcap/_components/gold_gld_proxy.csv")
        except Exception:
            pass
        return finalize_marketcap(out)

    if method == "scaled_from_return":
        rel = mc.get("scale_from_return_csv") or asset["return"]["csv"]
        if return_df is None:
            return_df = read_monthly_index_from_return_csv(rel)
        return scale_from_anchor(
            return_df,
            mc["anchor_date"],
            float(mc["anchor_value_usd"]),
        )

    if method == "worldbank_ratio_gdp_amount_scaled":
        ratio_cfg = mc["worldbank_ratio"]
        gdp_cfg = mc["worldbank_gdp"]
        ratio_annual = fetch_worldbank_annual(ratio_cfg["country"], ratio_cfg["indicator"])
        gdp_annual = fetch_worldbank_annual(gdp_cfg["country"], gdp_cfg["indicator"])

        ratio_annual = ratio_annual.rename(columns={"value": "ratio"})
        gdp_annual = gdp_annual.rename(columns={"value": "gdp"})
        merged = ratio_annual.merge(gdp_annual, on="date", how="inner").dropna()
        if merged.empty:
            raise RuntimeError("worldbank_ratio_gdp_amount_scaled：合并后为空")

        # heuristic: ratio indicator is usually percent (>2) or fraction (<=1)
        if float(merged["ratio"].max()) > 2.0:
            merged["amount"] = (merged["ratio"] / 100.0) * merged["gdp"]
        else:
            merged["amount"] = merged["ratio"] * merged["gdp"]

        split_factor = float(mc.get("split_factor", 1.0))
        merged["amount"] = merged["amount"] * split_factor

        annual = merged[["date", "amount"]].rename(columns={"amount": "value"})
        # scale by the (monthly) return/price proxy
        if return_df is None or return_df.empty:
            raise RuntimeError("worldbank_ratio_gdp_amount_scaled 需要 return_df 用于月度缩放")
        return scale_annual_to_monthly(annual, return_df)

    if method == "fred_ratio_times_gdp_amount_scaled":
        fred_ratio_id = mc["fred_ratio_series_id"]
        gdp_cfg = mc["worldbank_gdp"]
        split_factor = float(mc.get("split_factor", 1.0))

        fred = get_fred()
        ratio_s = fred.get_series(fred_ratio_id).dropna()
        if ratio_s.empty:
            raise RuntimeError(f"fred_ratio_times_gdp_amount_scaled: ratio 无数据: {fred_ratio_id}")

        ratio_ann = pd.DataFrame(
            {
                "date": ratio_s.resample("YS").last().index.strftime("%Y-12-31"),
                "ratio": ratio_s.resample("YS").last().values,
            }
        ).dropna()

        gdp_annual = fetch_worldbank_annual(gdp_cfg["country"], gdp_cfg["indicator"])
        gdp_annual = gdp_annual.rename(columns={"value": "gdp"})
        merged = ratio_ann.merge(gdp_annual, on="date", how="inner").dropna()
        if merged.empty:
            raise RuntimeError("fred_ratio_times_gdp_amount_scaled：合并后为空")

        if float(merged["ratio"].max()) > 2.0:
            merged["amount"] = (merged["ratio"] / 100.0) * merged["gdp"]
        else:
            merged["amount"] = merged["ratio"] * merged["gdp"]

        merged["amount"] = merged["amount"] * split_factor
        annual = merged[["date", "amount"]].rename(columns={"amount": "value"})
        if return_df is None or return_df.empty:
            raise RuntimeError("fred_ratio_times_gdp_amount_scaled 需要 return_df 用于月度缩放")
        return scale_annual_to_monthly(annual, return_df)

    if method == "gdp_times_return_proxy":
        gdp_cfg = mc["worldbank_gdp"]
        split_factor = float(mc.get("split_factor", 1.0))
        gdp_annual = fetch_worldbank_annual(gdp_cfg["country"], gdp_cfg["indicator"])
        if gdp_annual.empty:
            raise RuntimeError("gdp_times_return_proxy：GDP 年度锚为空")
        gdp_annual["value"] = pd.to_numeric(gdp_annual["value"], errors="coerce") * split_factor
        annual = gdp_annual[["date", "value"]].rename(columns={"value": "value"})
        if return_df is None or return_df.empty:
            raise RuntimeError("gdp_times_return_proxy 需要 return_df")
        return scale_annual_to_monthly(annual, return_df)

    if method == "cn_housing_zero_dep":
        return fetch_cn_housing_zero_dep_marketcap(mc)

    if method == "oil_trade_usd":
        return fetch_oil_trade_usd_monthly(mc)

    if method == "futures_notional_proxy":
        sym = mc["symbol"]
        mult = float(mc["contract_multiplier"])
        price_floor = float(mc.get("price_floor", 0.0))
        start = mc.get("start", "1990-01-01")
        return fetch_futures_notional_proxy_monthly(sym, mult, price_floor=price_floor, start=start)

    raise ValueError(f"未知市值方法: {method}")


def build_btc_validation_component() -> None:
    """Blockchain 市值 vs yfinance 价格 × 中位估算流通量。"""
    mcap_path = DATA_DIR / "csv/rotation/marketcap/btc.csv"
    if not mcap_path.exists():
        return
    price = fetch_yfinance_monthly("BTC-USD")
    mcap = pd.read_csv(mcap_path)
    mcap["date"] = pd.to_datetime(mcap["date"])
    price["date"] = pd.to_datetime(price["date"])
    merged = mcap.merge(price, on="date")
    if merged.empty:
        return
    supply = (merged["value_usd"] / merged["value"]).median()
    out = price.copy()
    out["value"] = out["value"] * supply
    save_simple(out, "csv/rotation/marketcap/_components/btc_price_supply.csv")


def run_validation(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    VALIDATE_DIR.mkdir(parents=True, exist_ok=True)
    report: list[dict[str, Any]] = []

    for pair in manifest.get("cross_validation", []):
        try:
            a_path = DATA_DIR / pair["a"]["path"]
            b_path = None
            if "b" in pair:
                b_path = DATA_DIR / pair["b"]["path"]

            if not a_path.exists() or (b_path is not None and not b_path.exists()):
                raise FileNotFoundError("验证文件缺失")
            a = pd.read_csv(a_path)
            a_col = pair["a"]["column"]
            a["date"] = pd.to_datetime(a["date"])
            b = None
            b_col = None
            if b_path is not None:
                b = pd.read_csv(b_path)
                b_col = pair["b"]["column"]
                b["date"] = pd.to_datetime(b["date"])
            method = pair["method"]

            if method == "annual_end":
                a_ann = a.set_index("date")[a_col].resample("YS").last()
                b_ann = b.set_index("date")[b_col].resample("YS").last()
                merged = pd.concat([a_ann, b_ann], axis=1, keys=["a", "b"]).dropna()
            elif method == "monthly_overlap":
                merged = pd.merge(
                    a[["date", a_col]].rename(columns={a_col: "a"}),
                    b[["date", b_col]].rename(columns={b_col: "b"}),
                    on="date",
                    how="inner",
                ).dropna()
            elif method == "yoy_growth_corr":
                a_s = a.set_index("date")[a_col].sort_index().pct_change(12)
                b_s = b.set_index("date")[b_col].sort_index().pct_change(12)
                merged = pd.concat([a_s, b_s], axis=1, keys=["a", "b"]).dropna()
            elif method == "monthly_variation":
                merged = None
                s = a.set_index("date")[a_col].sort_index()
                pct = s.pct_change().dropna()
                nonzero_ratio = float((pct.abs() > 0).mean()) if len(pct) else None
                pct_std = float(pct.std()) if len(pct) else None
                pct_mean_abs = float(pct.abs().mean()) if len(pct) else None

                out = pd.DataFrame(
                    [
                        {
                            "date_start": s.index.min().strftime("%Y-%m-%d"),
                            "date_end": s.index.max().strftime("%Y-%m-%d"),
                            "months": int(len(s)),
                            "pct_nonzero_ratio": nonzero_ratio,
                            "pct_std": pct_std,
                            "pct_mean_abs": pct_mean_abs,
                        }
                    ]
                )
                out_path = VALIDATE_DIR / f"{pair['id']}.csv"
                out.to_csv(out_path, index=False, float_format="%.6f")
                report.append(
                    {
                        "id": pair["id"],
                        "name": pair["name"],
                        "method": method,
                        "overlap_start": out.loc[0, "date_start"],
                        "overlap_end": out.loc[0, "date_end"],
                        "rows": int(out.loc[0, "months"]),
                        "correlation": None,
                        "mean_abs_diff": pct_std,
                        "csv": f"csv/validate/{pair['id']}.csv",
                    }
                )
                print(f"✓ 验证 {pair['id']}: months={len(s)} nonzero={nonzero_ratio:.3f} std={pct_std:.6f}")
                continue
            else:
                raise ValueError(method)

            if merged is None:
                raise RuntimeError("内部错误：merged 为空")
            if merged.empty:
                raise RuntimeError("无重叠区间")

            if method != "yoy_growth_corr":
                merged["diff_pct"] = (merged["a"] - merged["b"]) / merged["b"] * 100

            out = merged.reset_index()
            if "date" not in out.columns:
                out = out.rename(columns={out.columns[0]: "date"})
            out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
            out_path = VALIDATE_DIR / f"{pair['id']}.csv"
            out.to_csv(out_path, index=False, float_format="%.6f")

            corr = merged["a"].corr(merged["b"])
            mae = (merged["a"] - merged["b"]).abs().mean() if method != "yoy_growth_corr" else None
            report.append(
                {
                    "id": pair["id"],
                    "name": pair["name"],
                    "method": method,
                    "overlap_start": out["date"].iloc[0],
                    "overlap_end": out["date"].iloc[-1],
                    "rows": len(out),
                    "correlation": round(float(corr), 4) if corr == corr else None,
                    "mean_abs_diff": round(float(mae), 4) if mae is not None else None,
                    "csv": f"csv/validate/{pair['id']}.csv",
                }
            )
            print(f"✓ 验证 {pair['id']}: r={corr:.3f}, n={len(out)}")
        except Exception as exc:
            report.append({"id": pair["id"], "name": pair["name"], "error": str(exc)})
            print(f"✗ 验证 {pair['id']}: {exc}", file=sys.stderr)

    out_path = DATA_DIR / "rotation_validate_report.json"
    out_path.write_text(
        json.dumps(
            {"generated_at": datetime.now().isoformat(timespec="seconds"), "pairs": report},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  → {out_path.relative_to(ROOT)}")
    return report


def describe_df(df: pd.DataFrame, col: str = "value") -> str:
    if df.empty:
        return "0 行"
    return f"{len(df)} 行, {df['date'].iloc[0]} → {df['date'].iloc[-1]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取轮动 19 项回报与市值")
    parser.add_argument("--id", nargs="*", help="只拉指定资产 id")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args()

    manifest = load_manifest()
    if args.validate_only:
        build_btc_validation_component()
        run_validation(manifest)
        return 0

    assets = manifest["assets"]
    if args.id:
        id_set = set(args.id)
        assets = [a for a in assets if a["id"] in id_set]

    print(f"轮动数据拉取 | {len(assets)} 项 | {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("-" * 60)

    ok, failed = 0, []
    for i, asset in enumerate(assets):
        if i > 0 and args.delay > 0:
            time.sleep(args.delay)
        aid = asset["id"]
        try:
            ret_df = fetch_return_series(asset["return"])
            save_simple(ret_df, asset["return"]["csv"])
            print(f"✓ {aid} 回报: {describe_df(ret_df)}")

            mc_spec = asset.get("marketcap") or {}
            if mc_spec.get("method") not in (None, "na") and mc_spec.get("csv"):
                mc_df = fetch_marketcap_series(asset, ret_df)
                if mc_df is not None and not mc_df.empty:
                    save_marketcap(mc_df, mc_spec["csv"])
                    print(f"  市值: {describe_df(mc_df, 'value_usd')}")
                else:
                    print(f"  市值: 空")
            else:
                print(f"  市值: N/A")
            ok += 1
        except Exception as exc:
            print(f"✗ {aid}: {exc}", file=sys.stderr)
            failed.append(aid)

    print("-" * 60)
    print("交叉验证...")
    try:
        build_btc_validation_component()
        run_validation(manifest)
    except Exception as exc:
        print(f"验证阶段警告: {exc}", file=sys.stderr)

    print("-" * 60)
    print(f"完成: {ok} 成功, {len(failed)} 失败")
    if failed:
        print(f"失败: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
