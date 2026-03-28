## Install Jarvis v2 (local dev setup)

Jarvis v2 is designed to run locally on macOS with a minimal set of dependencies. This guide assumes a recent macOS version and a working Homebrew and Python 3 installation.

### 1. Clone the repository

```bash
git clone https://github.com/ctimothe/jarvis.git
cd jarvis_v2
```

### 2. Start Jarvis via the helper script

The `workmode.sh` script creates a virtualenv, installs Python dependencies, patches `webrtcvad` for newer Python versions, and launches Jarvis:

```bash
bash workmode.sh
```

On first run this may take a bit longer while dependencies download and the `.venv` is created.

### 3. Grant macOS permissions

On first use, macOS will likely prompt for:

- **Microphone** access for Terminal (or your terminal app)
- **Accessibility** permissions so Jarvis can register the hotkey (`Cmd+Shift+J`)

You can also review/fix these manually:

- `System Settings → Privacy & Security → Microphone` → enable Terminal
- `System Settings → Privacy & Security → Accessibility` → add and enable Terminal

If you see repeated \"I didn't catch that\" with `speech=0ms` in the console, it usually means the microphone permission is missing or the wrong input device is selected.

### 4. Check health and environment

Run the status script from the repo root:

```bash
bash status.sh
```

This checks:

- whether the Jarvis process is running
- whether the Ollama API is reachable (for `ask_ai` and summarisation)
- whether the virtualenv exists and core Python dependencies are importable
- prints short guidance on Accessibility and Microphone settings if needed.

### 5. Upgrade Jarvis

To update to the latest version from `master`:

```bash
cd jarvis_v2
git pull origin master
bash workmode.sh
```

This pulls new code and re-runs the setup script to ensure dependencies stay in sync.

### 6. Optional: local STT and wake-word extras

You can enable local Whisper STT and the OpenWakeWord backend via environment variables before running `workmode.sh`:

```bash
export JARVIS_INSTALL_LOCAL_STT=1        # install numpy + faster-whisper
export JARVIS_STT_BACKEND=local         # prefer local Whisper over Google
export JARVIS_INSTALL_WAKEWORD=1        # install openwakeword for wake-word mode
export JARVIS_TRIGGER_MODE=wake         # use wake-word instead of hotkey

bash workmode.sh
```

See the main `README.md` and `INSTRUCTIONS.md` for more environment options and tuning presets.\n*** End Patch```} ***!
