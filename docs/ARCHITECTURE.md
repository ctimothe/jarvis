## Jarvis v2 architecture overview

Jarvis v2 is a **single-process macOS voice assistant**. There is no separate backend or client; everything runs inside `jarvis_clean.py` under a local Python process started by `workmode.sh`.

### High-level runtime

Voice turns follow a fixed pipeline:

```mermaid
flowchart TD
    trigger[Trigger\nHotkey or wake word]
    mic[SmartMic.listen\nVAD + STT]
    router[route()\nIntent + mission control]
    handler[Typed handlers\nopen/music/work_mode/system/shell]
    actions[Typed actions\nActionRequest → queue]
    tts[TTS\nmacOS say]

    trigger --> mic
    mic --> router
    router --> handler
    handler --> actions
    handler --> tts
    actions --> tts
```

- **Trigger**: hotkey (`Cmd+Shift+J`) and/or wake word (via `OpenWakeWordEngine` or `STTPhraseWakeWordEngine`) are managed by the `Jarvis` class.
- **SmartMic**: `SmartMic.listen()` uses WebRTC VAD to detect speech, with optional Apple native STT or local Whisper (`faster_whisper`) for transcription. It records per-turn capture metrics: `cue_to_speech_start_ms`, `speech_duration_ms`, and `speech_end_to_transcript_ms`.
- **Router**: `route(text)`:
  - handles mission control commands (`execute mission`, `cancel mission`, `mission report`) first
  - runs the **deterministic intent layer** (`_deterministic_intent_layer`) to send structured shell-style queries directly to `handle_shell`
  - falls back to `_quick_truth_response`, then to `_classify()` (rules → optional LLM) and named handlers.
- **Handlers**:
  - `handle_open` / `handle_music` / `handle_work_mode` / `handle_system` wrap macOS primitives (`open -a`, `osascript`, `pmset`) into fixed flows
  - `handle_shell` is the **typed action engine** used for all file, git, status, translation, and new dev/macOS control capabilities.
- **TTS**: `speak()` uses the macOS `say` CLI, with a global `_say_proc` so Jarvis can interrupt itself cleanly.

### Typed action engine and safety contract

The shell engine in `jarvis_clean.py` turns natural language into *typed* actions, enforced by a strict policy layer:

- **Core types**:
  - `ActionRequest`: `{ action: str, args: dict, principal: str, reason: str, ... }`
  - `PolicyDecision`: `{ allowed: bool, reason: str, requires_approval: bool }`
  - `ActionResult`: `{ ok: bool, return_code: int, stdout: str, stderr: str, duration_ms: int, command_repr: str }`
- **Parsing**:
  - `_build_action_request(query)` consumes the user’s utterance and returns a specific `ActionRequest` such as `ACTION_BATTERY_STATUS`, `ACTION_GIT_STATUS`, `ACTION_PROJECT_SEARCH`, `ACTION_SET_VOLUME_LEVEL`, etc.
  - `_build_mission_plan(query)` uses `_build_action_request` per step, splitting on connectors like `then`, `and then`, `;`, `->` to create a `MissionPlan` for multi-step missions.
- **Policy**:
  - `_policy_check(request)` enforces:
    - only actions in `SUPPORTED_ACTIONS` are allowed
    - a per-principal fixed-window rate limit (`FixedWindowRateLimiter`)
    - protected path rules: anything under system locations (like `/System`, `/bin`, `/Library/Apple`) is blocked
    - write restrictions: `WRITE_ACTIONS` may only write inside `HOME`
    - git restrictions: git actions (`ACTION_GIT_STATUS`, `ACTION_GIT_DIFF_STAT`, `ACTION_GIT_LOG_RECENT`, `ACTION_GIT_BRANCHES`, `ACTION_GIT_RECENT_CHANGES`) must run under `HOME`
    - search restrictions: `ACTION_PROJECT_SEARCH` must target a path under `HOME`
  - destructive actions (`ACTION_DELETE_PATH`) are listed in `DESTRUCTIVE_ACTIONS` and require a spoken approval gate via `_confirm_destructive_action()`.
- **Execution**:
  - `_execute_action_request(request)` is the **only** place that turns an action into concrete subprocess calls. It:
    - uses `_run_safe_process(args)` for all OS commands, with explicit argument lists (no `shell=True`) and CPU/file descriptor limits.
    - uses well-bounded helpers like `_run_battery_status_action`, `_run_volume_status_action`, `_run_now_playing_action`, `_run_wifi_status_action`, `_run_translate_action`, and the new dev/macOS helpers (git, project search, volume control, app control, open URL).
  - `_action_worker_loop()` pulls `ActionJob`s from a bounded `Queue`, runs each action with retries and backoff on timeouts, and updates `_failure_streak` plus local alerts when repeated failures occur.
- **Mission mode**:
  - `_preview_mission(plan)` checks all steps through `_policy_check()` without consuming rate limit and summarizes the plan using `_describe_action_request()`.
  - `_execute_mission_plan(plan)`:
    - re-checks each step with `_policy_check()`
    - enforces destructive approval gates
    - runs actions via the queue worker
    - accumulates a concise mission report and writes a `mission_executed` entry into the audit log.

This typed contract guarantees that:

- there is a single choke point for policy enforcement (`_policy_check`)
- a single place for OS-level side effects (`_execute_action_request`)
- `ask_ai()` and other LLM calls never perform actions themselves or claim to have done so.

### Observability: audit and metrics

Jarvis writes JSONL logs under `~/.jarvis_audit`:

- **Audit log** (`audit.jsonl` via `_audit()` and `_append_jsonl`):
  - events: `action_requested`, `action_executed`, `action_timeout`, `mission_executed`, and others
  - payloads include: `request_id`, `principal`, `action`, `args`, policy decisions, and clipped stderr output.
- **Metrics log** (`metrics.jsonl` via `_metric()`):
  - simple time-series metrics with fields `{ ts, name, value, tags }`
  - used by:
    - `_latency_metric()` to track stage-specific timing (e.g. `latency.stage_ms` for `cue_to_speech_start`, `speech_duration`, `speech_end_to_transcript`, `transcript_to_response`, `post_speech_to_response`, `roundtrip_total`)
    - `_local_alert()` to mark alerts
    - `_action_worker_loop()` to record `action.duration_ms` per action/attempt.

`Jarvis.activate()` uses these building blocks to produce a per-turn latency summary and metrics:

- records `capture` metrics from `SmartMic.last_capture_info`
- times the `route()` call to compute `transcript_to_response_ms`
- pushes `roundtrip_total` to `_metric`
- prints a structured `⏱  Turn:` line to the console when `JARVIS_SHOW_TURN_TIMERS` is enabled.

### Tests as executable specification

Two core test modules capture Jarvis’s behavioral and performance constraints:

- **`tests/test_action_policy.py`**:
  - stubs external dependencies (`requests`, `speech_recognition`, `pyaudio`, `webrtcvad`, `pynput`) before importing `jarvis_clean`, so tests don’t require a real mic/network.
  - asserts that `_build_action_request()` correctly parses a wide range of canonical queries into the intended actions, including:
    - file operations (create/list/find/move/copy/rename/delete)
    - status actions (battery, volume, song, wifi, time, active app)
    - translation queries
    - new daily-driver actions (git status/diff/log/branches/recent changes, project search, volume set/mute, quit/focus app, open URL).
  - validates policy behavior:
    - protected-path blocking
    - home-only write restrictions
    - destructive approval flags
    - git/search actions blocked outside `HOME`.
  - verifies mission behavior:
    - mission plan parsing and reasons
    - mission execute/cancel controls and pending state behavior.
  - enforces routing invariants:
    - deterministic layer short-circuits the classifier for canonical queries
    - rules-mode classifier does not fall back to LLM unnecessarily
    - quick truth responses (`how are you`, `wake up`, etc.) stay local and predictable.
- **`tests/test_perf_latency.py`**:
  - measures the **p50** and **p90** end-to-end route time for a canonical local status query (`is my laptop charging`) under stubbed dependencies.
  - enforces:
    - `p50 <= 1200ms`
    - `p90 <= 2000ms`
  - This keeps the core end-to-end experience fast even as new logic is added to `route()` or `handle_shell`.

Together, these tests form an executable specification for:

- how Jarvis maps natural language to action types
- which actions must be treated as structured and deterministic
- strict safety and policy guarantees
- acceptable latency budgets for the “local status” path.\n*** End Patch"}|()
