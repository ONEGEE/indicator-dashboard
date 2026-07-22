#!/usr/bin/env python3
"""拉取 RRG 日频价格（大类资产 / 美股 GICS / A股申万 / 国家指数），并导出前端 JSON。

用法：
  python scripts/fetch_rrg.py
  python scripts/fetch_rrg.py --mode cross_asset
  python scripts/fetch_rrg.py --mode us_gics
  python scripts/fetch_rrg.py --mode cn_sw
  python scripts/fetch_rrg.py --mode country
  python scripts/fetch_rrg.py --mode all
  python scripts/fetch_rrg.py --manifest data/manifest_rrg_us_gics.json --out rrg_prices_us_gics.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.data_lib import DATA_DIR, finalize_simple, save_simple

WEB_PUBLIC = ROOT / "web" / "public"

MODE_DEFAULTS: dict[str, dict[str, str]] = {
    "cross_asset": {
        "manifest": "manifest_rrg_cross_asset.json",
        "out": "rrg_prices.json",
        "csv_subdir": "rrg",
    },
    "us_gics": {
        "manifest": "manifest_rrg_us_gics.json",
        "out": "rrg_prices_us_gics.json",
        "csv_subdir": "rrg/us_gics",
    },
    "cn_sw": {
        "manifest": "manifest_rrg_cn_sw.json",
        "out": "rrg_prices_cn_sw.json",
        "csv_subdir": "rrg/cn_sw",
    },
    "country": {
        "manifest": "manifest_rrg_country.json",
        "out": "rrg_prices_country.json",
        "csv_subdir": "rrg/country",
    },
}


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def fetch_yfinance_daily(symbol: str) -> pd.DataFrame:
    """日频收盘价，尽量拉到可追溯起点（period=max）。"""
    import yfinance as yf

    raw = yf.download(
        symbol,
        period="max",
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if raw is None or raw.empty:
        raw = yf.download(
            symbol,
            start="1970-01-01",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    if raw is None or raw.empty:
        raise RuntimeError(f"yfinance 无数据: {symbol}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] for c in raw.columns]
    close = raw["Close"].dropna()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    today = pd.Timestamp.today().normalize()
    close = close[close.index <= today]
    if close.empty:
        raise RuntimeError(f"yfinance 无有效历史: {symbol}")
    out = close.reset_index()
    out.columns = ["date", "value"]
    return finalize_simple(out)


def fetch_akshare_sw(symbol: str) -> pd.DataFrame:
    """申万行业指数日频（symbol 为 801010，不含 .SI）。"""
    import akshare as ak

    code = str(symbol).replace(".SI", "").strip()
    raw = ak.index_hist_sw(symbol=code, period="day")
    if raw is None or raw.empty:
        raise RuntimeError(f"akshare_sw 无数据: {code}")
    # 列名可能因版本而异
    cols = {c: str(c) for c in raw.columns}
    date_col = next((c for c in raw.columns if "日期" in str(c) or str(c).lower() == "date"), None)
    close_col = next((c for c in raw.columns if "收盘" in str(c) or str(c).lower() == "close"), None)
    if date_col is None or close_col is None:
        raise RuntimeError(f"akshare_sw 列异常: {list(cols.values())}")
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(raw[date_col]),
            "value": pd.to_numeric(raw[close_col], errors="coerce"),
        }
    ).dropna()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    today = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    out = out[out["date"] <= today]
    if out.empty:
        raise RuntimeError(f"akshare_sw 无有效历史: {code}")
    return finalize_simple(out)


def fetch_akshare_zh_index(symbol: str) -> pd.DataFrame:
    """A股标准指数日频，symbol 形如 sh000300。"""
    import akshare as ak

    raw = ak.stock_zh_index_daily(symbol=symbol)
    if raw is None or raw.empty:
        raise RuntimeError(f"akshare_zh_index 无数据: {symbol}")
    date_col = "date" if "date" in raw.columns else raw.columns[0]
    close_col = "close" if "close" in raw.columns else "收盘"
    if close_col not in raw.columns:
        raise RuntimeError(f"akshare_zh_index 列异常: {list(raw.columns)}")
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(raw[date_col]),
            "value": pd.to_numeric(raw[close_col], errors="coerce"),
        }
    ).dropna()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    today = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    out = out[out["date"] <= today]
    if out.empty:
        raise RuntimeError(f"akshare_zh_index 无有效历史: {symbol}")
    return finalize_simple(out)


def fetch_asset(asset: dict[str, Any]) -> pd.DataFrame:
    src = asset.get("source", "yfinance")
    if src == "yfinance":
        return fetch_yfinance_daily(asset["symbol"])
    if src == "akshare_sw":
        return fetch_akshare_sw(asset["symbol"])
    if src == "akshare_zh_index":
        return fetch_akshare_zh_index(asset["symbol"])
    raise ValueError(f"未知来源: {src}")


def export_web(
    manifest: dict[str, Any],
    assets_ok: list[dict[str, Any]],
    csv_subdir: str,
) -> dict[str, Any]:
    today = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    series = []
    for asset in assets_ok:
        path = DATA_DIR / asset["csv"]
        df = pd.read_csv(path)
        points = [
            [str(r["date"])[:10], round(float(r["value"]), 6)]
            for _, r in df.iterrows()
            if pd.notna(r["value"]) and str(r["date"])[:10] <= today
        ]
        if len(points) < 60:
            continue
        item: dict[str, Any] = {
            "id": asset["id"],
            "name": asset["name"],
            "name_en": asset.get("name_en"),
            "group": asset.get("group"),
            "symbol": asset["symbol"],
            "vehicle": asset.get("vehicle"),
            "notes": asset.get("notes", ""),
            "benchmark_candidate": bool(asset.get("benchmark_candidate")),
            "points": points,
        }
        if asset.get("level"):
            item["level"] = asset["level"]
        if asset.get("parent_id") is not None:
            item["parent_id"] = asset.get("parent_id")
        elif asset.get("level") == "L1":
            item["parent_id"] = None
        series.append(item)

    rrg = dict(manifest.get("rrg") or {})
    rrg["frequency_options"] = ["weekly", "monthly", "yearly"]
    rrg["base_frequency"] = "daily"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": manifest.get("mode", "cross_asset"),
        "title": manifest.get("title"),
        "description": manifest.get("description"),
        "taxonomy": manifest.get("taxonomy"),
        "rrg": rrg,
        "benchmarks": manifest.get("benchmarks"),
        "counts": {"assets": len(series)},
        "series": series,
    }


def run_one(
    *,
    manifest_path: Path,
    out_name: str,
    csv_subdir: str,
    ids: list[str] | None,
    delay: float,
    export_only: bool,
) -> int:
    manifest = load_manifest(manifest_path)
    assets = list(manifest["assets"])
    if ids:
        id_set = set(ids)
        assets = [a for a in assets if a["id"] in id_set]

    csv_root = DATA_DIR / "csv" / csv_subdir
    csv_root.mkdir(parents=True, exist_ok=True)
    assets_ok: list[dict[str, Any]] = []

    if not export_only:
        print(
            f"{manifest.get('title', 'RRG')} | {len(assets)} 项 | "
            f"{datetime.now():%Y-%m-%d %H:%M:%S}"
        )
        print("-" * 60)
        failed: list[str] = []
        for i, asset in enumerate(assets):
            if i and delay:
                time.sleep(delay)
            aid = asset["id"]
            rel = f"csv/{csv_subdir}/{aid}.csv"
            try:
                df = fetch_asset(asset)
                save_simple(df, rel)
                print(
                    f"✓ {aid} ({asset['symbol']}): {len(df)} 日, "
                    f"{df['date'].iloc[0]} → {df['date'].iloc[-1]}"
                )
                assets_ok.append({**asset, "csv": rel})
            except Exception as exc:
                print(f"✗ {aid}: {exc}", file=sys.stderr)
                failed.append(aid)
                if (DATA_DIR / rel).exists():
                    assets_ok.append({**asset, "csv": rel})
                    print(f"  · 使用缓存 {rel}")
        if failed:
            print(f"失败: {', '.join(failed)}", file=sys.stderr)
    else:
        for asset in manifest["assets"]:
            rel = f"csv/{csv_subdir}/{asset['id']}.csv"
            if (DATA_DIR / rel).exists():
                assets_ok.append({**asset, "csv": rel})

    web = export_web(manifest, assets_ok, csv_subdir)
    out = DATA_DIR / out_name
    out.write_text(json.dumps(web, ensure_ascii=False, indent=2), encoding="utf-8")
    WEB_PUBLIC.mkdir(parents=True, exist_ok=True)
    (WEB_PUBLIC / out_name).write_text(
        json.dumps(web, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print("-" * 60)
    print(f"✓ rrg web: {web['counts']['assets']} 项 → {out.relative_to(ROOT)}")
    print(f"  → web/public/{out_name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取 RRG 日频价格（最长历史）")
    parser.add_argument(
        "--mode",
        choices=["cross_asset", "us_gics", "cn_sw", "country", "all"],
        default=None,
        help="预设模式（与 --manifest/--out 二选一；默认 cross_asset）",
    )
    parser.add_argument("--manifest", type=str, help="自定义 manifest 路径")
    parser.add_argument("--out", type=str, help="输出 JSON 文件名（相对 data/ 与 web/public/）")
    parser.add_argument("--csv-subdir", type=str, help="CSV 子目录（相对 data/csv/）")
    parser.add_argument("--id", nargs="*", help="只拉指定 id")
    parser.add_argument("--delay", type=float, default=0.4)
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()

    if args.manifest:
        manifest_path = Path(args.manifest)
        if not manifest_path.is_absolute():
            manifest_path = ROOT / manifest_path
        out_name = args.out or "rrg_prices.json"
        csv_subdir = args.csv_subdir or "rrg"
        return run_one(
            manifest_path=manifest_path,
            out_name=out_name,
            csv_subdir=csv_subdir,
            ids=args.id,
            delay=args.delay,
            export_only=args.export_only,
        )

    mode = args.mode or "cross_asset"
    modes = list(MODE_DEFAULTS.keys()) if mode == "all" else [mode]
    code = 0
    for m in modes:
        cfg = MODE_DEFAULTS[m]
        # backwards compat: prefer cross_asset file, fall back to manifest_rrg.json
        manifest_path = DATA_DIR / cfg["manifest"]
        if m == "cross_asset" and not manifest_path.exists():
            manifest_path = DATA_DIR / "manifest_rrg.json"
        rc = run_one(
            manifest_path=manifest_path,
            out_name=args.out if args.out and mode != "all" else cfg["out"],
            csv_subdir=args.csv_subdir if args.csv_subdir and mode != "all" else cfg["csv_subdir"],
            ids=args.id,
            delay=args.delay,
            export_only=args.export_only,
        )
        if rc != 0:
            code = rc
    return code


if __name__ == "__main__":
    raise SystemExit(main())
