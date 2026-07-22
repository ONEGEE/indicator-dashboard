#!/bin/bash
# 增量更新：指数 + 资产 + 宏观，并重建 catalog
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG_DIR="$ROOT/data/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/update_$(date +%Y%m%d).log"

{
  echo "==== $(date '+%Y-%m-%d %H:%M:%S') 开始增量更新 ===="
  if [ -d .venv ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
  fi
  echo "--- indices ---"
  python scripts/fetch_indices.py --mode update --delay 0.8
  echo "--- assets ---"
  python scripts/fetch_assets.py --mode update --delay 0.6
  echo "--- macro ---"
  python scripts/fetch_macro.py --mode update --delay 0.4
  echo "--- longrun ---"
  python scripts/fetch_longrun.py --skip-download
  echo "--- stitch ---"
  python scripts/stitch_series.py
  echo "--- rotation ---"
  python scripts/fetch_rotation.py --delay 0.6
  python scripts/build_rotation_catalog.py
  echo "--- catalog ---"
  python scripts/build_catalog.py
  echo "==== $(date '+%Y-%m-%d %H:%M:%S') 结束 ===="
  echo
} >>"$LOG_FILE" 2>&1
