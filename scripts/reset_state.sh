#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$SCRIPT_DIR/state.template.json"
STATE="$SCRIPT_DIR/state.json"
LOG_DIR="$SCRIPT_DIR/run_logs"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "❌ Missing template: $TEMPLATE"
  exit 1
fi

cp "$TEMPLATE" "$STATE"
mkdir -p "$LOG_DIR"
rm -f "$LOG_DIR"/*.log

echo "✅ Reset local runtime state at $STATE"
echo "✅ Cleared runtime logs in $LOG_DIR"
