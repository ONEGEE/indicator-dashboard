#!/usr/bin/env python3
"""将指数 / 宏观 / 资产 manifests 归纳为中金大类资产配置 catalog。

输出：
  - data/catalog.json
  - web/public/catalog.json（供网站读取）
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.data_lib import deprecated_ids, load_rules  # noqa: E402
DATA_DIR = ROOT / "data"
WEB_PUBLIC = ROOT / "web" / "public"

PILLARS = [
    {
        "id": "equity",
        "name": "股票",
        "name_en": "Equity",
        "role": "承载增长",
        "description": "全球主要股指。中金观点：美股长期质量突出，但并非任何十年都最优；需跟踪非美市场边际变化。",
    },
    {
        "id": "bond",
        "name": "债券",
        "name_en": "Bond",
        "role": "平滑波动",
        "description": "国债收益率与债券ETF。中金观点：债券并非无条件安全，核心价值在于与股票的动态对冲。",
    },
    {
        "id": "real_estate",
        "name": "地产",
        "name_en": "Real Estate",
        "role": "稳定回报与分散",
        "description": "房价指数与地产相关宏观。中金观点：百年尺度上地产风险收益接近股票，不宜仅因老龄化线性外推。",
    },
    {
        "id": "commodity",
        "name": "商品",
        "name_en": "Commodity",
        "role": "通胀与供给冲击对冲",
        "description": "综合商品与能源/工业金属。中金观点：长期回报接近通胀，价值在于周期窗口中的对冲而非被动持有。",
    },
    {
        "id": "precious_metal",
        "name": "贵金属",
        "name_en": "Precious Metal",
        "role": "货币信用与极端风险对冲",
        "description": "黄金等贵金属。中金观点：法币时代有长期回报，但非线性释放，既不宜矮化也不宜神化。",
    },
    {
        "id": "macro",
        "name": "宏观",
        "name_en": "Macro",
        "role": "定价环境",
        "description": "CPI、利率、增长、就业等宏观变量，用于解释大类资产轮动的宏观情境。",
    },
]

# 将既有序列映射到中金五类 + 宏观


def infer_pillar(item: dict[str, Any], origin: str) -> str:
    if item.get("pillar"):
        return item["pillar"]
    subcategory = item.get("subcategory", "")
    category = item.get("category", "")
    series_id = item.get("id", "")

    if origin == "index" or category == "index":
        return "equity"
    if category in {"bond", "commodity", "precious_metal"}:
        return category
    if subcategory == "housing" or series_id.startswith(("us_case", "us_fhfa", "us_housing", "us_building", "us_new_home", "us_months", "us_median_home", "us_avg_home", "cn_house", "cn_lpr", "us_mortgage")):
        return "real_estate"
    if subcategory in {"prices", "labor", "growth", "money", "rates"} or origin == "macro":
        # 利率类宏观也可挂 bond，但 catalog 里单独放 macro 更清晰
        if series_id in {"us_fed_funds", "us_treasury_10y", "us_yield_curve_10y2y", "us_mortgage_30y"}:
            # mortgage already housing; fed/treasury stay macro for environment
            if series_id == "us_mortgage_30y":
                return "real_estate"
        return "macro"
    return "macro"


def scan_csv(rel_csv: str) -> dict[str, Any]:
    path = DATA_DIR / rel_csv
    stats: dict[str, Any] = {
        "exists": path.exists(),
        "rows": 0,
        "start": None,
        "end": None,
        "last_value": None,
        "value_field": None,
        "schema": None,
    }
    if not path.exists():
        return stats
    df = pd.read_csv(path)
    stats["rows"] = len(df)
    if df.empty or "date" not in df.columns:
        return stats
    stats["start"] = str(df["date"].iloc[0])
    stats["end"] = str(df["date"].iloc[-1])
    stats["schema"] = list(df.columns)

    for field in ["close", "value", "lpr_5y", "new_yoy"]:
        if field in df.columns:
            val = pd.to_numeric(df[field], errors="coerce").dropna()
            if not val.empty:
                stats["value_field"] = field
                stats["last_value"] = float(val.iloc[-1])
                break
    return stats


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def normalize_item(item: dict[str, Any], origin: str) -> dict[str, Any]:
    pillar = item.get("pillar") or infer_pillar(item, origin)
    stats = scan_csv(item["csv"])
    return {
        "id": item["id"],
        "name": item["name"],
        "name_en": item.get("name_en"),
        "pillar": pillar,
        "origin": origin,
        "tier": item.get("tier", "market"),
        "category": item.get("category"),
        "subcategory": item.get("subcategory"),
        "region": item.get("region"),
        "source": item.get("source"),
        "symbol": item.get("symbol"),
        "frequency": item.get("frequency"),
        "unit": item.get("unit"),
        "csv": item["csv"],
        "notes": item.get("notes"),
        "stats": stats,
    }


def build_catalog() -> dict[str, Any]:
    index_m = load_json(DATA_DIR / "manifest.json")
    macro_m = load_json(DATA_DIR / "manifest_macro.json")
    asset_m = load_json(DATA_DIR / "manifest_assets.json")

    series = []
    series += [normalize_item(s, "index") for s in index_m["series"]]
    series += [normalize_item(s, "macro") for s in macro_m["series"]]
    series += [normalize_item(s, "asset") for s in asset_m["series"]]

    stitched_path = DATA_DIR / "manifest_stitched.json"
    if stitched_path.exists():
        stitched_m = load_json(stitched_path)
        series += [normalize_item(s, "stitched") for s in stitched_m.get("series", [])]

    skip = deprecated_ids()
    longrun_catalog = DATA_DIR / "manifest_longrun_catalog.json"
    longrun_sources = {}
    if longrun_catalog.exists():
        lr = load_json(longrun_catalog)
        longrun_sources = lr.get("sources", {})
        for s in lr.get("series", []):
            if s["id"] in skip:
                continue
            series.append(normalize_item(s, "longrun"))

    validate_report = DATA_DIR / "validate_report.json"
    validation = load_json(validate_report) if validate_report.exists() else None
    rules = load_rules()

    by_pillar: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    for s in series:
        by_pillar[s["pillar"]] = by_pillar.get(s["pillar"], 0) + 1
        by_tier[s.get("tier", "market")] = by_tier.get(s.get("tier", "market"), 0) + 1

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "framework": {
            "title": "全球大类资产配置数据台",
            "reference": "中金《资产配置手册：全球资产100年》",
            "reference_url": "https://caifuhao.eastmoney.com/news/20260508081446026335040",
            "summary": "以权益承载增长，以债券平滑波动，以地产、商品及黄金对冲宏观与地缘风险，并根据市场形势动态调整配置权重。",
            "pillars": PILLARS,
            "longrun_sources": longrun_sources,
        },
        "validation": validation,
        "series_rules": {
            "deprecated": rules.get("deprecated", []),
            "stitched": rules.get("stitched", []),
            "kept_overlap_notes": rules.get("kept_overlap_notes", []),
        },
        "counts": {
            "total": len(series),
            "with_data": sum(1 for s in series if s["stats"]["exists"] and s["stats"]["rows"] > 0),
            "by_pillar": by_pillar,
            "by_tier": by_tier,
        },
        "series": series,
    }


def main() -> None:
    catalog = build_catalog()
    out = DATA_DIR / "catalog.json"
    out.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    WEB_PUBLIC.mkdir(parents=True, exist_ok=True)
    (WEB_PUBLIC / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"✓ catalog: {catalog['counts']['total']} 序列, {catalog['counts']['with_data']} 已有数据")
    print(f"  → {out.relative_to(ROOT)}")
    print(f"  → web/public/catalog.json")
    for pid, n in catalog["counts"]["by_pillar"].items():
        print(f"    {pid}: {n}")
    if catalog["counts"].get("by_tier"):
        print("  tier:", catalog["counts"]["by_tier"])


if __name__ == "__main__":
    main()
