## macOS automation and permissions model

Jarvis runs as a single local Python process and controls macOS using a small, explicit set of primitives. This document explains those primitives and how permissions are expected to behave so issues are easier to debug.

### Automation primitives

Jarvis uses three main macOS integration points:

- **AppleScript via `osascript`** (wrapped by `_osascript()` in `jarvis_clean.py`):
  - App control:
    - open/focus apps: `open -a <App>` and `tell application "<App>" to activate`
    - quit apps: `tell application "<App>" to quit`
  - Music:
    - Spotify and Music control: play/pause/next/previous, volume, and now playing details
  - System Events:
    - lock screen: simulated `Ctrl+Cmd+Q` using `System Events`
    - shutdown/restart flows (with a spoken countdown)
- **Core CLI tools**:
  - `pmset` for sleep and battery info
  - `system_profiler` for detailed battery health
  - `networksetup` for Wi‑Fi SSID discovery
  - `df` for disk usage
  - `git` and `rg` for developer and project-search actions (restricted to `HOME`)
- **TTS and app launching**:
  - `say` for all speech output
  - `open -a Ollama` to start the local model runtime when needed

All of these are invoked through the typed action engine:

- macOS‑oriented actions (e.g. volume set/mute, now playing, Wi‑Fi status, active app, app quit/focus, open URL) are represented as specific `ACTION_*` constants and executed only inside `_execute_action_request()` using explicit argv lists.
- File and dev actions are similarly typed, and policy-checked before any subprocess is run.

### Permissions expectations

Because Jarvis runs in a Terminal (or iTerm) process, macOS privacy and security settings apply to that terminal app:

- **Microphone**:
  - `System Settings → Privacy & Security → Microphone` must allow Terminal (or your chosen terminal) for `SmartMic.listen()` to receive audio.
  - When this is missing or denied, Jarvis can start listening but will record **zero speech frames**, producing turns with `speech=0ms`, `stt=0ms`, and the spoken response “I didn't catch that.”
- **Accessibility (input monitoring)**:
  - `System Settings → Privacy & Security → Accessibility` should include Terminal with the toggle enabled.
  - Without this, macOS logs `This process is not trusted! Input event monitoring will not be possible until it is added to accessibility clients.` and global hotkeys may not fire reliably.
- **Speech recognition helper** (Apple native STT):
  - When configured to use the Apple native backend, Jarvis builds a small helper app bundle (`JarvisSpeechHelper.app`) with the proper usage descriptions.
  - On newer macOS releases, this helper can be unstable due to TCC policy; Jarvis detects that and falls back to local Whisper or Google STT instead, printing guidance on how to reset TCC if needed.

### Health checks and “doctor” flow

There are two main ways to diagnose environment issues:

- **`bash status.sh`**:
  - Prints:
    - whether the Jarvis process is running
    - whether the Ollama API is reachable
    - whether the virtualenv is present
  - Runs a lightweight “Jarvis doctor” section:
    - verifies core Python dependencies (`speech_recognition`, `pyaudio`, `webrtcvad`, `requests`, `pynput`) are importable in `.venv`
    - reminds you to:
      - add Terminal to Accessibility if the hotkey does nothing
      - grant Microphone access to Terminal if the mic appears silent.
- **Spoken “doctor” helper**:
  - Saying phrases like “Jarvis doctor” or “health check” triggers a quick explanation of the same steps, optimized for TTS, and suggests running the status script from the repo.

Taken together, the typed action engine, narrow set of macOS primitives, and explicit permission guidance make Jarvis’s automation behavior predictable, auditable, and debuggable.\n*** End Patch```} ***!
