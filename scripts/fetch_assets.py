#!/usr/bin/env python3
"""拉取债券 / 商品 / 贵金属行情，写入 data/csv/assets/。

数据源：yfinance + AkShare(中美国债收益率)
配置：data/manifest_assets.json
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
MANIFEST_PATH = DATA_DIR / "manifest_assets.json"
COLUMNS = ["date", "open", "high", "low", "close", "volume"]
UPDATE_OVERLAP_DAYS = 7


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def select_series(
    manifest: dict[str, Any],
    ids: list[str] | None = None,
    regions: list[str] | None = None,
    pillar: str | None = None,
) -> list[dict[str, Any]]:
    series = manifest["series"]
    if ids:
        id_set = set(ids)
        series = [s for s in series if s["id"] in id_set]
    if regions:
        region_set = {r.upper() for r in regions}
        series = [s for s in series if s["region"] in region_set]
    if pillar:
        series = [s for s in series if s.get("pillar") == pillar]
    return series


def finalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    out = df[COLUMNS].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["date", "close"])
    out = out.drop_duplicates(subset=["date"], keep="last")
    return out.sort_values("date").reset_index(drop=True)


def finalize_simple(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["date", "value"])
    out = df[["date", "value"]].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["date", "value"])
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
    return finalize_ohlcv(out)


_ZH_US_RATE_CACHE: pd.DataFrame | None = None


def load_zh_us_rate() -> pd.DataFrame:
    global _ZH_US_RATE_CACHE
    if _ZH_US_RATE_CACHE is not None:
        return _ZH_US_RATE_CACHE
    import akshare as ak

    _ZH_US_RATE_CACHE = ak.bond_zh_us_rate(start_date="19901219")
    return _ZH_US_RATE_CACHE


def fetch_zh_us_rate_column(column: str) -> pd.DataFrame:
    raw = load_zh_us_rate()
    if column not in raw.columns:
        raise RuntimeError(f"列不存在: {column}")
    out = pd.DataFrame({"date": pd.to_datetime(raw["日期"]), "value": raw[column]})
    return finalize_simple(out)


def fetch_by_source(item: dict[str, Any], start: str | None = None, end: str | None = None) -> pd.DataFrame:
    source = item["source"]
    symbol = item["symbol"]
    if source == "yfinance":
        return fetch_yfinance(symbol, start=start, end=end)
    if source == "akshare_zh_us_rate":
        return fetch_zh_us_rate_column(symbol)
    raise ValueError(f"未知数据源: {source}")


def read_existing(path: Path, simple: bool) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if df.empty:
        return None
    return finalize_simple(df) if simple else finalize_ohlcv(df)


def merge_frames(existing: pd.DataFrame | None, fresh: pd.DataFrame, simple: bool) -> pd.DataFrame:
    if existing is None or existing.empty:
        return fresh
    merged = pd.concat([existing, fresh], ignore_index=True)
    return finalize_simple(merged) if simple else finalize_ohlcv(merged)


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format="%.6f")


def update_start(path: Path, simple: bool) -> str | None:
    existing = read_existing(path, simple)
    if existing is None or existing.empty:
        return None
    last = pd.to_datetime(existing["date"].iloc[-1])
    return (last - timedelta(days=UPDATE_OVERLAP_DAYS)).strftime("%Y-%m-%d")


def fetch_one(item: dict[str, Any], mode: str, start: str | None, end: str | None) -> tuple[pd.DataFrame, Path]:
    csv_path = DATA_DIR / item["csv"]
    simple = item["source"] == "akshare_zh_us_rate"
    fetch_start = start
    existing = None
    if mode == "update" and not start and not simple:
        existing = read_existing(csv_path, simple=False)
        fetch_start = update_start(csv_path, simple=False)

    fresh = fetch_by_source(item, start=fetch_start, end=end)
    if fresh.empty:
        raise RuntimeError(f"未获取到数据: {item['symbol']}")

    if mode == "update" and not simple:
        df = merge_frames(existing, fresh, simple=False)
    else:
        df = fresh

    save_csv(df, csv_path)
    return df, csv_path


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取债券/商品/贵金属数据")
    parser.add_argument("--mode", choices=["full", "update"], default="full")
    parser.add_argument("--id", action="append")
    parser.add_argument("--region")
    parser.add_argument("--pillar", help="bond / commodity / precious_metal")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--delay", type=float, default=0.6)
    args = parser.parse_args()

    manifest = load_manifest()
    regions = [r.strip() for r in args.region.split(",")] if args.region else None
    series = select_series(manifest, ids=args.id, regions=regions, pillar=args.pillar)
    if not series:
        print("未匹配到任何资产序列", file=sys.stderr)
        return 1

    print(f"模式: {args.mode} | 共 {len(series)} 个序列 | {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("-" * 60)

    ok, failed = 0, []
    for i, item in enumerate(series):
        if i > 0 and args.delay > 0:
            time.sleep(args.delay)
        label = f"{item['name']} ({item['symbol']}/{item['source']})"
        try:
            df, path = fetch_one(item, args.mode, args.start, args.end)
            print(f"✓ {label}: {len(df)} 行, {df['date'].iloc[0]} → {df['date'].iloc[-1]}")
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
