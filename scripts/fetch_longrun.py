#!/usr/bin/env python3
"""拉取并整理百年长周期数据（JST / David Jacks / Shiller / FRED 延伸）。

与中金《全球资产100年》框架对齐，用于后续回撤/风险收益分析。

用法：
  python scripts/fetch_longrun.py
  python scripts/fetch_longrun.py --skip-download
  python scripts/fetch_longrun.py --validate-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
OUT_DIR = DATA_DIR / "csv" / "longrun"
VALIDATE_DIR = DATA_DIR / "csv" / "validate"
MANIFEST_PATH = DATA_DIR / "manifest_longrun.json"

JST_URL = "https://www.macrohistory.net/app/download/9834512569/JSTdatasetR6.xlsx"
JACKS_URL = "https://davidjacks.org/wp-content/uploads/2026/01/Real-commodity-prices-1850-2025.xlsx"
SHILLER_URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"

UA = {"User-Agent": "Mozilla/5.0 (compatible; databoard/1.0)"}


def load_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as resp:
        dest.write_bytes(resp.read())


def ensure_raw(skip_download: bool) -> dict[str, Path]:
    files = {
        "jst": RAW_DIR / "JSTdatasetR6.xlsx",
        "jacks": RAW_DIR / "jacks_commodity_1850_2025.xlsx",
        "shiller": RAW_DIR / "shiller_ie_data.xls",
    }
    urls = {"jst": JST_URL, "jacks": JACKS_URL, "shiller": SHILLER_URL}
    if not skip_download:
        for key, path in files.items():
            if not path.exists() or path.stat().st_size < 1000:
                print(f"下载 {key}: {urls[key]}")
                download(urls[key], path)
    for key, path in files.items():
        if not path.exists():
            raise FileNotFoundError(f"缺少原始文件: {path}，请先运行不带 --skip-download")
    return files


def finalize_simple(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["date", "value"]].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["date", "value"])
    out = out.drop_duplicates(subset=["date"], keep="last")
    return out.sort_values("date").reset_index(drop=True)


def year_to_date(year: pd.Series) -> pd.Series:
    y = pd.to_numeric(year, errors="coerce").astype("Int64")
    return pd.to_datetime(y.astype(str) + "-01-01", errors="coerce")


def save_series(df: pd.DataFrame, rel_path: str) -> Path:
    path = DATA_DIR / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format="%.6f")
    return path


def export_jst(raw: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    jst = pd.read_excel(raw)
    exported: list[dict[str, Any]] = []
    countries = manifest["jst_countries"]
    for country in countries:
        sub = jst[jst["country"] == country].copy()
        if sub.empty:
            # JST uses full names; map ISO
            iso_map = {"USA": "USA", "UK": "UK", "Germany": "Germany", "France": "France",
                       "Japan": "Japan", "Australia": "Australia"}
            name = iso_map.get(country, country)
            sub = jst[jst["country"] == name].copy()
        for var in manifest["jst_variables"]:
            col = var["column"]
            if col not in sub.columns:
                continue
            out = pd.DataFrame({"date": year_to_date(sub["year"]), "value": sub[col]})
            out = finalize_simple(out)
            if out.empty:
                continue
            cid = country.lower().replace(" ", "_")
            sid = f"jst_{cid}_{var['id_suffix']}"
            rel = f"csv/longrun/{sid}.csv"
            save_series(out, rel)
            exported.append({
                "id": sid,
                "name": f"{country} {var['name']}",
                "name_en": f"{country} {var['column']} (JST)",
                "pillar": var["pillar"],
                "origin": "longrun",
                "category": "longrun",
                "region": country,
                "source": "jst",
                "symbol": col,
                "frequency": "annual",
                "unit": var.get("unit"),
                "csv": rel,
                "tier": "longrun",
                "notes": "JST Macrohistory R6 · 1870-2020",
            })
            print(f"✓ JST {sid}: {len(out)} 行, {out['date'].iloc[0]} → {out['date'].iloc[-1]}")
    return exported


def _parse_jacks_commodities(raw_path: Path) -> pd.DataFrame:
    raw = pd.read_excel(raw_path, sheet_name="Commodities", header=None)
    names = raw.iloc[1].tolist()
    names[0] = "year"
    df = raw.iloc[2:].copy()
    df.columns = names
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    return df.dropna(subset=["year"]).astype({"year": int})


def export_jacks(raw: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    exported: list[dict[str, Any]] = []
    commodities = _parse_jacks_commodities(raw)

    idx_raw = pd.read_excel(raw, sheet_name="Indices", header=None)
    idx_raw.columns = ["year", "idx_1975", "idx_2019", "idx_equal"]
    indices = idx_raw.iloc[2:].copy()
    indices["year"] = pd.to_numeric(indices["year"], errors="coerce")
    indices = indices.dropna(subset=["year"]).astype({"year": int})

    sub_raw = pd.read_excel(raw, sheet_name="Sub-indices")
    sub_raw = sub_raw.rename(columns={
        "Commodities to be grown": "grown",
        "Commodities in the ground": "ground",
        "In the ground, ex-energy": "ground_ex_energy",
    })

    for spec in manifest["jacks_series"]:
        sheet = spec["sheet"]
        col = spec["column"]
        if sheet == "Commodities":
            src = commodities
        elif sheet == "Indices":
            src = indices
        else:
            src = sub_raw
        if col not in src.columns:
            print(f"✗ Jacks 缺列 {col} in {sheet}", file=sys.stderr)
            continue
        out = pd.DataFrame({"date": year_to_date(src["year"]), "value": src[col]})
        out = finalize_simple(out)
        if spec.get("start_row"):
            out = out[out["date"] >= f"{spec['start_row']}-01-01"]
        rel = f"csv/longrun/{spec['id']}.csv"
        save_series(out, rel)
        exported.append({
            "id": spec["id"],
            "name": spec["name"],
            "name_en": spec["id"],
            "pillar": spec["pillar"],
            "origin": "longrun",
            "category": "longrun",
            "region": "GLOBAL",
            "source": "jacks",
            "symbol": col,
            "frequency": "annual",
            "unit": "real_price_index",
            "csv": rel,
            "tier": "longrun",
            "notes": "David Jacks · 1850-2025 实际价格",
        })
        print(f"✓ Jacks {spec['id']}: {len(out)} 行, {out['date'].iloc[0]} → {out['date'].iloc[-1]}")
    return exported


def export_shiller(raw: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    exported: list[dict[str, Any]] = []
    sh = pd.read_excel(raw, sheet_name="Data", skiprows=7)
    sh = sh.dropna(subset=["Date"])
    sh["year"] = sh["Date"].astype(float).astype(int)
    sh["month"] = ((sh["Date"].astype(float) - sh["year"]) * 100 + 0.5).round().astype(int)
    sh["month"] = sh["month"].clip(1, 12)
    sh["date"] = pd.to_datetime({"year": sh["year"], "month": sh["month"], "day": 1})
    price = pd.to_numeric(sh["Price"], errors="coerce")
    out = pd.DataFrame({"date": sh["date"], "value": price})
    out = finalize_simple(out)
    rel = "csv/longrun/us_sp500_shiller.csv"
    save_series(out, rel)
    spec = manifest["shiller_series"][0]
    exported.append({
        "id": spec["id"],
        "name": spec["name"],
        "name_en": "S&P Composite (Shiller)",
        "pillar": spec["pillar"],
        "origin": "longrun",
        "category": "longrun",
        "region": "US",
        "source": "shiller",
        "symbol": "Price",
        "frequency": "monthly",
        "unit": "index",
        "csv": rel,
        "tier": "longrun",
        "notes": "Shiller IE data · 1871-2023，可衔接 yfinance ^GSPC",
    })
    print(f"✓ Shiller us_sp500_shiller: {len(out)} 行, {out['date'].iloc[0]} → {out['date'].iloc[-1]}")
    return exported


def get_fred():
    load_dotenv(ROOT / ".env")
    key = os.getenv("FRED_API_KEY")
    if not key or key.startswith("your_"):
        raise RuntimeError("请在 .env 中设置 FRED_API_KEY")
    from fredapi import Fred

    return Fred(api_key=key)


def export_fred_extended(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    fred = get_fred()
    exported: list[dict[str, Any]] = []
    for spec in manifest["fred_extended"]:
        series = fred.get_series(spec["symbol"]).dropna()
        out = finalize_simple(pd.DataFrame({"date": series.index, "value": series.values}))
        rel = f"csv/longrun/{spec['id']}.csv"
        save_series(out, rel)
        exported.append({
            "id": spec["id"],
            "name": spec["name"],
            "name_en": spec["symbol"],
            "pillar": spec["pillar"],
            "origin": "longrun",
            "category": "longrun",
            "region": "US",
            "source": "fred_extended",
            "symbol": spec["symbol"],
            "frequency": spec["frequency"],
            "unit": spec.get("unit"),
            "csv": rel,
            "tier": "longrun",
            "notes": "FRED 延伸序列，用于与 JST 交叉验证",
        })
        print(f"✓ FRED {spec['id']}: {len(out)} 行, {out['date'].iloc[0]} → {out['date'].iloc[-1]}")
    return exported


def read_simple_csv(rel: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / rel)
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["date", "value"])


def load_series_for_validation(spec: dict[str, Any]) -> pd.Series:
    src = spec["source"]
    if src == "jst":
        path = OUT_DIR / f"jst_{spec['country'].lower()}_{spec['column']}.csv"
        # country file naming uses full country in export - fix
        matches = list(OUT_DIR.glob(f"jst_*_{spec['column']}.csv"))
        for m in matches:
            if spec["country"].lower() in m.stem.lower():
                path = m
                break
        df = read_simple_csv(str(path.relative_to(DATA_DIR)))
    elif src == "fred":
        fred = get_fred()
        s = fred.get_series(spec["symbol"]).dropna()
        df = pd.DataFrame({"date": s.index, "value": s.values})
        df["date"] = pd.to_datetime(df["date"])
    elif src == "csv":
        df = read_simple_csv(spec["path"])
    else:
        raise ValueError(src)
    return df.set_index("date")["value"].sort_index()


def annual_mean(series: pd.Series) -> pd.Series:
    return series.resample("YS").mean()


def run_validation(manifest: dict[str, Any]) -> None:
    VALIDATE_DIR.mkdir(parents=True, exist_ok=True)
    report: list[dict[str, Any]] = []
    for pair in manifest["cross_validation"]:
        try:
            a = load_series_for_validation(pair["a"])
            b = load_series_for_validation(pair["b"])
            method = pair["method"]

            if method == "annual_mean":
                aa = annual_mean(a)
                bb = annual_mean(b)
                merged = pd.concat([aa, bb], axis=1, keys=["a", "b"]).dropna()
            elif method == "monthly_overlap":
                merged = pd.concat([a, b], axis=1, keys=["a", "b"]).dropna()
            elif method == "annual_rebase_1975":
                aa = annual_mean(a)
                bb = annual_mean(b)
                merged = pd.concat([aa, bb], axis=1, keys=["a", "b"]).dropna()
                if not merged.empty:
                    base_year = pd.Timestamp("1975-01-01")
                    if base_year in merged.index:
                        merged["a"] = merged["a"] / merged.loc[base_year, "a"] * 100
                        merged["b"] = merged["b"] / merged.loc[base_year, "b"] * 100
            else:
                raise ValueError(method)

            if merged.empty:
                raise RuntimeError("无重叠区间")

            merged["diff_pct"] = (merged["a"] - merged["b"]) / merged["b"] * 100
            merged = merged.reset_index().rename(columns={"index": "date"})
            merged["date"] = pd.to_datetime(merged["date"]).dt.strftime("%Y-%m-%d")

            out_path = VALIDATE_DIR / f"{pair['id']}.csv"
            merged.to_csv(out_path, index=False, float_format="%.6f")

            corr = merged["a"].corr(merged["b"])
            mae = (merged["a"] - merged["b"]).abs().mean()
            report.append({
                "id": pair["id"],
                "name": pair["name"],
                "method": method,
                "overlap_start": merged["date"].iloc[0],
                "overlap_end": merged["date"].iloc[-1],
                "rows": len(merged),
                "correlation": round(float(corr), 4) if corr == corr else None,
                "mean_abs_diff": round(float(mae), 4),
                "csv": f"csv/validate/{pair['id']}.csv",
            })
            print(f"✓ 交叉验证 {pair['id']}: r={corr:.3f}, n={len(merged)}")
        except Exception as exc:
            report.append({"id": pair["id"], "name": pair["name"], "error": str(exc)})
            print(f"✗ 交叉验证 {pair['id']}: {exc}", file=sys.stderr)

    report_path = DATA_DIR / "validate_report.json"
    report_path.write_text(
        json.dumps({"generated_at": datetime.now().isoformat(timespec="seconds"), "pairs": report},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  → {report_path.relative_to(ROOT)}")


def write_longrun_catalog(entries: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    skip = set()
    rules_path = DATA_DIR / "series_rules.json"
    if rules_path.exists():
        with rules_path.open(encoding="utf-8") as f:
            skip = {d["id"] for d in json.load(f).get("deprecated", [])}
    filtered = [e for e in entries if e["id"] not in skip]
    catalog = {
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sources": manifest["sources"],
        "series": filtered,
    }
    path = DATA_DIR / "manifest_longrun_catalog.json"
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {path.relative_to(ROOT)} ({len(filtered)} 序列, 跳过 {len(entries)-len(filtered)} 条废弃)")


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取百年长周期数据")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest()
    if args.validate_only:
        run_validation(manifest)
        return 0

    raw = ensure_raw(args.skip_download)
    entries: list[dict[str, Any]] = []
    entries += export_jst(raw["jst"], manifest)
    entries += export_jacks(raw["jacks"], manifest)
    entries += export_shiller(raw["shiller"], manifest)
    entries += export_fred_extended(manifest)
    write_longrun_catalog(entries, manifest)
    run_validation(manifest)
    print("-" * 60)
    print(f"完成: {len(entries)} 条长周期序列")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
