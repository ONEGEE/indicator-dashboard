#!/usr/bin/env bash
# 分阶段更新数据，避免单次 fetch_rrg --mode all 过长导致超时。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

echo "==> 检查 Playwright（cn_housing 需要）"
"$PYTHON" scripts/ensure_playwright.py

echo "==> 轮动数据"
"$PYTHON" scripts/fetch_rotation.py

echo "==> RRG 数据（分模式，避免 --mode all 超时）"
RRG_FAILED=()
for mode in cross_asset us_gics cn_sw country; do
  echo "--- fetch_rrg: $mode ---"
  if ! "$PYTHON" scripts/fetch_rrg.py --mode "$mode"; then
    RRG_FAILED+=("$mode")
    echo "⚠ fetch_rrg $mode 失败，已跳过（其它模式继续）" >&2
  fi
done
if ((${#RRG_FAILED[@]})); then
  echo "⚠ RRG 部分失败: ${RRG_FAILED[*]}" >&2
fi

echo "==> 构建目录"
"$PYTHON" scripts/build_rotation_catalog.py
"$PYTHON" scripts/build_catalog.py

echo "==> 构建前端 static/"
if [[ ! -d web/node_modules ]]; then
  (cd web && npm ci)
fi
(cd web && npm run build)

echo "==> 完成 $(date '+%Y-%m-%d %H:%M:%S')"
