#!/bin/bash
# 安装 / 卸载 macOS launchd 定时任务
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.databoard.update-indices"
PLIST_DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"
TEMPLATE="$ROOT/scripts/${LABEL}.plist.template"

uninstall() {
  if launchctl list "$LABEL" >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$PLIST_DEST" 2>/dev/null || true
  fi
  rm -f "$PLIST_DEST"
  echo "已卸载定时任务: $LABEL"
}

install() {
  mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/data/logs"
  sed "s|__PROJECT_ROOT__|$ROOT|g" "$TEMPLATE" >"$PLIST_DEST"
  chmod +x "$ROOT/scripts/update_indices.sh"
  # 先卸再装，避免重复
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"
  echo "已安装定时任务: $LABEL"
  echo "  时间: 每天 08:30、18:30"
  echo "  脚本: $ROOT/scripts/update_indices.sh"
  echo "  日志: $ROOT/data/logs/"
  echo
  echo "查看状态: launchctl list | grep databoard"
  echo "立刻试跑: bash $ROOT/scripts/update_indices.sh"
}

case "${1:-}" in
  --uninstall|-u) uninstall ;;
  *) install ;;
esac
