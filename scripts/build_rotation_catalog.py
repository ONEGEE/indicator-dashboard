#!/usr/bin/env python3
"""生成轮动层 catalog：资产 × 回报 + 市值 + 指标说明。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
WEB_PUBLIC = ROOT / "web" / "public"

UPDATE_RULE_HINTS = {
    "monthly_nbs": "国家统计局月度数据通常于次月中旬发布，预计下次更新约在数据截止月次月15日前后",
    "monthly_market": "行情类月度序列可随时刷新；惯例按每月最后一个交易日后更新",
    "quarterly_fred": "美联储季度账户约滞后一个季度；月度序列由季度值前向填充",
    "annual_worldbank": "世界银行年度指标滞后约1–2年，年内用价格指数外推",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def scan_return(rel: str) -> dict[str, Any]:
    path = DATA_DIR / rel
    stats: dict[str, Any] = {"exists": path.exists(), "rows": 0, "start": None, "end": None}
    if not path.exists():
        return stats
    df = pd.read_csv(path)
    stats["rows"] = len(df)
    if not df.empty and "date" in df.columns:
        stats["start"] = str(df["date"].iloc[0])
        stats["end"] = str(df["date"].iloc[-1])
        if "value" in df.columns:
            val = pd.to_numeric(df["value"], errors="coerce").dropna()
            if not val.empty:
                stats["last_value"] = float(val.iloc[-1])
    return stats


def scan_marketcap(rel: str | None) -> dict[str, Any]:
    if not rel:
        return {"exists": False, "applicable": False}
    path = DATA_DIR / rel
    stats: dict[str, Any] = {"exists": path.exists(), "applicable": True, "rows": 0}
    if not path.exists():
        return stats
    df = pd.read_csv(path)
    stats["rows"] = len(df)
    if not df.empty:
        stats["start"] = str(df["date"].iloc[0])
        stats["end"] = str(df["date"].iloc[-1])
        if "value_usd" in df.columns:
            val = pd.to_numeric(df["value_usd"], errors="coerce").dropna()
            if not val.empty:
                stats["last_value_usd"] = float(val.iloc[-1])
    return stats


def compute_next_update(last_date: str | None, update_rule: str | None) -> str | None:
    if not last_date:
        return None
    try:
        dt = pd.Timestamp(last_date)
    except Exception:
        return None
    rule = update_rule or "monthly_market"
    if rule == "monthly_nbs":
        nxt = (dt + pd.offsets.MonthBegin(2)).replace(day=15)
        return nxt.strftime("%Y-%m-%d")
    if rule == "quarterly_fred":
        nxt = dt + pd.offsets.QuarterEnd(2)
        return nxt.strftime("%Y-%m-%d")
    if rule == "annual_worldbank":
        nxt = pd.Timestamp(year=dt.year + 1, month=12, day=31)
        return nxt.strftime("%Y-%m-%d")
    nxt = dt + pd.offsets.MonthBegin(2)
    return nxt.strftime("%Y-%m-%d")


def enrich_documentation(
    doc: dict[str, Any] | None,
    ret_stats: dict[str, Any],
    mc_stats: dict[str, Any],
    update_policy: dict[str, str],
    generated_at: str,
) -> dict[str, Any]:
    base = dict(doc or {})
    last_data = mc_stats.get("end") or ret_stats.get("end")
    rule = base.get("update_rule")
    base["last_data_date"] = last_data
    base["last_updated"] = generated_at
    base["expected_next_update"] = compute_next_update(last_data, rule)
    if rule and rule in update_policy:
        base["update_schedule"] = update_policy[rule]
    elif rule and rule in UPDATE_RULE_HINTS:
        base["update_schedule"] = UPDATE_RULE_HINTS[rule]
    return base


def build() -> dict[str, Any]:
    manifest = load_json(DATA_DIR / "manifest_rotation.json")
    validate_path = DATA_DIR / "rotation_validate_report.json"
    validation = load_json(validate_path) if validate_path.exists() else None
    generated_at = datetime.now().isoformat(timespec="seconds")
    update_policy = manifest.get("update_policy") or UPDATE_RULE_HINTS

    assets = []
    by_pillar: dict[str, int] = {}
    with_marketcap = 0

    for item in manifest["assets"]:
        mc = item.get("marketcap") or {}
        ret_stats = scan_return(item["return"]["csv"])
        mc_stats = scan_marketcap(mc.get("csv"))
        if mc_stats.get("exists") and mc_stats.get("rows", 0) > 0:
            with_marketcap += 1
        pillar = item["pillar"]
        by_pillar[pillar] = by_pillar.get(pillar, 0) + 1
        documentation = enrich_documentation(
            item.get("documentation"),
            ret_stats,
            mc_stats,
            update_policy,
            generated_at,
        )
        assets.append(
            {
                "id": item["id"],
                "name": item["name"],
                "name_en": item.get("name_en"),
                "pillar": pillar,
                "region": item.get("region"),
                "return": {
                    "csv": item["return"]["csv"],
                    "source": item["return"]["source"],
                    "symbol": item["return"].get("symbol"),
                    "frequency": "monthly",
                    "notes": item["return"].get("notes"),
                    "stats": ret_stats,
                },
                "marketcap": {
                    "csv": mc.get("csv"),
                    "method": mc.get("method"),
                    "unit": mc.get("unit"),
                    "authority": mc.get("authority"),
                    "notes": mc.get("notes"),
                    "stats": mc_stats,
                },
                "documentation": documentation,
            }
        )

    return {
        "generated_at": generated_at,
        "layer": "rotation",
        "description": "全球资产轮动：月度回报 + 市值/存量（含指标说明）",
        "validation": validation,
        "counts": {
            "total": len(assets),
            "with_return_data": sum(1 for a in assets if a["return"]["stats"].get("rows", 0) > 0),
            "with_marketcap_data": with_marketcap,
            "by_pillar": by_pillar,
        },
        "assets": assets,
    }


def last_complete_month_start(today: pd.Timestamp | None = None) -> pd.Timestamp:
    """展示截止到上一完整自然月（隐藏仍在进行中的当月）。"""
    today = (today or pd.Timestamp.today()).normalize()
    return today.replace(day=1) - pd.offsets.MonthBegin(1)


def export_marketcap_web(assets: list[dict[str, Any]]) -> dict[str, Any]:
    """导出前端规模占比页：月度占比面板 + 各资产序列（不含未完成当月）。"""
    pillar_labels = {
        "equity": "股票",
        "bond": "债券",
        "precious_metal": "贵金属",
        "commodity": "商品",
        "crypto": "加密",
        "fx": "外汇",
        "real_estate": "地产",
    }
    display_end = last_complete_month_start()
    series_meta: list[dict[str, Any]] = []
    frames: dict[str, pd.Series] = {}

    for asset in assets:
        mc = asset.get("marketcap") or {}
        rel = mc.get("csv")
        if not rel or mc.get("method") in (None, "na"):
            continue
        path = DATA_DIR / rel
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if df.empty or "value_usd" not in df.columns:
            continue
        df["date"] = pd.to_datetime(df["date"])
        df["value_usd"] = pd.to_numeric(df["value_usd"], errors="coerce")
        df = df.dropna(subset=["date", "value_usd"]).sort_values("date")
        df["date"] = df["date"].dt.to_period("M").dt.to_timestamp()
        df = df[df["date"] <= display_end]
        if df.empty:
            continue
        s = df.drop_duplicates("date", keep="last").set_index("date")["value_usd"].astype(float)
        frames[asset["id"]] = s
        doc = asset.get("documentation") or {}
        points = [[d.strftime("%Y-%m-%d"), float(v)] for d, v in s.items()]
        series_meta.append(
            {
                "id": asset["id"],
                "name": asset["name"],
                "pillar": asset["pillar"],
                "pillar_label": pillar_labels.get(asset["pillar"], asset["pillar"]),
                "method": mc.get("method"),
                "authority": mc.get("authority"),
                "unit": mc.get("unit"),
                "documentation": doc,
                "points": points,
            }
        )

    if not frames:
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "display_end": display_end.strftime("%Y-%m-%d"),
            "counts": {"with_marketcap": 0, "total_usd_latest": 0, "share_months": 0},
            "series": [],
            "latest": [],
            "share_panel": {"ids": [], "meta": {}, "dates": [], "totals": [], "values": [], "shares": []},
        }

    ids = [m["id"] for m in series_meta]
    panel = pd.DataFrame(frames).sort_index().reindex(columns=ids)
    totals = panel.sum(axis=1, min_count=1)
    shares = panel.div(totals, axis=0)

    dates = [d.strftime("%Y-%m-%d") for d in panel.index]
    values_rows = [
        [None if pd.isna(v) else float(v) for v in panel.iloc[i].tolist()] for i in range(len(panel))
    ]

    csv_dir = DATA_DIR / "csv" / "rotation"
    csv_dir.mkdir(parents=True, exist_ok=True)
    wide = panel.copy()
    wide.insert(0, "total_usd", totals)
    for col in ids:
        wide[f"{col}_share"] = shares[col]
    wide.index = pd.to_datetime(wide.index)
    wide.index.name = "date"
    wide = wide.reset_index()
    wide["date"] = wide["date"].dt.strftime("%Y-%m-%d")
    wide_path = csv_dir / "marketcap_share_panel.csv"
    wide.to_csv(wide_path, index=False, float_format="%.6f")

    last_idx = len(dates) - 1
    last_total = float(totals.iloc[last_idx]) if last_idx >= 0 and pd.notna(totals.iloc[last_idx]) else 0.0
    latest_items: list[dict[str, Any]] = []
    for j, meta in enumerate(series_meta):
        v = values_rows[last_idx][j] if last_idx >= 0 else None
        if v is None:
            continue
        latest_items.append(
            {
                "id": meta["id"],
                "name": meta["name"],
                "pillar": meta["pillar"],
                "pillar_label": meta["pillar_label"],
                "date": dates[last_idx],
                "value_usd": v,
                "share": (v / last_total) if last_total > 0 else 0.0,
            }
        )
    latest_items.sort(key=lambda x: x["value_usd"], reverse=True)

    id_meta = {
        m["id"]: {
            "name": m["name"],
            "pillar": m["pillar"],
            "pillar_label": m["pillar_label"],
            "authority": m.get("authority"),
            "method": m.get("method"),
        }
        for m in series_meta
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "display_end": display_end.strftime("%Y-%m-%d"),
        "counts": {
            "with_marketcap": len(series_meta),
            "total_usd_latest": last_total,
            "share_months": len(dates),
        },
        "series": series_meta,
        "latest": latest_items,
        "share_panel": {
            "ids": ids,
            "meta": id_meta,
            "dates": dates,
            "totals": [None if pd.isna(t) else round(float(t), 2) for t in totals.tolist()],
            # 仅存规模；占比由前端按所选样本重算，避免重复与体积膨胀
            "values": [
                [None if v is None else round(v, 2) for v in row] for row in values_rows
            ],
            "csv": "csv/rotation/marketcap_share_panel.csv",
        },
    }


def main() -> None:
    catalog = build()
    out = DATA_DIR / "rotation_catalog.json"
    out.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    WEB_PUBLIC.mkdir(parents=True, exist_ok=True)
    (WEB_PUBLIC / "rotation_catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    mc_web = export_marketcap_web(catalog["assets"])
    mc_out = DATA_DIR / "rotation_marketcap.json"
    # 数据目录保留缩进；前端 public 用紧凑 JSON 加快加载
    mc_out.write_text(json.dumps(mc_web, ensure_ascii=False, indent=2), encoding="utf-8")
    (WEB_PUBLIC / "rotation_marketcap.json").write_text(
        json.dumps(mc_web, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    c = catalog["counts"]
    print(f"✓ rotation catalog: {c['total']} 项, 回报 {c['with_return_data']}, 市值 {c['with_marketcap_data']}")
    print(f"  → {out.relative_to(ROOT)}")
    print(
        f"✓ rotation marketcap web: {mc_web['counts']['with_marketcap']} 项, "
        f"占比月数 {mc_web['counts'].get('share_months', 0)}, "
        f"展示截止 {mc_web.get('display_end')}"
    )
    print(f"  → {mc_out.relative_to(ROOT)}")
    print(f"  → web/public/rotation_marketcap.json")
    print(f"  → data/csv/rotation/marketcap_share_panel.csv")


if __name__ == "__main__":
    main()
