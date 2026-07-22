#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/web"

if [[ ! -d node_modules ]]; then
  npm ci
fi

npm run build
echo "Built static assets -> $ROOT/static/"
