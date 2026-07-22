#!/usr/bin/env python3
"""统一拉取主要股票指数日线数据，写入 data/csv/。

数据源：
  - yfinance：美/日/韩/港（恒生）
  - akshare：A股主要指数、恒生科技

配置：data/manifest.json

用法：
  python scripts/fetch_indices.py                  # 全量拉取所有指数
  python scripts/fetch_indices.py --mode update    # 增量更新（定时任务推荐）
  python scripts/fetch_indices.py --id cn_sse     # 只拉单个
  python scripts/fetch_indices.py --region US,CN  # 按地区筛选
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MANIFEST_PATH = DATA_DIR / "manifest.json"
COLUMNS = ["date", "open", "high", "low", "close", "volume"]
UPDATE_OVERLAP_DAYS = 7
AK_DEFAULT_START = "19900101"


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def select_series(
    manifest: dict[str, Any],
    ids: list[str] | None = None,
    regions: list[str] | None = None,
) -> list[dict[str, Any]]:
    series = manifest["series"]
    if ids:
        id_set = set(ids)
        series = [s for s in series if s["id"] in id_set]
    if regions:
        region_set = {r.upper() for r in regions}
        series = [s for s in series if s["region"] in region_set]
    return series


def to_ymd(value: str | None, compact: bool = False) -> str | None:
    if not value:
        return None
    dt = pd.to_datetime(value)
    return dt.strftime("%Y%m%d" if compact else "%Y-%m-%d")


def finalize(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    out = df[COLUMNS].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["date", "close"])
    out = out.drop_duplicates(subset=["date"], keep="last")
    return out.sort_values("date").reset_index(drop=True)


def fetch_yfinance(symbol: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    if start or end:
        raw = ticker.history(start=start, end=end, auto_adjust=True)
    else:
        raw = ticker.history(period="max", auto_adjust=True)
    if raw.empty:
        return pd.DataFrame(columns=COLUMNS)

    out = raw.reset_index()
    out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None)
    out = out.rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    return finalize(out)


def fetch_akshare_cn(symbol: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    import akshare as ak

    start_s = to_ymd(start, compact=True) or AK_DEFAULT_START
    end_s = to_ymd(end, compact=True) or datetime.now().strftime("%Y%m%d")
    raw = ak.index_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_s,
        end_date=end_s,
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=COLUMNS)

    out = pd.DataFrame(
        {
            "date": raw["日期"],
            "open": raw["开盘"],
            "high": raw["最高"],
            "low": raw["最低"],
            "close": raw["收盘"],
            "volume": raw["成交量"],
        }
    )
    return finalize(out)


def fetch_akshare_hk(symbol: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    import akshare as ak

    raw = ak.stock_hk_index_daily_em(symbol=symbol)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=COLUMNS)

    # 东财港指字段: date/open/high/low/latest，无成交量
    out = pd.DataFrame(
        {
            "date": raw["date"],
            "open": raw["open"],
            "high": raw["high"],
            "low": raw["low"],
            "close": raw["latest"],
            "volume": 0,
        }
    )
    out = finalize(out)
    if start:
        out = out[out["date"] >= to_ymd(start)]
    if end:
        out = out[out["date"] <= to_ymd(end)]
    return out.reset_index(drop=True)


def fetch_by_source(
    item: dict[str, Any],
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    source = item["source"]
    symbol = item["symbol"]
    if source == "yfinance":
        return fetch_yfinance(symbol, start=start, end=end)
    if source == "akshare":
        return fetch_akshare_cn(symbol, start=start, end=end)
    if source == "akshare_hk":
        return fetch_akshare_hk(symbol, start=start, end=end)
    raise ValueError(f"未知数据源: {source}")


def read_existing_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if df.empty:
        return None
    return finalize(df)


def merge_history(existing: pd.DataFrame | None, fresh: pd.DataFrame) -> pd.DataFrame:
    if existing is None or existing.empty:
        return fresh
    merged = pd.concat([existing, fresh], ignore_index=True)
    return finalize(merged)


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format="%.4f")


def update_fetch_start(csv_path: Path) -> str | None:
    existing = read_existing_csv(csv_path)
    if existing is None or existing.empty:
        return None
    last_date = pd.to_datetime(existing["date"].iloc[-1])
    return (last_date - timedelta(days=UPDATE_OVERLAP_DAYS)).strftime("%Y-%m-%d")


def fetch_one(
    item: dict[str, Any],
    mode: str,
    start: str | None,
    end: str | None,
) -> tuple[pd.DataFrame, Path]:
    csv_path = DATA_DIR / item["csv"]
    fetch_start = start
    existing = None

    if mode == "update" and not start:
        existing = read_existing_csv(csv_path)
        fetch_start = update_fetch_start(csv_path)

    fresh = fetch_by_source(item, start=fetch_start, end=end)
    if fresh.empty:
        raise RuntimeError(f"未获取到数据: {item['symbol']} via {item['source']}")

    df = merge_history(existing, fresh) if mode == "update" else fresh
    save_csv(df, csv_path)
    return df, csv_path


def main() -> int:
    parser = argparse.ArgumentParser(description="统一拉取主要股票指数日线数据")
    parser.add_argument(
        "--mode",
        choices=["full", "update"],
        default="full",
        help="full=全量拉取; update=增量更新（定时任务推荐）",
    )
    parser.add_argument("--id", action="append", help="只拉指定 id，可重复传入")
    parser.add_argument("--region", help="按地区筛选，逗号分隔，如 US,CN,HK")
    parser.add_argument("--start", help="起始日期 YYYY-MM-DD（覆盖 update 自动计算）")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--delay", type=float, default=0.8, help="每个请求间隔秒数")
    args = parser.parse_args()

    manifest = load_manifest()
    regions = [r.strip() for r in args.region.split(",")] if args.region else None
    series = select_series(manifest, ids=args.id, regions=regions)

    if not series:
        print("未匹配到任何指数，请检查 --id / --region 参数", file=sys.stderr)
        return 1

    print(f"模式: {args.mode} | 共 {len(series)} 个指数 | {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("-" * 60)

    ok, failed = 0, []
    for i, item in enumerate(series):
        if i > 0 and args.delay > 0:
            time.sleep(args.delay)

        label = f"{item['name']} ({item['symbol']}/{item['source']})"
        try:
            df, path = fetch_one(item, args.mode, args.start, args.end)
            print(
                f"✓ {label}: {len(df)} 行, "
                f"{df['date'].iloc[0]} → {df['date'].iloc[-1]}"
            )
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
