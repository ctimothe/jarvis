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

echo

if [[ -x "$SCRIPT_DIR/.venv/bin/python3" ]]; then
  echo "Jarvis doctor:"
  if "$SCRIPT_DIR/.venv/bin/python3" - <<'PY' >/dev/null 2>&1; then
import importlib
mods = ("speech_recognition", "pyaudio", "webrtcvad", "requests", "pynput")
missing = [m for m in mods if importlib.util.find_spec(m) is None]
raise SystemExit(1 if missing else 0)
PY
  then
    echo "  ✅ Core Python deps: present"
  else
    echo "  ⚠️ Core Python deps: missing (re-run bash workmode.sh)"
  fi
  echo "  ℹ️ If hotkey does nothing, add Terminal to Accessibility in System Settings."
  echo "  ℹ️ If mic fails, check Microphone access for Terminal in Privacy settings."
fi
