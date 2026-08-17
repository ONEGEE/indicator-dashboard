#!/usr/bin/env python3
"""RRG 右多策略：庙旺得利参数网格回测（月度行业 L1）。

用法：
  python scripts/backtest_rrg_right_long.py
  python scripts/backtest_rrg_right_long.py --mode us_gics
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "rrg_insights"
PANEL = {
    "us_gics": OUT_DIR / "panel_us_gics.csv",
    "cn_sw": OUT_DIR / "panel_cn_sw.csv",
}
HORIZONS = (1, 3, 6)


@dataclass(frozen=True)
class Params:
    li_mom_months: int  # consecutive mom>=100
    li_mom_min_in_window: int | None  # if set, use max(li_mom_months) window with at least this many
    de_hold_months: int  # months ratio stays >=100 after cross
    wang_dist_pct: float  # distance percentile threshold (within mode cross-section that month)
    wang_ratio_min: float  # or ratio >= this
    miao_leading_months: int  # bars_in_quadrant leading with ratio>=100
    review_cap_months: int = 12

    def key(self) -> str:
        w = f"win{self.li_mom_min_in_window}" if self.li_mom_min_in_window else "consec"
        return (
            f"li{self.li_mom_months}{w}_de{self.de_hold_months}_"
            f"wang{int(self.wang_dist_pct*100)}r{self.wang_ratio_min}_miao{self.miao_leading_months}"
        )


def mom_streak(row: pd.Series, months: int, min_in_window: int | None) -> bool:
    if min_in_window is not None:
        # use mom_above_3 field only when months==3; generalize from panel columns
        if months == 3 and min_in_window == 2:
            return row.get("mom_above_3", 0) >= 2
        if months == 3 and min_in_window == 3:
            return row.get("mom_above_3", 0) >= 3
        # for months==2 approximate via mom_above_3>=2 when only 3-col exists
        if months == 2:
            return row.get("mom_above_3", 0) >= 2
        return row.get("mom_above_3", 0) >= months
    if months == 2:
        return row.get("mom_above_3", 0) >= 2  # panel only has 3-window counter
    return row.get("mom_above_3", 0) >= months


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["id", "date"]).copy()
    g = df.groupby("id")
    df["prev_ratio"] = g["rs_ratio"].shift(1)
    df["prev_mom"] = g["rs_momentum"].shift(1)
    # distance percentile within mode+date
    df["dist_pct"] = df.groupby("date")["distance"].rank(pct=True)
    return df


def detect_li(df: pd.DataFrame, p: Params) -> pd.Series:
    base = df["rs_ratio"] < 100
    mom_ok = df.apply(
        lambda r: mom_streak(r, p.li_mom_months, p.li_mom_min_in_window),
        axis=1,
    )
    return base & mom_ok


def detect_de(df: pd.DataFrame, p: Params) -> pd.Series:
    """Ratio cross up then hold H months: mark at first month of hold completion."""
    out = pd.Series(False, index=df.index)
    for _id, sub in df.groupby("id"):
        ratios = sub["rs_ratio"].values
        moms = sub["rs_momentum"].values
        idx = sub.index.tolist()
        cross_i = None
        for i in range(1, len(sub)):
            if ratios[i - 1] < 100 <= ratios[i] and moms[i] >= 100:
                cross_i = i
                break
        if cross_i is None:
            continue
        hold = p.de_hold_months
        end = cross_i + hold - 1
        if end < len(sub):
            ok = all(ratios[j] >= 100 for j in range(cross_i, end + 1))
            if ok and moms[end] >= 100:
                out.loc[idx[end]] = True
    return out


def detect_de_all(df: pd.DataFrame, p: Params) -> pd.Series:
    """Every de event (each cross+hold), not just first in series."""
    out = pd.Series(False, index=df.index)
    for _id, sub in df.groupby("id"):
        ratios = sub["rs_ratio"].values
        moms = sub["rs_momentum"].values
        idx = sub.index.tolist()
        i = 1
        while i < len(sub):
            if ratios[i - 1] < 100 <= ratios[i] and moms[i] >= 100:
                end = i + p.de_hold_months - 1
                if end < len(sub):
                    ok = all(ratios[j] >= 100 for j in range(i, end + 1))
                    if ok and moms[end] >= 100:
                        out.loc[idx[end]] = True
                        i = end + 1
                        continue
            i += 1
    return out


def detect_wang(df: pd.DataFrame, p: Params, de_mask: pd.Series) -> pd.Series:
    cond = (
        (df["rs_ratio"] >= 100)
        & (df["rs_momentum"] >= 100)
        & de_mask.cummax()  # had de before or at this point per id — approximate below
    )
    strength = (df["dist_pct"] >= p.wang_dist_pct) | (df["rs_ratio"] >= p.wang_ratio_min)
    out = cond & strength
    # per-id: only after first de
    final = pd.Series(False, index=df.index)
    for _id, sub in df.groupby("id"):
        de_dates = sub.index[de_mask.loc[sub.index]]
        if len(de_dates) == 0:
            continue
        first_de = de_dates[0]
        mask = out.loc[sub.index] & (sub.index >= first_de)
        final.loc[mask.index[mask]] = True
    return final


def detect_miao(df: pd.DataFrame, p: Params, wang_mask: pd.Series) -> pd.Series:
    base = (
        (df["quadrant"] == "leading")
        & (df["rs_ratio"] >= 100)
        & (df["bars_in_quadrant"] >= p.miao_leading_months)
        & (df["ratio_above_3"] >= 3)
    )
    final = pd.Series(False, index=df.index)
    for _id, sub in df.groupby("id"):
        w_idx = sub.index[wang_mask.loc[sub.index]]
        if len(w_idx) == 0:
            continue
        first_w = w_idx[0]
        m = base.loc[sub.index] & (sub.index >= first_w)
        final.loc[m.index[m]] = True
    return final


def summarize_events(df: pd.DataFrame, mask: pd.Series, label: str) -> dict[str, Any]:
    sub = df[mask]
    row: dict[str, Any] = {"stage": label, "n": int(mask.sum()), "assets": int(sub["id"].nunique()) if len(sub) else 0}
    for h in HORIZONS:
        col = f"rel_{h}m"
        x = sub[col].dropna()
        row[f"n_{h}m"] = int(len(x))
        row[f"mean_{h}m"] = float(x.mean()) if len(x) else math.nan
        row[f"win_{h}m"] = float((x > 0).mean()) if len(x) else math.nan
    return row


def score_config(rows: list[dict[str, Any]], stage: str, horizon: str = "3m") -> float:
    for r in rows:
        if r["stage"] == stage:
            n = r.get(f"n_{horizon.replace('m','')}m", r.get("n_3m", 0))
            if n < 15:
                return -999.0
            win = r.get(f"win_{horizon.replace('m','')}m", math.nan)
            mean = r.get(f"mean_{horizon.replace('m','')}m", math.nan)
            if not math.isfinite(win) or not math.isfinite(mean):
                return -999.0
            # composite: win rate + scaled mean excess
            return win * 100 + mean * 100 * 0.5
    return -999.0


def run_grid(mode: str, df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = prepare(df)
    li_opts = [
        (2, 2),  # 2 of 3 months mom
        (3, 3),  # 3 of 3
    ]
    de_opts = [1, 2]
    wang_dist = [0.65, 0.70, 0.75]
    wang_ratio = [101.0, 102.0]
    miao_opts = [4, 6, 8]

    grid_rows: list[dict[str, Any]] = []
    best_by_stage: dict[str, dict[str, Any]] = {}

    for li_m, li_min, de_h, wd, wr, miao in product(
        [2, 3], [2, 3], de_opts, wang_dist, wang_ratio, miao_opts
    ):
        if li_m == 2 and li_min == 3:
            continue
        if li_m == 3 and li_min == 2:
            continue
        p = Params(
            li_mom_months=li_m,
            li_mom_min_in_window=li_min if li_m == 2 else None if li_m == 3 else li_min,
            de_hold_months=de_h,
            wang_dist_pct=wd,
            wang_ratio_min=wr,
            miao_leading_months=miao,
        )
        if p.li_mom_months == 3:
            p = Params(
                li_mom_months=3,
                li_mom_min_in_window=3,
                de_hold_months=de_h,
                wang_dist_pct=wd,
                wang_ratio_min=wr,
                miao_leading_months=miao,
            )
        else:
            p = Params(
                li_mom_months=2,
                li_mom_min_in_window=2,
                de_hold_months=de_h,
                wang_dist_pct=wd,
                wang_ratio_min=wr,
                miao_leading_months=miao,
            )

        li = detect_li(df, p)
        de = detect_de_all(df, p)
        wang = detect_wang(df, p, de)
        miao = detect_miao(df, p, wang)

        stage_rows = [
            summarize_events(df, li, "利"),
            summarize_events(df, de, "得"),
            summarize_events(df, wang, "旺"),
            summarize_events(df, miao, "庙"),
        ]
        for sr in stage_rows:
            grid_rows.append({"mode": mode, "params": p.key(), **p.__dict__, **sr})

        for stage in ["利", "得", "旺", "庙"]:
            sc = score_config(stage_rows, stage, "3m")
            prev = best_by_stage.get(stage)
            if prev is None or sc > prev["score"]:
                best_by_stage[stage] = {"score": sc, "params": p, "stats": next(r for r in stage_rows if r["stage"] == stage)}

    # Also test H6 baseline 利 only
    h6 = (df["mom_above_3"] == 3) & (df["rs_ratio"] < 100)
    h6_row = summarize_events(df, h6, "利_H6基准")

    return pd.DataFrame(grid_rows), {"best_by_stage": best_by_stage, "h6_baseline": h6_row}


def train_test_split(df: pd.DataFrame, cut: str = "2015-01-01") -> tuple[pd.DataFrame, pd.DataFrame]:
    return df[df["date"] < cut].copy(), df[df["date"] >= cut].copy()


def recommend(mode: str, full: dict[str, Any], train: dict[str, Any], test: dict[str, Any]) -> dict[str, Any]:
    rec: dict[str, Any] = {"mode": mode, "stages": {}, "hardcode": {}, "customizable": []}
    for stage in ["利", "得", "旺", "庙"]:
        fp = full["best_by_stage"][stage]["params"]
        tp = train["best_by_stage"][stage]["params"]
        test_stats = None
        # evaluate train-best on test
        df_test = prepare(test_df := pd.read_csv(PANEL[mode]))
        df_test = df_test[df_test["date"] >= "2015-01-01"]
        p = tp
        li = detect_li(df_test, p)
        de = detect_de_all(df_test, p)
        wang = detect_wang(df_test, p, de)
        miao = detect_miao(df_test, p, wang)
        masks = {"利": li, "得": de, "旺": wang, "庙": miao}
        test_stats = summarize_events(df_test, masks[stage], stage)

        fs = full["best_by_stage"][stage]["stats"]
        ts = train["best_by_stage"][stage]["stats"]
        same = fp.key() == tp.key()
        rec["stages"][stage] = {
            "full_sample_best": fp.__dict__,
            "train_best": tp.__dict__,
            "full_stats_3m": {k: fs.get(k) for k in fs if "3m" in k or k in ("n", "assets", "stage")},
            "train_stats_3m": {k: ts.get(k) for k in ts if "3m" in k or k in ("n", "assets", "stage")},
            "test_stats_3m": {k: test_stats.get(k) for k in test_stats if "3m" in k or k in ("n", "assets", "stage")},
            "train_test_same_best": same,
        }
        # hardcode if train==full same AND test win reasonable OR stable across nearby params
        if stage == "利":
            rec["hardcode"]["li"] = tp.__dict__
        elif stage == "得":
            rec["hardcode"]["de"] = tp.__dict__
        elif stage == "旺":
            rec["hardcode"]["wang"] = tp.__dict__
        elif stage == "庙":
            rec["hardcode"]["miao"] = tp.__dict__

    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="all", choices=["us_gics", "cn_sw", "all"])
    args = ap.parse_args()
    modes = ["us_gics", "cn_sw"] if args.mode == "all" else [args.mode]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_grid: list[pd.DataFrame] = []
    recommendations: dict[str, Any] = {"modes": {}, "h6_baseline": {}, "notes": []}

    for mode in modes:
        path = PANEL[mode]
        if not path.exists():
            print(f"SKIP {mode}: run backtest_rrg.py first")
            continue
        raw = pd.read_csv(path)
        train_df, test_df = train_test_split(raw)
        grid_df, full_meta = run_grid(mode, raw)
        _, train_meta = run_grid(mode, train_df)
        rec = recommend(mode, full_meta, train_meta, test_df)
        recommendations["modes"][mode] = rec
        recommendations["h6_baseline"][mode] = full_meta["h6_baseline"]
        all_grid.append(grid_df)
        print(f"\n{'='*70}\n{mode}\n{'='*70}")
        print("H6 baseline 利:", full_meta["h6_baseline"])
        for stage in ["利", "得", "旺", "庙"]:
            b = full_meta["best_by_stage"][stage]
            s = b["stats"]
            print(
                f"  [{stage}] best={b['params'].key()} n={s['n']} "
                f"3m_win={s.get('win_3m', float('nan')):.1%} 3m_mean={s.get('mean_3m', float('nan'))*100:+.2f}%"
            )
            t = rec["stages"][stage]["test_stats_3m"]
            print(
                f"       train-best on test: n={t.get('n_3m',0)} "
                f"win={t.get('win_3m', float('nan')):.1%} mean={t.get('mean_3m', float('nan'))*100:+.2f}%"
            )

    if all_grid:
        out = pd.concat(all_grid, ignore_index=True)
        out.to_csv(OUT_DIR / "right_long_grid.csv", index=False)
        with (OUT_DIR / "right_long_recommendations.json").open("w", encoding="utf-8") as f:
            json.dump(recommendations, f, ensure_ascii=False, indent=2, default=str)
        print(f"\nWrote {OUT_DIR / 'right_long_grid.csv'}")
        print(f"Wrote {OUT_DIR / 'right_long_recommendations.json'}")


if __name__ == "__main__":
    main()
