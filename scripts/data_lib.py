"""数据整理共用工具：序列拼接、去重、读写。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RULES_PATH = DATA_DIR / "series_rules.json"


def load_rules() -> dict[str, Any]:
    with RULES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def deprecated_ids() -> set[str]:
    return {item["id"] for item in load_rules().get("deprecated", [])}


def read_simple(rel_path: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / rel_path)
    df["date"] = pd.to_datetime(df["date"])
    if "value" in df.columns:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date")


def read_ohlcv(rel_path: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / rel_path)
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["date", "close"]).sort_values("date")


def finalize_simple(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["date", "value"]].copy()
    out["date"] = pd.to_datetime(out["date"])
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["date", "value"])
    out = out.drop_duplicates(subset=["date"], keep="last")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out.sort_values("date").reset_index(drop=True)


def save_simple(df: pd.DataFrame, rel_path: str) -> Path:
    path = DATA_DIR / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    finalize_simple(df).to_csv(path, index=False, float_format="%.6f")
    return path


def stitch_segments(segments: list[pd.DataFrame]) -> pd.DataFrame:
    """按顺序拼接多段序列，后段覆盖重叠日期。"""
    if not segments:
        return pd.DataFrame(columns=["date", "value"])
    combined = pd.concat(segments, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])
    combined["value"] = pd.to_numeric(combined["value"], errors="coerce")
    combined = combined.dropna(subset=["date", "value"])
    combined = combined.drop_duplicates(subset=["date"], keep="last")
    return combined.sort_values("date").reset_index(drop=True)


def resample_monthly_close(rel_path: str) -> pd.DataFrame:
    df = read_ohlcv(rel_path)
    monthly = (
        df.set_index("date")["close"]
        .resample("MS")
        .last()
        .dropna()
        .reset_index()
        .rename(columns={"close": "value"})
    )
    return monthly


def stitch_us_cpi() -> pd.DataFrame:
    """CPIAUCNS(1913-1946) + CPIAUCSL(1947+) → 完整月度 CPI。"""
    early = read_simple("csv/longrun/us_cpi_1913.csv")
    early = early[early["date"] < pd.Timestamp("1947-01-01")]
    late_path = "csv/macro/_components/us_cpi_cpiausl.csv"
    if (DATA_DIR / late_path).exists():
        late = read_simple(late_path)
    else:
        # 兼容：尚未拆分组件时从当前 us_cpi 读取
        late = read_simple("csv/macro/us_cpi.csv")
    late = late[late["date"] >= pd.Timestamp("1947-01-01")]
    return stitch_segments([early, late])


def stitch_us_sp500_monthly() -> pd.DataFrame:
    """Shiller 月度(1871-2023-09) + yfinance 日K 转月度(2023-10+)。"""
    shiller = read_simple("csv/longrun/us_sp500_shiller.csv")
    shiller = shiller[shiller["date"] < pd.Timestamp("2023-10-01")]
    recent = resample_monthly_close("csv/us_sp500.csv")
    recent = recent[recent["date"] >= pd.Timestamp("2023-10-01")]
    return stitch_segments([shiller, recent])


def stitch_us_bond_10y_monthly() -> pd.DataFrame:
    """JST 长期利率(1870-1952) + FRED GS10 月度(1953+)。"""
    jst = read_simple("csv/longrun/jst_usa_ltrate.csv")
    jst = jst[jst["date"] < pd.Timestamp("1953-04-01")]
    gs10 = read_simple("csv/longrun/us_gs10_monthly.csv")
    gs10 = gs10[gs10["date"] >= pd.Timestamp("1953-04-01")]
    return stitch_segments([jst, gs10])


# ── 轮动 / 市值层 ──────────────────────────────────────────────

def finalize_marketcap(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["date", "value_usd"]].copy()
    out["date"] = pd.to_datetime(out["date"])
    out["value_usd"] = pd.to_numeric(out["value_usd"], errors="coerce")
    out = out.dropna(subset=["date", "value_usd"])
    out = out.drop_duplicates(subset=["date"], keep="last")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out.sort_values("date").reset_index(drop=True)


def last_complete_month_start(today: pd.Timestamp | None = None) -> pd.Timestamp:
    """展示截止到上一完整自然月（隐藏仍在进行中的当月）。"""
    today = (today or pd.Timestamp.today()).normalize()
    return today.replace(day=1) - pd.offsets.MonthBegin(1)


def project_marketcap_with_return(
    mc_df: pd.DataFrame,
    return_df: pd.DataFrame,
    through: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """用回报/价格指数延续市值至 through，填补官方存量数据滞后月份。

    返回 (合并后市值, 仅外推月份明细；无外推时后者为空)。
    """
    through = through or last_complete_month_start()
    mc = mc_df.copy()
    mc["date"] = pd.to_datetime(mc["date"])
    mc["value_usd"] = pd.to_numeric(mc["value_usd"], errors="coerce")
    mc = mc.dropna(subset=["date", "value_usd"]).sort_values("date")
    if mc.empty:
        return mc_df, pd.DataFrame(columns=["date", "value_usd"])

    ret = return_df.copy()
    ret["date"] = pd.to_datetime(ret["date"])
    ret["value"] = pd.to_numeric(ret["value"], errors="coerce")
    ret = ret.dropna(subset=["date", "value"]).sort_values("date")
    if ret.empty:
        return mc_df, pd.DataFrame(columns=["date", "value_usd"])

    mc["month"] = mc["date"].dt.to_period("M").dt.to_timestamp()
    ret["month"] = ret["date"].dt.to_period("M").dt.to_timestamp()
    mc_s = mc.drop_duplicates("month", keep="last").set_index("month")["value_usd"]
    ret_s = ret.drop_duplicates("month", keep="last").set_index("month")["value"]

    last_m = mc_s.index.max()
    if last_m >= through:
        return mc_df, pd.DataFrame(columns=["date", "value_usd"])

    anchor_val = float(mc_s.loc[last_m])
    anchor_idx = float(ret_s.loc[last_m]) if last_m in ret_s.index else float(ret_s.asof(last_m))
    if not anchor_idx or anchor_idx <= 0:
        return mc_df, pd.DataFrame(columns=["date", "value_usd"])

    months = pd.date_range(last_m + pd.offsets.MonthBegin(1), through, freq="MS")
    extra_rows: list[dict[str, object]] = []
    for m in months:
        idx = float(ret_s.loc[m]) if m in ret_s.index else float(ret_s.asof(m))
        if not idx or idx <= 0:
            continue
        val = anchor_val * (idx / anchor_idx)
        extra_rows.append({"date": m, "value_usd": val})

    if not extra_rows:
        return mc_df, pd.DataFrame(columns=["date", "value_usd"])

    extra = pd.DataFrame(extra_rows)
    combined = pd.concat([mc[["date", "value_usd"]], extra], ignore_index=True)
    return combined, extra


def save_marketcap(df: pd.DataFrame, rel_path: str) -> Path:
    path = DATA_DIR / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    finalize_marketcap(df).to_csv(path, index=False, float_format="%.2f")
    return path


def to_monthly_last(series: pd.Series) -> pd.Series:
    s = series.copy()
    s.index = pd.to_datetime(s.index)
    return s.resample("MS").last().dropna()


def scale_annual_to_monthly(
    annual: pd.DataFrame,
    monthly_index: pd.DataFrame,
    value_col: str = "value",
) -> pd.DataFrame:
    """用年度市值锚点 + 月度价格指数，生成月度市值序列。

    年度观测视为该年年末（12 月）存量。各月以上一锚点向前缩放：
        mcap(t) = cap(A) * index(t) / index(A)，A = 不晚于 t 的最近年末锚点。

    这样 12→1 月连续，避免旧算法「用当年年末市值回推整年」造成的每年 1 月断层。
    新年度锚点落地时，可能在该年 12 月出现一次与指数隐含路径的校准跳变（属年末对账）。
    """
    ann = annual.copy()
    ann["date"] = pd.to_datetime(ann["date"])
    ann[value_col] = pd.to_numeric(ann[value_col], errors="coerce")
    ann = ann.dropna().sort_values("date")

    idx = monthly_index.copy()
    idx["date"] = pd.to_datetime(idx["date"])
    idx["value"] = pd.to_numeric(idx["value"], errors="coerce")
    idx = idx.dropna().set_index("date").sort_index()

    anchors: list[tuple[pd.Timestamp, float]] = []
    for _, row in ann.iterrows():
        year = int(row["date"].year)
        year_idx = idx[idx.index.year == year]
        if year_idx.empty:
            continue
        dec = year_idx[year_idx.index.month == 12]
        anchor_date = dec.index[-1] if not dec.empty else year_idx.index[-1]
        anchors.append((anchor_date, float(row[value_col])))

    if not anchors:
        return pd.DataFrame(columns=["date", "value_usd"])

    anchors.sort(key=lambda x: x[0])
    first_date, first_cap = anchors[0]
    first_base = float(idx.loc[first_date, "value"])
    if first_base == 0:
        return pd.DataFrame(columns=["date", "value_usd"])

    rows: list[dict[str, Any]] = []
    # 首个锚点年：允许用年末锚回推同年更早月份（仅此一年）
    pre = idx[(idx.index < first_date) & (idx.index.year == first_date.year)]
    for dt, val in pre["value"].items():
        rows.append({"date": dt, "value_usd": first_cap * float(val) / first_base})

    for dt, val in idx["value"].items():
        if dt < first_date and dt.year != first_date.year:
            continue
        a_date, a_cap = anchors[0]
        for ad, ac in anchors:
            if ad <= dt:
                a_date, a_cap = ad, ac
            else:
                break
        base_val = float(idx.loc[a_date, "value"])
        if base_val == 0:
            continue
        rows.append({"date": dt, "value_usd": a_cap * float(val) / base_val})

    out = pd.DataFrame(rows)
    out = out.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    return out.reset_index(drop=True)


def scale_from_anchor(
    monthly_index: pd.DataFrame,
    anchor_date: str,
    anchor_value: float,
) -> pd.DataFrame:
    idx = monthly_index.copy()
    idx["date"] = pd.to_datetime(idx["date"])
    idx["value"] = pd.to_numeric(idx["value"], errors="coerce")
    idx = idx.dropna().set_index("date").sort_index()
    anchor_ts = pd.Timestamp(anchor_date)
    base = idx[idx.index <= anchor_ts]
    if base.empty:
        raise RuntimeError(f"指数在锚点 {anchor_date} 前无数据")
    base_val = float(base.iloc[-1]["value"])
    cap = anchor_value * (idx["value"] / base_val)
    out = cap.reset_index()
    out.columns = ["date", "value_usd"]
    return out.dropna()

