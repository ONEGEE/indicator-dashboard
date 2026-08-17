#!/usr/bin/env python3
"""RRG 右多策略：完整旅程状态机回测（月度 L1）。

用法：
  python scripts/backtest_rrg_right_long_journey.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "rrg_insights"
POLICY_PATH = OUT_DIR / "right_long_policy.json"
PANEL = {"us_gics": OUT_DIR / "panel_us_gics.csv", "cn_sw": OUT_DIR / "panel_cn_sw.csv"}

Stage = Literal["利", "得", "旺", "庙"]
Status = Literal["active", "falsified", "review"]


@dataclass
class Segment:
    stage: Stage
    start: str
    end: str


@dataclass
class Journey:
    mode: str
    asset_id: str
    asset_name: str
    journey_id: int
    opened_at: str
    closed_at: str | None
    status: Status
    current_stage: Stage | None
    falsified_at: str | None
    falsified_reason: str | None
    segments: list[Segment] = field(default_factory=list)
    reached_de: bool = False
    reached_miao: bool = False
    months_in_miao: int = 0

    def append_month(self, date: str, stage: Stage) -> None:
        if self.segments and self.segments[-1].stage == stage:
            self.segments[-1].end = date
        else:
            self.segments.append(Segment(stage, date, date))
        self.current_stage = stage


def load_policy() -> dict[str, Any]:
    with POLICY_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def mode_params(policy: dict[str, Any], mode: str) -> dict[str, Any]:
    shared = policy["hardcode"]["shared"]
    spec = policy["hardcode"][mode]
    return {**shared, **spec}


def mom_ok(row: pd.Series, p: dict[str, Any]) -> bool:
    need = int(p["li_mom_min_in_window"])
    return int(row.get("mom_above_3", 0)) >= need


def is_wang(row: pd.Series, p: dict[str, Any]) -> bool:
    if row["rs_ratio"] < 100 or row["rs_momentum"] < 100:
        return False
    return float(row["dist_pct"]) >= p["wang_dist_pct"] or float(row["rs_ratio"]) >= p["wang_ratio_min"]


def is_miao(row: pd.Series, p: dict[str, Any]) -> bool:
    return (
        row["quadrant"] == "leading"
        and row["rs_ratio"] >= 100
        and int(row["bars_in_quadrant"]) >= int(p["miao_leading_months"])
        and int(row.get("ratio_above_3", 0)) >= 3
    )


def classify_stage(row: pd.Series, p: dict[str, Any], reached_de: bool) -> Stage | None:
    """给定当前月，若已在旅程中，应处于哪一档（不含利的前置观察）。"""
    if is_miao(row, p) and reached_de:
        return "庙"
    if is_wang(row, p) and reached_de:
        return "旺"
    if row["rs_ratio"] >= 100 and row["rs_momentum"] >= 100 and reached_de:
        return "得"
    if mom_ok(row, p) and row["rs_ratio"] < 100:
        return "利"
    if reached_de and row["rs_ratio"] >= 100:
        return "得"
    return None


def can_open(row: pd.Series, p: dict[str, Any]) -> Stage | None:
    if mom_ok(row, p) and row["rs_ratio"] < 100:
        return "利"
    if row["rs_ratio"] >= 100 and row["rs_momentum"] >= 100:
        if is_miao(row, p):
            return "庙"
        if is_wang(row, p):
            return "旺"
        return "得"
    return None


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["id", "date"]).copy()
    df["dist_pct"] = df.groupby("date")["distance"].rank(pct=True)
    return df


def simulate_mode(mode: str, df: pd.DataFrame, policy: dict[str, Any]) -> list[Journey]:
    p = mode_params(policy, mode)
    hold = int(p["de_hold_months"])
    review_cap = int(p["review_cap_months"])
    journeys: list[Journey] = []
    jid = 0

    for asset_id, sub in df.groupby("id"):
        name = str(sub.iloc[0]["name"])
        active: Journey | None = None
        rows = sub.reset_index(drop=True)

        # track ratio cross hold
        de_confirmed = False
        cross_idx: int | None = None

        for i, row in rows.iterrows():
            date = str(row["date"])
            prev = rows.iloc[i - 1] if i > 0 else None

            # detect cross for de confirmation
            if prev is not None and prev["rs_ratio"] < 100 <= row["rs_ratio"] and row["rs_momentum"] >= 100:
                cross_idx = i
                de_confirmed = False

            if cross_idx is not None and not de_confirmed:
                if i >= cross_idx + hold - 1:
                    window = rows.iloc[cross_idx : i + 1]
                    if (window["rs_ratio"] >= 100).all() and row["rs_momentum"] >= 100:
                        de_confirmed = True

            if active is None:
                open_stage = can_open(row, p)
                if open_stage:
                    jid += 1
                    active = Journey(
                        mode=mode,
                        asset_id=asset_id,
                        asset_name=name,
                        journey_id=jid,
                        opened_at=date,
                        closed_at=None,
                        status="active",
                        current_stage=open_stage,
                        falsified_at=None,
                        falsified_reason=None,
                        reached_de=open_stage in ("得", "旺", "庙"),
                        reached_miao=open_stage == "庙",
                    )
                    active.append_month(date, open_stage)
                continue

            # active journey updates
            if active.status != "active":
                continue

            stage = classify_stage(row, p, active.reached_de or de_confirmed)
            if de_confirmed:
                active.reached_de = True
            if stage == "庙":
                active.reached_miao = True
                active.months_in_miao += 1
            elif active.reached_miao and stage != "庙":
                active.months_in_miao = 0

            # falsify rules
            if not active.reached_de:
                if not mom_ok(row, p):
                    active.status = "falsified"
                    active.falsified_at = date
                    active.falsified_reason = "利：动能回落，未出现得"
                    active.closed_at = date
                    active.append_month(date, active.current_stage or "利")
                    journeys.append(active)
                    active = None
                    cross_idx = None
                    de_confirmed = False
                    continue
            else:
                if row["rs_ratio"] < 100:
                    active.status = "falsified"
                    active.falsified_at = date
                    active.falsified_reason = "Ratio 跌破 100"
                    active.closed_at = date
                    if stage:
                        active.append_month(date, active.current_stage or "得")
                    journeys.append(active)
                    active = None
                    cross_idx = None
                    de_confirmed = False
                    continue

            if active.reached_miao and active.months_in_miao >= review_cap:
                active.status = "review"
                active.closed_at = date

            if stage:
                active.append_month(date, stage)
            elif active.current_stage:
                active.append_month(date, active.current_stage)

        if active is not None:
            journeys.append(active)

    return journeys


def summarize_journeys(mode: str, journeys: list[Journey]) -> dict[str, Any]:
    total = len(journeys)
    active = [j for j in journeys if j.status == "active"]
    review = [j for j in journeys if j.status == "review"]
    falsified = [j for j in journeys if j.status == "falsified"]
    reached_de = [j for j in journeys if j.reached_de]
    reached_miao = [j for j in journeys if j.reached_miao]

    def dur(j: Journey) -> int:
        if not j.segments:
            return 0
        return sum(
            1
            for _ in range(1)  # placeholder
        )

    # duration in months = sum segment lengths approximated by counting segment end-start
    durations = []
    for j in journeys:
        months = 0
        for seg in j.segments:
            # each segment end is updated per month; count unique months approx via segment count weighted
            months += max(1, 1)  # fix below
        if j.segments:
            # count total months as number of segment updates - use closed_at-opened
            durations.append(len(j.segments))  # underestimate; use events instead

    # concurrent active at each date
    dates = sorted({seg.end for j in journeys for seg in j.segments})
    concurrent = []
    for d in dates:
        c = sum(
            1
            for j in journeys
            if j.opened_at <= d
            and (j.closed_at is None or j.closed_at >= d)
            and j.status in ("active", "review")
        )
        concurrent.append(c)

    li_only = [j for j in journeys if not j.reached_de and j.status == "falsified"]
    de_plus_active = [j for j in active + review if j.reached_de]

    return {
        "mode": mode,
        "total_journeys": total,
        "active": len(active),
        "review": len(review),
        "falsified": len(falsified),
        "reached_de": len(reached_de),
        "reached_de_pct": round(len(reached_de) / total * 100, 1) if total else 0,
        "reached_miao": len(reached_miao),
        "reached_miao_pct": round(len(reached_miao) / total * 100, 1) if total else 0,
        "falsified_before_de": len(li_only),
        "falsified_before_de_pct": round(len(li_only) / total * 100, 1) if total else 0,
        "concurrent_active_median": float(pd.Series(concurrent).median()) if concurrent else 0,
        "concurrent_active_p90": float(pd.Series(concurrent).quantile(0.9)) if concurrent else 0,
        "concurrent_active_max": max(concurrent) if concurrent else 0,
        "de_plus_active_now": len(de_plus_active),
        "avg_segments": round(sum(len(j.segments) for j in journeys) / total, 2) if total else 0,
    }


def export_journeys_json(mode: str, journeys: list[Journey], limit_recent: int = 80) -> list[dict[str, Any]]:
    """Export recent journeys for frontend dev sample."""
    rows = sorted(journeys, key=lambda j: j.opened_at, reverse=True)[:limit_recent]
    out = []
    for j in rows:
        out.append(
            {
                "journeyId": j.journey_id,
                "assetId": j.asset_id,
                "assetName": j.asset_name,
                "openedAt": j.opened_at,
                "closedAt": j.closed_at,
                "status": j.status,
                "currentStage": j.current_stage,
                "reachedDe": j.reached_de,
                "reachedMiao": j.reached_miao,
                "falsifiedAt": j.falsified_at,
                "falsifiedReason": j.falsified_reason,
                "segments": [{"stage": s.stage, "start": s.start, "end": s.end} for s in j.segments],
            }
        )
    return out


def main() -> None:
    policy = load_policy()
    summary_all: dict[str, Any] = {"modes": {}, "journeys_sample": {}}

    for mode, path in PANEL.items():
        if not path.exists():
            print(f"SKIP {mode}")
            continue
        df = prepare(pd.read_csv(path))
        journeys = simulate_mode(mode, df, policy)
        sm = summarize_journeys(mode, journeys)
        summary_all["modes"][mode] = sm
        summary_all["journeys_sample"][mode] = export_journeys_json(mode, journeys, 40)
        print(f"\n=== {mode} ===")
        for k, v in sm.items():
            if k != "mode":
                print(f"  {k}: {v}")

    out_path = OUT_DIR / "right_long_journey_summary.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary_all, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
