# Copilot instructions for `jarvis_v2`

## Architecture at a glance
- This is a **single-process macOS voice assistant**, not a client/server app. Core runtime is `jarvis_clean.py`.
- Main flow: trigger (`Command+Shift+J` or wake word) → `SmartMic.listen()` → `route()` → typed handlers (`handle_open|music|work_mode|system|shell`) → TTS via `say`.
- Deterministic shell path takes priority: `route()` checks `_deterministic_intent_layer()` before classifier/LLM.
- `runner.py` + `dev_tasks.py` are a separate bounded autonomous loop (stateful task pass over `state.json`), not part of the live voice loop.

## Safety invariants (must preserve)
- Keep typed action contract only: `ActionRequest` → `_policy_check()` → queue dispatch → `ActionResult`.
- Do **not** reintroduce raw command generation or `shell=True`; execution must stay in `_execute_action_request()` with explicit argument lists.
- Preserve policy gates in `_policy_check()`: protected paths, write-inside-home restriction, git path restriction, and per-principal rate limit.
- Destructive actions (`ACTION_DELETE_PATH`) must continue to require spoken confirmation via `_confirm_destructive_action()`.
- `ask_ai()` must never imply actions were executed; only Python handlers execute system changes.

## Extension pattern for new shell capabilities
- Add action constant + include in `SUPPORTED_ACTIONS` (and `WRITE_ACTIONS`/`DESTRUCTIVE_ACTIONS` if applicable).
- Parse in `_build_action_request()` and add a human summary in `_describe_action_request()`.
- Enforce constraints in `_policy_check()`.
- Implement execution in `_execute_action_request()` (or dedicated `_run_*_action`).
- Ensure output remains TTS-friendly through `_format_action_result()`.
- Example already in tree: translation flow (`ACTION_TRANSLATE_TEXT`, `_parse_translation_request`, `_run_translate_action`).

## Mission mode + observability
- Multi-step missions are parsed by `_build_mission_plan()` using connectors like `then`, `and then`, `;`, `->`, previewed by `_preview_mission()`, executed by `_execute_mission_plan()`.
- Keep mission controls stable: `execute mission`, `cancel mission`, `mission report`.
- Preserve audit/metrics writes to `~/.jarvis_audit/audit.jsonl` and `~/.jarvis_audit/metrics.jsonl` via `_audit()` / `_metric()`.

## Developer workflows
- Canonical start: `bash workmode.sh` (creates `.venv`, installs deps, patches `webrtcvad`, launches Jarvis).
- Runtime ops: `bash status.sh`, `bash stopwork.sh`, `bash scripts/reset_state.sh`.
- Fast checks: `.venv/bin/python3 -m pytest -q`, `bash -n workmode.sh status.sh stopwork.sh`.
- Syntax sanity check: `.venv/bin/python3 -c "import ast,pathlib; ast.parse(pathlib.Path('jarvis_clean.py').read_text()); print('Syntax OK')"`.

## Test conventions in this repo
- `tests/test_action_policy.py` stubs audio/network deps (`requests`, `speech_recognition`, `pyaudio`, `webrtcvad`, `pynput`) before importing `jarvis_clean`; follow this pattern for new tests.
- Keep tests focused on policy/parser/route latency and deterministic behavior (see `tests/test_perf_latency.py`).

## Platform assumptions
- macOS-first commands and integrations are intentional (`say`, `osascript`, `pmset`, `networksetup`, AppleScript for Spotify/Music, `open -a Ollama`).
- Default local model endpoint is `http://localhost:11434` with model `llama3.1:8b`.
