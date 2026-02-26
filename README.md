Jarvis v2 - bounded autonomous task runner
- Runs a small, safe set of tasks in a loop
- Logs progress to run_logs/ and saves state to state.json
- Interrupt with Ctrl-C to gracefully stop; you can resume later

Quick commands:
- Start voice assistant: `bash workmode.sh`
- Check health: `bash status.sh`
- Stop assistant: `bash stopwork.sh`
- Reset local runner state/logs: `bash scripts/reset_state.sh`
- Run tests: `.venv/bin/python3 -m pytest -q`
