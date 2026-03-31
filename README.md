Jarvis - bounded autonomous task runner
- Runs a small, safe set of tasks in a loop
- Logs progress to run_logs/ and saves state to state.json
- Interrupt with Ctrl-C to gracefully stop; you can resume later
- Mission mode for multi-step shell actions with preview + explicit execute/cancel
- Deterministic local Siri-style status commands (battery, volume, song, wifi, date/time, active app)
## Daily-driver voice commands
- STATUS:
  - `is my laptop charging`
  - `what is my volume level`
  - `what song is playing`
  - `am i on wifi`
  - `what time is it`
  - `what app is active`
- Mac controls:
  - `set volume to 30`
  - `mute my volume` / `unmute my volume`
  - `quit chrome` / `focus chrome`
  - `open url https://example.com`
- Developer helpers (per‑repo):
  - `git status in ~/code`
  - `git diff in ~/code`
  - `git log in ~/code`
  - `git branches in ~/code`
  - `what changed since last commit in ~/code`
  - `search for hello in ~/code`
Quick commands:
- Start voice assistant: `bash workmode.sh`
- Check health: `bash status.sh`
- Stop assistant: `bash stopwork.sh`
- Reset local runner state/logs: `bash scripts/reset_state.sh`
- Run tests: `.venv/bin/python3 -m pytest -q`
Mission mode example:
- Say: `create folder called wow then create file called wow/notes.txt then list wow`
- Jarvis previews the plan, then waits for: `execute mission` or `cancel mission`
Battery example:
- Say: `what is the percentage of my battery health`
- Jarvis routes to shell status and speaks charge + health summary.
Local status examples:
- `what is my volume level`
- `what song is playing`
- `am i on wifi`
- `what time is it`
- `what app is active`

Translation examples:
- `translate "hello" to spanish`
- `say this in french: good morning`

Latency tuning:
- Default listen cue is a short beep (faster than spoken "Listening").
- Optional: `export JARVIS_LISTEN_CUE=speech` (old behavior) or `export JARVIS_LISTEN_CUE=none`.
- Per-turn timer summary in console: `export JARVIS_SHOW_TURN_TIMERS=1` (default on).
- STT backend defaults to `apple_native` on macOS for speed: `export JARVIS_STT_BACKEND=apple_native|google|local|auto`.
- Apple Speech language: `export JARVIS_APPLE_STT_LANGUAGE=en-US`.
- On macOS 26+, Apple helper is auto-disabled by default due TCC crash behavior; Jarvis falls back to local Whisper. Override only if you want to test: `export JARVIS_FORCE_APPLE_HELPER=1`.
- Apple strict endpoint close: `export JARVIS_APPLE_STT_SILENCE_END_MS=420` and `export JARVIS_APPLE_STT_MIN_SPEECH_MS=170`.
- Apple energy gate tuning: `export JARVIS_APPLE_STT_ENERGY_FLOOR=0.010` and `export JARVIS_APPLE_STT_ENERGY_MULTIPLIER=2.0`.
- Local model: `export JARVIS_LOCAL_STT_MODEL=tiny.en` (or `base.en` for better accuracy).
- End-of-speech cutoff: `export JARVIS_SILENCE_END_MS=300` (lower = faster, higher = safer).
- Optional local package install: `export JARVIS_INSTALL_LOCAL_STT=1` before `bash workmode.sh`.
- Trigger mode: `export JARVIS_TRIGGER_MODE=hotkey|wake|hybrid` (default `hotkey`).
- Wake backend: `export JARVIS_WAKEWORD_BACKEND=openwakeword|stt_phrase` (default `openwakeword`).
- Wake sensitivity: `export JARVIS_WAKEWORD_THRESHOLD=0.55` (higher = stricter).
- Wake polling window: `export JARVIS_WAKEWORD_POLL_SECONDS=0.8`.
- Wake guard against false triggers: `export JARVIS_WAKEWORD_TTS_GUARD_MS=1800`.
- Wake phrase strictness: `export JARVIS_WAKEWORD_MAX_WORDS=4`.
- VAD profile: `export JARVIS_VAD_PROFILE=fast|balanced|robust`.
- Partial transcript controls: `export JARVIS_SHOW_PARTIALS=1` and `export JARVIS_LOCAL_STT_PARTIAL_MAX_UPDATES=10`.
- Local STT quality tuning: `export JARVIS_LOCAL_STT_BEAM_SIZE=3`, `export JARVIS_LOCAL_STT_BEST_OF=3`, `export JARVIS_LOCAL_STT_CONDITION_ON_PREVIOUS=0`.
- Classifier mode: `export JARVIS_CLASSIFIER_MODE=rules|llm` (default `rules`).
- Translation target default: `export JARVIS_TRANSLATION_DEFAULT_TARGET=spanish`.
- Response style: `export JARVIS_RESPONSE_STYLE=truth_concise|balanced`.
- If prompted, allow Speech Recognition + Microphone in macOS privacy settings for Apple-native STT.
- Apple-native STT runs as a persistent local daemon process for faster follow-up turns.
- Strict preset for fast close: `JARVIS_APPLE_STT_SILENCE_END_MS=320` and `JARVIS_APPLE_STT_ENERGY_MULTIPLIER=2.4`.
- If Apple STT is blocked, reset permissions:
  - `tccutil reset SpeechRecognition com.jarvis.speechhelper`
  - `tccutil reset Microphone com.jarvis.speechhelper`
  - `tccutil reset SpeechRecognition com.apple.Terminal`
  - `tccutil reset Microphone com.apple.Terminal`
