#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "JARVIS workspace: $SCRIPT_DIR"

if pgrep -f "jarvis_clean.py" >/dev/null 2>&1; then
	echo "✅ Jarvis process: running"
else
	echo "ℹ️ Jarvis process: not running"
fi

if curl -sS --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
	echo "✅ Ollama API: reachable"
else
	echo "⚠️ Ollama API: offline (start Ollama app)"
fi

if [[ -x "$SCRIPT_DIR/.venv/bin/python3" ]]; then
	echo "✅ Virtualenv: present"
else
	echo "ℹ️ Virtualenv: missing (run bash workmode.sh)"
fi
