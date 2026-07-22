#!/usr/bin/env python3
"""统一拉取中美宏观 / 房地产相关数据，写入 data/csv/macro/。

数据源：
  - FRED（美国官方宏观，需 .env 中 FRED_API_KEY）
  - AkShare（中国宏观 / 房价 / LPR）

配置：data/manifest_macro.json

用法：
  python scripts/fetch_macro.py
  python scripts/fetch_macro.py --mode update
  python scripts/fetch_macro.py --region US,CN
  python scripts/fetch_macro.py --subcategory housing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MANIFEST_PATH = DATA_DIR / "manifest_macro.json"
SIMPLE_COLUMNS = ["date", "value"]


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def select_series(
    manifest: dict[str, Any],
    ids: list[str] | None = None,
    regions: list[str] | None = None,
    subcategory: str | None = None,
) -> list[dict[str, Any]]:
    series = manifest["series"]
    if ids:
        id_set = set(ids)
        series = [s for s in series if s["id"] in id_set]
    if regions:
        region_set = {r.upper() for r in regions}
        series = [s for s in series if s["region"] in region_set]
    if subcategory:
        series = [s for s in series if s.get("subcategory") == subcategory]
    return series


def finalize_simple(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=SIMPLE_COLUMNS)
    out = df[SIMPLE_COLUMNS].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["date", "value"])
    out = out.drop_duplicates(subset=["date"], keep="last")
    return out.sort_values("date").reset_index(drop=True)


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format="%.6f")


def get_fred():
    load_dotenv(ROOT / ".env")
    key = os.getenv("FRED_API_KEY")
    if not key or key.startswith("your_"):
        raise RuntimeError("请在项目根目录 .env 中设置 FRED_API_KEY")
    from fredapi import Fred

    return Fred(api_key=key)


def fetch_fred(symbol: str) -> pd.DataFrame:
    fred = get_fred()
    series = fred.get_series(symbol).dropna()
    if series.empty:
        return pd.DataFrame(columns=SIMPLE_COLUMNS)
    out = pd.DataFrame({"date": series.index, "value": series.values})
    return finalize_simple(out)


def fetch_akshare_jin10(func_name: str) -> pd.DataFrame:
    import akshare as ak

    raw = getattr(ak, func_name)()
    if raw is None or raw.empty:
        return pd.DataFrame(columns=SIMPLE_COLUMNS)
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(raw["日期"]),
            "value": pd.to_numeric(raw["今值"], errors="coerce"),
        }
    )
    return finalize_simple(out)


def parse_china_month(text: str) -> pd.Timestamp | pd.NaT:
    m = re.search(r"(\d{4})年(\d{1,2})月", str(text))
    if not m:
        return pd.NaT
    return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)


def parse_china_quarter(text: str) -> pd.Timestamp | pd.NaT:
    text = str(text)
    m = re.search(r"(\d{4})年第(\d)季度", text)
    if m and "第1-" not in text and "-" not in text.split("年")[-1]:
        year, q = int(m.group(1)), int(m.group(2))
        return pd.Timestamp(year=year, month=(q - 1) * 3 + 1, day=1)
    # 累计季度如「2026年第1-2季度」→ 取结束季
    m2 = re.search(r"(\d{4})年第(\d)-(\d)季度", text)
    if m2:
        year, q_end = int(m2.group(1)), int(m2.group(3))
        return pd.Timestamp(year=year, month=(q_end - 1) * 3 + 1, day=1)
    return pd.NaT


def fetch_china_cpi() -> pd.DataFrame:
    import akshare as ak

    raw = ak.macro_china_cpi()
    out = pd.DataFrame(
        {
            "date": raw["月份"].map(parse_china_month),
            "value": pd.to_numeric(raw["全国-同比增长"], errors="coerce"),
        }
    )
    return finalize_simple(out)


def fetch_china_ppi() -> pd.DataFrame:
    import akshare as ak

    raw = ak.macro_china_ppi()
    out = pd.DataFrame(
        {
            "date": raw["月份"].map(parse_china_month),
            "value": pd.to_numeric(raw["当月同比增长"], errors="coerce"),
        }
    )
    return finalize_simple(out)


def fetch_china_m2() -> pd.DataFrame:
    import akshare as ak

    raw = ak.macro_china_money_supply()
    out = pd.DataFrame(
        {
            "date": raw["月份"].map(parse_china_month),
            "value": pd.to_numeric(raw["货币和准货币(M2)-同比增长"], errors="coerce"),
        }
    )
    return finalize_simple(out)


def fetch_china_gdp() -> pd.DataFrame:
    import akshare as ak

    raw = ak.macro_china_gdp()
    out = pd.DataFrame(
        {
            "date": raw["季度"].map(parse_china_quarter),
            "value": pd.to_numeric(raw["国内生产总值-同比增长"], errors="coerce"),
        }
    )
    return finalize_simple(out)


def fetch_china_lpr() -> pd.DataFrame:
    import akshare as ak

    raw = ak.macro_china_lpr()
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(raw["TRADE_DATE"]),
            "lpr_1y": pd.to_numeric(raw["LPR1Y"], errors="coerce"),
            "lpr_5y": pd.to_numeric(raw["LPR5Y"], errors="coerce"),
        }
    )
    # LPR 改革前只有旧基准利率；保留有 LPR 报价的记录
    out = out.dropna(subset=["lpr_1y", "lpr_5y"], how="all")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out = out.drop_duplicates(subset=["date"], keep="last")
    return out.sort_values("date").reset_index(drop=True)


def fetch_china_house() -> pd.DataFrame:
    import akshare as ak

    raw = ak.macro_china_new_house_price()
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(raw["日期"]),
            "city": raw["城市"],
            "new_yoy": pd.to_numeric(raw["新建商品住宅价格指数-同比"], errors="coerce"),
            "new_mom": pd.to_numeric(raw["新建商品住宅价格指数-环比"], errors="coerce"),
            "new_base": pd.to_numeric(raw["新建商品住宅价格指数-定基"], errors="coerce"),
            "resale_yoy": pd.to_numeric(raw["二手住宅价格指数-同比"], errors="coerce"),
            "resale_mom": pd.to_numeric(raw["二手住宅价格指数-环比"], errors="coerce"),
            "resale_base": pd.to_numeric(raw["二手住宅价格指数-定基"], errors="coerce"),
        }
    )
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out = out.drop_duplicates(subset=["date", "city"], keep="last")
    return out.sort_values(["date", "city"]).reset_index(drop=True)


def fetch_by_source(item: dict[str, Any]) -> pd.DataFrame:
    source = item["source"]
    symbol = item["symbol"]
    if source == "fred":
        return fetch_fred(symbol)
    if source == "akshare_jin10":
        return fetch_akshare_jin10(symbol)
    if source == "akshare_china_cpi":
        return fetch_china_cpi()
    if source == "akshare_china_ppi":
        return fetch_china_ppi()
    if source == "akshare_china_m2":
        return fetch_china_m2()
    if source == "akshare_china_gdp":
        return fetch_china_gdp()
    if source == "akshare_china_lpr":
        return fetch_china_lpr()
    if source == "akshare_china_house":
        return fetch_china_house()
    raise ValueError(f"未知数据源: {source}")


def describe(df: pd.DataFrame) -> str:
    if df.empty:
        return "0 行"
    if "date" in df.columns:
        return f"{len(df)} 行, {df['date'].iloc[0]} → {df['date'].iloc[-1]}"
    return f"{len(df)} 行"


def main() -> int:
    parser = argparse.ArgumentParser(description="统一拉取中美宏观与房地产数据")
    parser.add_argument(
        "--mode",
        choices=["full", "update"],
        default="full",
        help="宏观序列体量小，full/update 均全量重拉后覆盖写入",
    )
    parser.add_argument("--id", action="append", help="只拉指定 id，可重复传入")
    parser.add_argument("--region", help="按地区筛选，逗号分隔，如 US,CN")
    parser.add_argument("--subcategory", help="按子类筛选，如 housing / prices / rates")
    parser.add_argument("--delay", type=float, default=0.4, help="每个请求间隔秒数")
    args = parser.parse_args()

    manifest = load_manifest()
    regions = [r.strip() for r in args.region.split(",")] if args.region else None
    series = select_series(
        manifest,
        ids=args.id,
        regions=regions,
        subcategory=args.subcategory,
    )
    if not series:
        print("未匹配到任何宏观序列", file=sys.stderr)
        return 1

    print(
        f"模式: {args.mode} | 共 {len(series)} 个序列 | "
        f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    )
    print("-" * 60)

    ok, failed = 0, []
    for i, item in enumerate(series):
        if i > 0 and args.delay > 0:
            time.sleep(args.delay)
        label = f"{item['name']} ({item['symbol']}/{item['source']})"
        try:
            if item["id"] == "us_cpi":
                # CPIAUCSL 写入组件文件，最终由 stitch_series 拼接为 us_cpi
                df = fetch_fred("CPIAUCSL")
                comp = DATA_DIR / "csv/macro/_components/us_cpi_cpiausl.csv"
                save_csv(df, comp)
                print(f"✓ {label}: {describe(df)} (组件)")
                print(f"  → {comp.relative_to(ROOT)}")
                ok += 1
                continue
            df = fetch_by_source(item)
            if df.empty:
                raise RuntimeError("返回空数据")
            path = DATA_DIR / item["csv"]
            save_csv(df, path)
            print(f"✓ {label}: {describe(df)}")
            print(f"  → {path.relative_to(ROOT)}")
            ok += 1
        except Exception as exc:
            print(f"✗ {label}: {exc}", file=sys.stderr)
            failed.append(item["id"])

    print("-" * 60)
    print(f"完成: {ok} 成功, {len(failed)} 失败")
    if failed:
        print(f"失败列表: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
