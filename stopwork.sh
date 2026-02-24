#!/usr/bin/env bash

set -euo pipefail

if pgrep -f "jarvis_clean.py" >/dev/null 2>&1; then
	pkill -f "jarvis_clean.py"
	echo "🛑 Stopped jarvis_clean.py"
else
	echo "ℹ️ Jarvis is not running"
fi
