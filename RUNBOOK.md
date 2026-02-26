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
