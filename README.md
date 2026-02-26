Jarvis v2 - bounded autonomous task runner
- Runs a small, safe set of tasks in a loop
- Logs progress to run_logs/ and saves state to state.json
- Interrupt with Ctrl-C to gracefully stop; you can resume later
- Mission mode for multi-step shell actions with preview + explicit execute/cancel

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

Latency tuning:
- Default listen cue is a short beep (faster than spoken "Listening").
- Optional: `export JARVIS_LISTEN_CUE=speech` (old behavior) or `export JARVIS_LISTEN_CUE=none`.
