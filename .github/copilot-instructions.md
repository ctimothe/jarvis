# Copilot Instructions for `jarvis_v2`

## Project shape (read this first)
- This repo is a **single-runtime Python voice assistant** centered in `jarvis_clean.py`.
- `workmode.sh` is the canonical launcher: it bootstraps `.venv`, installs deps, patches `webrtcvad` for Python 3.14+, then runs `jarvis_clean.py`.
- `status.sh` and `stopwork.sh` are operational helpers for checking/stopping a running Jarvis process.
- There is no backend/frontend split here; avoid adding framework scaffolding unless explicitly requested.

## Core runtime flow in `jarvis_clean.py`
- Input pipeline: hotkey (`Command+Shift+J`) → `SmartMic.listen()` (WebRTC VAD) → Google STT.
- Routing pipeline: `route()` → `_classify()` intent (LLM-first with offline keyword fallback).
- Action handlers: `handle_open`, `handle_music`, `handle_work_mode`, `handle_system`, `handle_shell`.
- AI text responses: `ask_ai()` uses strict prompts to avoid action hallucinations.
- Shell-intent execution is now **typed actions only** (no free-form command generation).

## Safety-critical patterns (do not weaken)
- Keep the typed contract (`ActionRequest`, `PolicyDecision`, `ActionResult`) as the only shell-action path.
- Never re-introduce `shell=True` or LLM-generated raw command execution.
- Enforce policy via `_policy_check()` before queueing any action.
- Keep protected-path and home-directory write restrictions for file-system actions.
- Destructive operations (`delete_path`) must keep spoken approval in `handle_shell()`.
- Preserve the invariant: only Python handlers perform actions; `ask_ai()` must never claim actions were executed.

## Platform and dependency assumptions
- macOS-first implementation (`say`, `osascript`, `open`, `pmset`, Spotify AppleScript).
- Ollama endpoint is local (`http://localhost:11434`) and model default is `llama3.1:8b`.
- Python deps are installed by `workmode.sh`; prefer updating that script over ad-hoc install docs.

## Developer workflows
- Run assistant: `bash workmode.sh`
- Check runtime health: `bash status.sh`
- Stop running assistant: `bash stopwork.sh`
- Syntax-check Python quickly: `.venv/bin/python3 -c "import ast,pathlib; ast.parse(pathlib.Path('jarvis_clean.py').read_text()); print('Syntax OK')"`
- Syntax-check shell scripts: `bash -n workmode.sh status.sh stopwork.sh`
- Inspect local audit log: `tail -n 40 ~/.jarvis_audit/audit.jsonl`
- Inspect local metrics log: `tail -n 40 ~/.jarvis_audit/metrics.jsonl`

## Editing conventions for this repo
- Keep changes minimal and localized to existing functions/sections in `jarvis_clean.py`.
- Prefer extending `KNOWN_APPS` and handler maps over introducing new routing systems.
- Maintain spoken-output style: concise, plain-language strings suitable for TTS.
- If changing intent behavior, update both `_INTENT_SYSTEM` and fallback logic in `_classify()` together.
- If adding shell capabilities, implement as a new typed action and wire parser + policy + executor together.
