#!/usr/bin/env python3
"""按 series_rules.json 拼接序列，去除 catalog 中的重复项。

在 fetch_macro / fetch_longrun / fetch_indices 之后运行：
  python scripts/stitch_series.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.data_lib import (  # noqa: E402
    DATA_DIR,
    finalize_simple,
    load_rules,
    save_simple,
    stitch_us_bond_10y_monthly,
    stitch_us_cpi,
    stitch_us_sp500_monthly,
)

STITCHERS = {
    "stitch_us_cpi": stitch_us_cpi,
    "stitch_us_sp500_monthly": stitch_us_sp500_monthly,
    "stitch_us_bond_10y_monthly": stitch_us_bond_10y_monthly,
}


def main() -> int:
    rules = load_rules()
    ok, failed = 0, []

    for spec in rules.get("stitched", []):
        method = spec["method"]
        stitcher = STITCHERS.get(method)
        if stitcher is None:
            print(f"✗ {spec['id']}: 未知拼接方法 {method}", file=sys.stderr)
            failed.append(spec["id"])
            continue
        try:
            df = stitcher()
            if df.empty:
                raise RuntimeError("拼接结果为空")
            path = save_simple(df, spec["output"])
            out = finalize_simple(df)
            print(
                f"✓ {spec['id']}: {len(out)} 行, "
                f"{out['date'].iloc[0]} → {out['date'].iloc[-1]}"
            )
            print(f"  → {path.relative_to(ROOT)}")
            ok += 1
        except Exception as exc:
            print(f"✗ {spec['id']}: {exc}", file=sys.stderr)
            failed.append(spec["id"])

  # 删除已废弃且无保留价值的文件
    for dep in rules.get("deprecated", []):
        if dep.get("keep_file"):
            continue
        rel = dep.get("keep_file") or f"csv/assets/{dep['id']}.csv"
        path = DATA_DIR / rel
        if path.exists():
            path.unlink()
            print(f"  删除冗余文件 {rel}")

    print("-" * 60)
    print(f"拼接完成: {ok} 成功, {len(failed)} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
