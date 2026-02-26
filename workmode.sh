#!/usr/bin/env bash
# Launch J.A.R.V.I.S. with a local virtual environment.
# Usage: bash workmode.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JARVIS="$SCRIPT_DIR/jarvis_clean.py"
VENV="$SCRIPT_DIR/.venv"
PYTHON="$VENV/bin/python3"

if [[ ! -f "$JARVIS" ]]; then
  echo "❌ jarvis_clean.py not found in $SCRIPT_DIR"
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "⚠️ Homebrew not found — microphone support may fail without portaudio."
else
  if ! brew list portaudio >/dev/null 2>&1; then
    echo "📦 Installing portaudio..."
    brew install portaudio -q
  fi
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "🔧 Creating virtual environment..."
  python3 -m venv "$VENV"
fi

echo "📦 Installing Python dependencies..."
"$PYTHON" -m pip install --quiet --upgrade pip
"$PYTHON" -m pip install --quiet speechrecognition pyaudio pynput requests webrtcvad setuptools

INSTALL_LOCAL_STT="${JARVIS_INSTALL_LOCAL_STT:-0}"
if [[ "$INSTALL_LOCAL_STT" == "1" ]]; then
  echo "📦 Checking optional local STT dependencies..."
  if ! "$PYTHON" - <<'PY'
import importlib.util
mods = ("numpy", "faster_whisper")
missing = [m for m in mods if importlib.util.find_spec(m) is None]
raise SystemExit(1 if missing else 0)
PY
  then
    echo "📦 Installing optional local STT packages (numpy, faster-whisper)..."
    if "$PYTHON" -m pip install --quiet numpy faster-whisper; then
      echo "✅ Local STT packages installed."
    else
      echo "⚠️  Optional local STT install failed. Jarvis will use Google STT fallback."
    fi
  else
    echo "✅ Optional local STT packages already available."
  fi
else
  echo "ℹ️ Optional local STT install skipped (set JARVIS_INSTALL_LOCAL_STT=1 to enable)."
fi

WAKEWORD_BACKEND="${JARVIS_WAKEWORD_BACKEND:-openwakeword}"
INSTALL_WAKEWORD="${JARVIS_INSTALL_WAKEWORD:-auto}"
if [[ "$INSTALL_WAKEWORD" == "auto" ]]; then
  if [[ "$WAKEWORD_BACKEND" == "openwakeword" ]]; then
    INSTALL_WAKEWORD="1"
  else
    INSTALL_WAKEWORD="0"
  fi
fi

if [[ "$INSTALL_WAKEWORD" == "1" ]]; then
  echo "📦 Installing optional wake-word package (openwakeword)..."
  if "$PYTHON" -m pip install --quiet openwakeword; then
    echo "✅ Wake-word package installed."
  else
    echo "⚠️  Wake-word package install failed. Falling back to stt_phrase backend."
  fi
fi

# Patch webrtcvad wrapper for Python 3.14+ where pkg_resources can be unavailable.
WRTC="$($PYTHON -c 'import site, pathlib; print(pathlib.Path(site.getsitepackages()[0]) / "webrtcvad.py")' 2>/dev/null || true)"
if [[ -n "${WRTC:-}" ]] && [[ -f "$WRTC" ]] && grep -q "pkg_resources" "$WRTC"; then
  "$PYTHON" - "$WRTC" <<'PYFIX'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text()
text = re.sub(r"import pkg_resources\n", "", text)
text = re.sub(r"pkg_resources\.get_distribution\('webrtcvad'\)\.version", "'2.0.10'", text)
path.write_text(text)
print("✅ Patched webrtcvad.py for Python 3.14+")
PYFIX
fi

echo

echo "🚀 Starting J.A.R.V.I.S..."
echo "   Hotkey : Command + Shift + J"
echo "   Quit   : Ctrl + C"
echo

"$PYTHON" "$JARVIS"
