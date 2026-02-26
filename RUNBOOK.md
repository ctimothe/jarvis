# JARVIS Operational Runbook

## Health checks
- Workspace status: `bash status.sh`
- Python syntax: `.venv/bin/python3 -c "import ast,pathlib; ast.parse(pathlib.Path('jarvis_clean.py').read_text()); print('Syntax OK')"`
- Shell script syntax: `bash -n workmode.sh status.sh stopwork.sh`
- Unit tests: `.venv/bin/python3 -m pytest -q`

## Runtime controls
- Start: `bash workmode.sh`
- Stop: `bash stopwork.sh`
- Reset local task-runner state/logs: `bash scripts/reset_state.sh`
- Mission mode voice controls:
  - Build plan with connectors: `then`, `and then`, `;`, `->`
  - Execute pending plan: `execute mission`
  - Cancel pending plan: `cancel mission`
  - Get last summary: `mission report`
- Low-latency/STT tuning:
  - `export JARVIS_LISTEN_CUE=beep` (default), `speech`, or `none`
  - `export JARVIS_STT_BACKEND=google` (default)
  - `export JARVIS_STT_BACKEND=local` for local Whisper
  - `export JARVIS_LOCAL_STT_MODEL=tiny.en` (`base.en` for better accuracy)
  - `export JARVIS_SILENCE_END_MS=300` for faster turn-taking
  - `export JARVIS_VAD_PROFILE=fast|balanced|robust` for capture stability/speed
  - `export JARVIS_INSTALL_LOCAL_STT=1` before `bash workmode.sh` to install local Whisper deps
  - `export JARVIS_TRIGGER_MODE=hotkey|wake|hybrid` (default `hybrid`)
  - `export JARVIS_WAKEWORD_BACKEND=stt_phrase|openwakeword`
  - `export JARVIS_WAKEWORD_TTS_GUARD_MS=1800` to ignore wake detection right after Jarvis speaks
  - `export JARVIS_WAKEWORD_MAX_WORDS=4` for strict wake phrase filtering
  - `export JARVIS_CLASSIFIER_MODE=rules|llm` (default `rules`; `llm` is slower)
  - `export JARVIS_RESPONSE_STYLE=truth_concise|balanced`
  - `export JARVIS_TRANSLATION_DEFAULT_TARGET=spanish`

## Deterministic local commands
- Battery: `is my laptop charging`, `battery health`
- Volume: `what is my volume level`
- Media: `what song is playing`
- Network: `am i on wifi`
- Time/date: `what time is it`, `date today`
- Active app: `what app is active`
- Translation: `translate "hello" to spanish`, `say this in french: hello`

## Shell startup issue
- If you see `command not found: compdef`, add this near the top of your `~/.zshrc`:
  - `autoload -Uz compinit`
  - `compinit`

## Audit and metrics
- Audit trail: `~/.jarvis_audit/audit.jsonl`
- Metrics stream: `~/.jarvis_audit/metrics.jsonl`
- Quick inspect:
  - `tail -n 100 ~/.jarvis_audit/audit.jsonl`
  - `tail -n 100 ~/.jarvis_audit/metrics.jsonl`

## Failure drills
1. Policy-block drill:
   - Ask to delete outside home (should be blocked by policy).
2. Approval drill:
   - Ask to delete a file in home (should require voice "yes").
3. Queue-pressure drill:
   - Trigger many file actions quickly; verify busy response if queue is full.
4. Timeout drill:
   - Trigger a long-running find; verify timeout response and audit event.
5. Observability drill:
   - Confirm `action_requested`, `action_executed`, and errors appear in audit log.

## Incident response quick steps
- Contain: `bash stopwork.sh`
- Collect artifacts:
  - `cp ~/.jarvis_audit/audit.jsonl ./incident-audit.jsonl`
  - `cp ~/.jarvis_audit/metrics.jsonl ./incident-metrics.jsonl`
- Verify no unsafe execution path exists:
  - `grep -n "shell=True" jarvis_clean.py`
- Recover by restarting with `bash workmode.sh` after triage.
