#!/usr/bin/env python3
"""兼容入口：拉取标普500。实际逻辑见 fetch_indices.py。"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fetch_indices.py"

if __name__ == "__main__":
    cmd = [sys.executable, str(SCRIPT), "--id", "us_sp500", *sys.argv[1:]]
    raise SystemExit(subprocess.call(cmd))
