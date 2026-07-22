#!/usr/bin/env python3
"""RRG 特征条件统计（预注册假设 H1–H6）。

用法：
  python scripts/backtest_rrg.py
  python scripts/backtest_rrg.py --mode us_gics
  python scripts/backtest_rrg.py --mode cn_sw
  python scripts/backtest_rrg.py --mode all
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WEB_PUBLIC = ROOT / "web" / "public"
OUT_DIR = ROOT / "data" / "rrg_insights"

JDK_MONTHLY = {"window": 12, "roc_period": 3}
HORIZONS = (1, 3, 6)

MODE_FILES = {
    "us_gics": ("rrg_prices_us_gics.json", "us_sp500", "L1"),
    "cn_sw": ("rrg_prices_cn_sw.json", "cn_sw_a", "L1"),
    "country": ("rrg_prices_country.json", "us_sp500", None),
    "cross_asset": ("rrg_prices.json", "us_sp500", None),
}


def ema(values: list[float], span: int) -> list[float]:
    alpha = 2 / (span + 1)
    out: list[float] = []
    prev = values[0]
    for i, v in enumerate(values):
        prev = v if i == 0 else alpha * v + (1 - alpha) * prev
        out.append(prev)
    return out


def rolling_mean_std(values: list[float], window: int, i: int) -> tuple[float, float] | None:
    if i + 1 < window:
        return None
    chunk = values[i - window + 1 : i + 1]
    mean = sum(chunk) / window
    var = sum((x - mean) ** 2 for x in chunk) / (window - 1)
    std = math.sqrt(var)
    if not math.isfinite(std) or std < 1e-12:
        return None
    return mean, std


def rolling_mean_std_nullable(values: list[float | None], window: int, i: int) -> tuple[float, float] | None:
    if i + 1 < window:
        return None
    chunk: list[float] = []
    for j in range(i - window + 1, i + 1):
        v = values[j]
        if v is None:
            return None
        chunk.append(v)
    mean = sum(chunk) / window
    var = sum((x - mean) ** 2 for x in chunk) / (window - 1)
    std = math.sqrt(var)
    if not math.isfinite(std) or std < 1e-12:
        return None
    return mean, std


def resample_monthly(points: list[list]) -> list[tuple[str, float]]:
    buckets: dict[str, tuple[str, float]] = {}
    for date, value in points:
        key = f"{str(date)[:7]}-01"
        buckets[key] = (key, float(value))
    return [buckets[k] for k in sorted(buckets)]


def compute_jdk_rrg(
    asset: list[tuple[str, float]],
    bench: list[tuple[str, float]],
    window: int = 12,
    roc_period: int = 3,
) -> list[dict[str, Any]]:
    bmap = {d: v for d, v in bench}
    aligned: list[tuple[str, float]] = []
    for d, px in asset:
        bx = bmap.get(d)
        if bx is None or bx <= 0 or px <= 0:
            continue
        aligned.append((d, px / bx))
    if len(aligned) < window + roc_period + 5:
        return []

    rs = [x[1] for x in aligned]
    jdk_rs = ema(rs, window)
    rs_ratio: list[float | None] = []
    for i in range(len(jdk_rs)):
        st = rolling_mean_std(jdk_rs, window, i)
        rs_ratio.append(None if st is None else 100 + 10 * ((jdk_rs[i] - st[0]) / st[1]))

    roc: list[float | None] = []
    for i, v in enumerate(rs_ratio):
        if v is None or i < roc_period:
            roc.append(None)
            continue
        prev = rs_ratio[i - roc_period]
        if prev is None or prev == 0:
            roc.append(None)
        else:
            roc.append(v / prev - 1)

    roc_filled: list[float] = []
    roc_index: list[int] = []
    for i, v in enumerate(roc):
        if v is None:
            continue
        roc_filled.append(v)
        roc_index.append(i)
    if len(roc_filled) < window + 2:
        return []

    jdk_roc_smooth = ema(roc_filled, window)
    jdk_roc_full: list[float | None] = [None] * len(aligned)
    for k, idx in enumerate(roc_index):
        jdk_roc_full[idx] = jdk_roc_smooth[k]

    out: list[dict[str, Any]] = []
    for i in range(len(aligned)):
        ratio = rs_ratio[i]
        smoothed = jdk_roc_full[i]
        if ratio is None or smoothed is None:
            continue
        st = rolling_mean_std_nullable(jdk_roc_full, window, i)
        if st is None:
            continue
        mom = 100 + 10 * ((smoothed - st[0]) / st[1])
        if not math.isfinite(ratio) or not math.isfinite(mom):
            continue
        out.append({"date": aligned[i][0], "rs_ratio": ratio, "rs_momentum": mom})
    return out


def quadrant(ratio: float, mom: float) -> str:
    if ratio >= 100 and mom >= 100:
        return "leading"
    if ratio >= 100 and mom < 100:
        return "weakening"
    if ratio < 100 and mom < 100:
        return "lagging"
    return "improving"


def compass_heading(dx: float, dy: float) -> float:
    """数学角 → 罗盘角：0=正上(动量增), 90=正右(强弱增), 顺时针。"""
    # atan2(dx, dy): 0 when pointing up (dy>0), clockwise positive
    ang = math.degrees(math.atan2(dx, dy))
    if ang < 0:
        ang += 360
    return ang


def heading_sector(h: float) -> str:
    if 0 <= h < 90:
        return "NE"  # 0-90 双增
    if 90 <= h < 180:
        return "SE"
    if 180 <= h < 270:
        return "SW"  # 180-270 双减
    return "NW"


def load_mode(mode: str) -> tuple[dict[str, Any], str, str | None]:
    fname, default_bench, level = MODE_FILES[mode]
    path = WEB_PUBLIC / fname
    if not path.exists():
        path = ROOT / "data" / fname
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    benches = {b["id"] for b in data.get("benchmarks", [])}
    if default_bench not in benches and data.get("benchmarks"):
        default_bench = data["benchmarks"][0]["id"]
    return data, default_bench, level


def build_panel(mode: str) -> pd.DataFrame:
    data, bench_id, level = load_mode(mode)
    series_by_id = {s["id"]: s for s in data["series"]}
    if bench_id not in series_by_id:
        raise RuntimeError(f"{mode}: benchmark {bench_id} missing")
    bench_pts = resample_monthly(series_by_id[bench_id]["points"])
    bench_price = {d: v for d, v in bench_pts}

    assets = []
    for s in data["series"]:
        if s["id"] == bench_id:
            continue
        if level and s.get("level") != level:
            continue
        if s.get("level") == "bench" or s["id"] in {b["id"] for b in data.get("benchmarks", [])}:
            if level:  # sector modes: skip bench assets from plottable
                continue
        assets.append(s)

    rows: list[dict[str, Any]] = []
    for s in assets:
        asset_pts = resample_monthly(s["points"])
        price_map = {d: v for d, v in asset_pts}
        rrg = compute_jdk_rrg(asset_pts, bench_pts, **JDK_MONTHLY)
        if len(rrg) < 8:
            continue

        bars_in_q = 1
        for i, p in enumerate(rrg):
            q = quadrant(p["rs_ratio"], p["rs_momentum"])
            prev_q = quadrant(rrg[i - 1]["rs_ratio"], rrg[i - 1]["rs_momentum"]) if i > 0 else q
            if i > 0 and q == prev_q:
                bars_in_q += 1
            else:
                bars_in_q = 1

            heading = np.nan
            velocity = np.nan
            if i > 0:
                dx = p["rs_ratio"] - rrg[i - 1]["rs_ratio"]
                dy = p["rs_momentum"] - rrg[i - 1]["rs_momentum"]
                velocity = math.hypot(dx, dy)
                heading = compass_heading(dx, dy)

            # path length last 3 segments
            path_len = 0.0
            for j in range(max(1, i - 2), i + 1):
                if j <= 0:
                    continue
                path_len += math.hypot(
                    rrg[j]["rs_ratio"] - rrg[j - 1]["rs_ratio"],
                    rrg[j]["rs_momentum"] - rrg[j - 1]["rs_momentum"],
                )

            vel_trend = "na"
            if i >= 3 and math.isfinite(velocity):
                v1 = math.hypot(rrg[i - 2]["rs_ratio"] - rrg[i - 3]["rs_ratio"], rrg[i - 2]["rs_momentum"] - rrg[i - 3]["rs_momentum"])
                v2 = math.hypot(rrg[i - 1]["rs_ratio"] - rrg[i - 2]["rs_ratio"], rrg[i - 1]["rs_momentum"] - rrg[i - 2]["rs_momentum"])
                v3 = velocity
                if v3 > v2 > v1:
                    vel_trend = "accel"
                elif v3 < v2 < v1:
                    vel_trend = "decel"
                else:
                    vel_trend = "stable"

            dist = math.hypot(p["rs_ratio"] - 100, p["rs_momentum"] - 100)
            transition = f"{prev_q}->{q}" if i > 0 else q

            # forward relative returns
            d0 = p["date"]
            px0 = price_map.get(d0)
            bx0 = bench_price.get(d0)
            fwd: dict[str, float] = {}
            for h in HORIZONS:
                if i + h >= len(rrg) or px0 is None or bx0 is None or px0 <= 0 or bx0 <= 0:
                    fwd[f"rel_{h}m"] = np.nan
                    continue
                d1 = rrg[i + h]["date"]
                px1 = price_map.get(d1)
                bx1 = bench_price.get(d1)
                if px1 is None or bx1 is None or px1 <= 0 or bx1 <= 0:
                    fwd[f"rel_{h}m"] = np.nan
                else:
                    fwd[f"rel_{h}m"] = (px1 / px0 - 1) - (bx1 / bx0 - 1)

            # momentum/ratio sustained above 100
            mom_above = sum(1 for k in range(max(0, i - 2), i + 1) if rrg[k]["rs_momentum"] >= 100)
            ratio_above = sum(1 for k in range(max(0, i - 2), i + 1) if rrg[k]["rs_ratio"] >= 100)

            rows.append(
                {
                    "mode": mode,
                    "id": s["id"],
                    "name": s["name"],
                    "date": d0,
                    "rs_ratio": p["rs_ratio"],
                    "rs_momentum": p["rs_momentum"],
                    "quadrant": q,
                    "prev_quadrant": prev_q,
                    "transition": transition,
                    "bars_in_quadrant": bars_in_q,
                    "heading": heading,
                    "heading_sector": heading_sector(heading) if math.isfinite(heading) else "na",
                    "velocity": velocity,
                    "path_len_3": path_len,
                    "vel_trend": vel_trend,
                    "distance": dist,
                    "mom_above_3": mom_above,
                    "ratio_above_3": ratio_above,
                    **fwd,
                }
            )
    return pd.DataFrame(rows)


def summarize(group: pd.Series) -> dict[str, float]:
    x = group.dropna()
    n = len(x)
    if n < 5:
        return {"n": n, "mean": np.nan, "win": np.nan, "t": np.nan}
    mean = float(x.mean())
    win = float((x > 0).mean())
    se = float(x.std(ddof=1) / math.sqrt(n)) if n > 1 else np.nan
    t = mean / se if se and se > 0 else np.nan
    return {"n": n, "mean": mean, "win": win, "t": t}


def run_hypotheses(df: pd.DataFrame, mode: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    base = df.dropna(subset=["heading"]).copy()

    # H1: improving→leading AND heading NE → positive 3m relative
    h1 = base[(base["transition"] == "improving->leading") & (base["heading_sector"] == "NE")]
    for h in HORIZONS:
        s = summarize(h1[f"rel_{h}m"])
        results.append({"mode": mode, "hyp": "H1", "label": "改善→领先 + heading 0-90°", "horizon": f"{h}m", **s})

    # H2: leading + heading SW → negative forward relative
    h2 = base[(base["quadrant"] == "leading") & (base["heading_sector"] == "SW")]
    for h in HORIZONS:
        s = summarize(h2[f"rel_{h}m"])
        results.append({"mode": mode, "hyp": "H2", "label": "领先内 heading 180-270°", "horizon": f"{h}m", **s})

    # H3: NE heading vs SW heading overall
    for sector, tag in [("NE", "H3a"), ("SW", "H3b")]:
        g = base[base["heading_sector"] == sector]
        for h in HORIZONS:
            s = summarize(g[f"rel_{h}m"])
            results.append(
                {
                    "mode": mode,
                    "hyp": tag,
                    "label": f"heading {sector}（{'0-90' if sector=='NE' else '180-270'}）",
                    "horizon": f"{h}m",
                    **s,
                }
            )
    # H3 contrast
    for h in HORIZONS:
        ne = base.loc[base["heading_sector"] == "NE", f"rel_{h}m"].dropna()
        sw = base.loc[base["heading_sector"] == "SW", f"rel_{h}m"].dropna()
        if len(ne) >= 5 and len(sw) >= 5:
            diff = float(ne.mean() - sw.mean())
            # pooled se rough
            se = math.sqrt(ne.var(ddof=1) / len(ne) + sw.var(ddof=1) / len(sw))
            t = diff / se if se > 0 else np.nan
            results.append(
                {
                    "mode": mode,
                    "hyp": "H3",
                    "label": "NE 均值 − SW 均值",
                    "horizon": f"{h}m",
                    "n": len(ne) + len(sw),
                    "mean": diff,
                    "win": float((ne > 0).mean()) - float((sw > 0).mean()),
                    "t": t,
                }
            )

    # H4: top 10% distance → mean reversion (negative subsequent relative if currently leading/outperforming)
    dist_cut = base["distance"].quantile(0.90)
    far = base[base["distance"] >= dist_cut]
    for h in HORIZONS:
        # if currently outperforming (ratio>100), expect negative rel; if underperforming expect positive
        far_out = far[far["rs_ratio"] >= 100]
        far_under = far[far["rs_ratio"] < 100]
        s_out = summarize(far_out[f"rel_{h}m"])
        s_und = summarize(far_under[f"rel_{h}m"])
        results.append({"mode": mode, "hyp": "H4a", "label": f"远距且强(Ratio≥100)→应回落", "horizon": f"{h}m", **s_out})
        results.append({"mode": mode, "hyp": "H4b", "label": f"远距且弱(Ratio<100)→应反弹", "horizon": f"{h}m", **s_und})

    # H5: long path (top 20%) vs short path (bottom 20%) — continuation vs stability
    pl = base["path_len_3"].dropna()
    if len(pl) > 50:
        hi = base[base["path_len_3"] >= pl.quantile(0.80)]
        lo = base[base["path_len_3"] <= pl.quantile(0.20)]
        for h in HORIZONS:
            # absolute magnitude of subsequent move (volatility proxy) + signed relative
            results.append({"mode": mode, "hyp": "H5a", "label": "长尾(高速度)后续超额", "horizon": f"{h}m", **summarize(hi[f"rel_{h}m"])})
            results.append({"mode": mode, "hyp": "H5b", "label": "短尾(低速度)后续超额", "horizon": f"{h}m", **summarize(lo[f"rel_{h}m"])})
            results.append(
                {
                    "mode": mode,
                    "hyp": "H5c",
                    "label": "长尾|超额| − 短尾|超额|（波动差）",
                    "horizon": f"{h}m",
                    "n": int(hi[f"rel_{h}m"].notna().sum() + lo[f"rel_{h}m"].notna().sum()),
                    "mean": float(hi[f"rel_{h}m"].abs().mean() - lo[f"rel_{h}m"].abs().mean()),
                    "win": np.nan,
                    "t": np.nan,
                }
            )

    # H6: momentum sustained above 100 leads ratio above 100
    # At each point where mom_above_3==3 and ratio still <100, does ratio cross above within 3m?
    lead_cases = base[(base["mom_above_3"] == 3) & (base["rs_ratio"] < 100)].copy()
    crossed = []
    for _, row in lead_cases.iterrows():
        # look ahead in same id
        sub = base[(base["id"] == row["id"]) & (base["date"] > row["date"])].head(3)
        crossed.append(1.0 if (sub["rs_ratio"] >= 100).any() else 0.0)
    if crossed:
        arr = np.array(crossed)
        results.append(
            {
                "mode": mode,
                "hyp": "H6",
                "label": "动量持续>100 且 Ratio<100 → 3期内 Ratio 上穿100",
                "horizon": "3m",
                "n": len(arr),
                "mean": float(arr.mean()),
                "win": float(arr.mean()),
                "t": np.nan,
            }
        )
        # baseline: random lagging/improving with mom not sustained
        base_cases = base[(base["mom_above_3"] < 2) & (base["rs_ratio"] < 100)]
        base_cross = []
        sample = base_cases.sample(n=min(len(base_cases), max(len(arr) * 3, 100)), random_state=42) if len(base_cases) else base_cases
        for _, row in sample.iterrows():
            sub = base[(base["id"] == row["id"]) & (base["date"] > row["date"])].head(3)
            base_cross.append(1.0 if (sub["rs_ratio"] >= 100).any() else 0.0)
        if base_cross:
            b = np.array(base_cross)
            results.append(
                {
                    "mode": mode,
                    "hyp": "H6b",
                    "label": "对照：动量未持续且 Ratio<100 → 3期内上穿",
                    "horizon": "3m",
                    "n": len(b),
                    "mean": float(b.mean()),
                    "win": float(b.mean()),
                    "t": np.nan,
                }
            )

    return results


def verdict_row(r: dict[str, Any]) -> str:
    hyp = r["hyp"]
    mean = r.get("mean")
    t = r.get("t")
    n = r.get("n", 0)
    if n is None or n < 30 or mean is None or (isinstance(mean, float) and math.isnan(mean)):
        return "不足"
    # expected signs
    expect_pos = hyp in {"H1", "H3a", "H3", "H4b", "H6"}
    expect_neg = hyp in {"H2", "H3b", "H4a"}
    if hyp.startswith("H5"):
        if hyp == "H5c":
            return "支持" if mean > 0 else "不支持"
        return "描述"
    ok = False
    if expect_pos:
        ok = mean > 0 and (not math.isfinite(t) or t > 1.5)
    elif expect_neg:
        ok = mean < 0 and (not math.isfinite(t) or t < -1.5)
    else:
        return "描述"
    if ok and abs(t) >= 2.0 if math.isfinite(t) else ok:
        return "强支持"
    if ok:
        return "弱支持"
    return "不支持"


def print_table(results: list[dict[str, Any]]) -> None:
    print(f"\n{'模式':<12} {'假设':<5} {'展望':<4} {'n':>6} {'均值超额':>10} {'胜率':>7} {'t':>7} {'判定':<6} 说明")
    print("-" * 110)
    for r in results:
        mean = r.get("mean")
        win = r.get("win")
        t = r.get("t")
        mean_s = f"{mean*100:.2f}%" if mean is not None and math.isfinite(mean) else "—"
        win_s = f"{win*100:.1f}%" if win is not None and math.isfinite(win) else "—"
        t_s = f"{t:.2f}" if t is not None and math.isfinite(t) else "—"
        v = verdict_row(r)
        print(
            f"{r['mode']:<12} {r['hyp']:<5} {r['horizon']:<4} {int(r['n']):>6} {mean_s:>10} {win_s:>7} {t_s:>7} {v:<6} {r['label']}"
        )


def export_insight_rules(all_results: list[dict[str, Any]]) -> dict[str, Any]:
    """根据判定生成前端可用的规则权重。"""
    # Aggregate by hyp across horizons preferring 3m
    by_key: dict[tuple[str, str], dict] = {}
    for r in all_results:
        if r["horizon"] not in {"3m", "1m"} and r["hyp"] not in {"H6", "H6b"}:
            continue
        key = (r["mode"], r["hyp"])
        # prefer 3m
        if key in by_key and by_key[key]["horizon"] == "3m" and r["horizon"] != "3m":
            continue
        by_key[key] = r

    mode_rules: dict[str, Any] = {}
    for (mode, hyp), r in by_key.items():
        v = verdict_row(r)
        mode_rules.setdefault(mode, {})[hyp] = {
            "verdict": v,
            "mean": None if r.get("mean") is None or (isinstance(r["mean"], float) and math.isnan(r["mean"])) else round(float(r["mean"]), 5),
            "win": None if r.get("win") is None or (isinstance(r["win"], float) and math.isnan(r["win"])) else round(float(r["win"]), 4),
            "t": None if r.get("t") is None or (isinstance(r["t"], float) and math.isnan(r["t"])) else round(float(r["t"]), 3),
            "n": int(r["n"]),
            "label": r["label"],
            "horizon": r["horizon"],
        }

    # Global feature confidence for narrative
    feature_confidence = {
        "heading_NE": "medium",
        "heading_SW": "medium",
        "transition_improving_leading": "medium",
        "distance_extreme": "low",
        "velocity_path": "low",
        "momentum_leads_ratio": "medium",
    }
    # upgrade if strongly supported in both main modes
    for feat, hyps in [
        ("heading_NE", ["H3a", "H3"]),
        ("heading_SW", ["H3b"]),
        ("transition_improving_leading", ["H1"]),
        ("distance_extreme", ["H4a", "H4b"]),
        ("velocity_path", ["H5c"]),
        ("momentum_leads_ratio", ["H6"]),
    ]:
        scores = []
        for mode in ("us_gics", "cn_sw"):
            for h in hyps:
                cell = mode_rules.get(mode, {}).get(h)
                if not cell:
                    continue
                if cell["verdict"] == "强支持":
                    scores.append(2)
                elif cell["verdict"] == "弱支持":
                    scores.append(1)
                elif cell["verdict"] == "不支持":
                    scores.append(-1)
        if scores:
            avg = sum(scores) / len(scores)
            if avg >= 1.5:
                feature_confidence[feat] = "high"
            elif avg >= 0.5:
                feature_confidence[feat] = "medium"
            elif avg < 0:
                feature_confidence[feat] = "low"
            else:
                feature_confidence[feat] = "medium"

    return {
        "generated_note": "Pre-registered H1–H6 monthly L1 tests; relative excess vs benchmark.",
        "jdk": JDK_MONTHLY,
        "mode_rules": mode_rules,
        "feature_confidence": feature_confidence,
        "narrative_policy": {
            "use_heading": feature_confidence["heading_NE"] in {"high", "medium"}
            or feature_confidence["heading_SW"] in {"high", "medium"},
            "use_transition_il": feature_confidence["transition_improving_leading"] in {"high", "medium"},
            "use_distance": feature_confidence["distance_extreme"] == "high",
            "use_velocity": feature_confidence["velocity_path"] == "high",
            "use_mom_lead": feature_confidence["momentum_leads_ratio"] in {"high", "medium"},
            "tone": "relative_allocation_only",
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="all", choices=["us_gics", "cn_sw", "country", "cross_asset", "all"])
    args = ap.parse_args()
    modes = list(MODE_FILES.keys()) if args.mode == "all" else [args.mode]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_results: list[dict[str, Any]] = []
    for mode in modes:
        print(f"\n=== Building panel: {mode} ===")
        try:
            df = build_panel(mode)
        except Exception as e:
            print(f"SKIP {mode}: {e}")
            continue
        print(f"rows={len(df)} assets={df['id'].nunique()} dates={df['date'].nunique()}")
        df.to_csv(OUT_DIR / f"panel_{mode}.csv", index=False)
        res = run_hypotheses(df, mode)
        all_results.extend(res)
        print_table(res)

    if not all_results:
        print("No results.")
        sys.exit(1)

    res_df = pd.DataFrame(all_results)
    res_df.to_csv(OUT_DIR / "hypothesis_results.csv", index=False)
    rules = export_insight_rules(all_results)
    with (OUT_DIR / "insight_rules.json").open("w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    # copy to web public for frontend optional load
    pub = WEB_PUBLIC / "rrg_insight_rules.json"
    with pub.open("w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {OUT_DIR / 'hypothesis_results.csv'}")
    print(f"Wrote {OUT_DIR / 'insight_rules.json'} and {pub}")
    print("\nFeature confidence:", json.dumps(rules["feature_confidence"], ensure_ascii=False))
    print("Narrative policy:", json.dumps(rules["narrative_policy"], ensure_ascii=False))


if __name__ == "__main__":
    main()
