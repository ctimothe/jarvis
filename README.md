Jarvis v2 - bounded autonomous task runner
- Runs a small, safe set of tasks in a loop
- Logs progress to run_logs/ and saves state to state.json
- Interrupt with Ctrl-C to gracefully stop; you can resume later
- Mission mode for multi-step shell actions with preview + explicit execute/cancel
- Deterministic local Siri-style status commands (battery, volume, song, wifi, date/time, active app)

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
- STT backend defaults to `google`: `export JARVIS_STT_BACKEND=local` only when you want local Whisper.
- Local model: `export JARVIS_LOCAL_STT_MODEL=tiny.en` (or `base.en` for better accuracy).
- End-of-speech cutoff: `export JARVIS_SILENCE_END_MS=300` (lower = faster, higher = safer).
- Optional local package install: `export JARVIS_INSTALL_LOCAL_STT=1` before `bash workmode.sh`.
- Trigger mode: `export JARVIS_TRIGGER_MODE=hotkey|wake|hybrid` (default `hybrid`).
- Wake backend: `export JARVIS_WAKEWORD_BACKEND=stt_phrase|openwakeword` (default `stt_phrase`).
- Wake guard against false triggers: `export JARVIS_WAKEWORD_TTS_GUARD_MS=1800`.
- Wake phrase strictness: `export JARVIS_WAKEWORD_MAX_WORDS=4`.
- VAD profile: `export JARVIS_VAD_PROFILE=fast|balanced|robust`.
- Classifier mode: `export JARVIS_CLASSIFIER_MODE=rules|llm` (default `rules`).
- Translation target default: `export JARVIS_TRANSLATION_DEFAULT_TARGET=spanish`.
- Response style: `export JARVIS_RESPONSE_STYLE=truth_concise|balanced`.
