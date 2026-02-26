#!/usr/bin/env python3
from __future__ import annotations
import datetime
import json
import subprocess
import sys
from typing import Any, Dict


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Task:
    def __init__(self, name:str):
        self.name=name
    def run(self, state:Dict[str,object]) -> Dict[str,object]:
        raise NotImplementedError
    def describe(self) -> str:
        return f"Task: {self.name}"

class DependencyAudit(Task):
    def __init__(self): super().__init__('dependency_audit')
    def run(self, state:Dict[str,object]) -> Dict[str,object]:
        """Run a real dependency audit using pip list --outdated.
        Returns a structured report with a list of outdated packages.
        """
        try:
            # Use the active interpreter so venv invocation is always correct.
            cmd = [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode == 0 and proc.stdout.strip():
                try:
                    outdated: list[dict[str, Any]] = json.loads(proc.stdout)
                except Exception:
                    outdated = []
                return {"status": "ok", "interpreter": sys.executable, "outdated_packages": outdated}

            # Fallback to non-JSON output when JSON output is not available.
            cmd_fallback = [sys.executable, "-m", "pip", "list", "--outdated"]
            proc_fallback = subprocess.run(cmd_fallback, capture_output=True, text=True, check=False)
            if proc_fallback.returncode == 0:
                lines = [line for line in proc_fallback.stdout.splitlines() if line.strip()]
                return {
                    "status": "ok",
                    "interpreter": sys.executable,
                    "outdated_packages_text": lines,
                }

            return {
                "status": "error",
                "interpreter": sys.executable,
                "error": proc.stderr.strip() or proc_fallback.stderr.strip() or "pip audit failed",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

class MoodCapture(Task):
    def __init__(self): super().__init__('mood_capture')
    def run(self, state:Dict[str,object]) -> Dict[str,object]:
        mood = state.get('mood', 'neutral')
        entry = {'timestamp': utc_now_iso(), 'mood': mood}
        hist = state.get('mood_history', [])
        hist.append(entry)
        state['mood_history'] = hist
        return {'status':'ok','mood_recorded':entry}

class SelfImprovementBacklog(Task):
    def __init__(self): super().__init__('self_improvement_backlog')
    def run(self, state:Dict[str,object]) -> Dict[str,object]:
        # Generate a tiny backlog item and append to backlog in state
        backlog = state.get('improvement_backlog', [])
        item = {
            'id': f'auto-{len(backlog)+1}',
            'desc': 'Propose a non-destructive improvement (docs, comments, README, small refactor)',
            'created_at': utc_now_iso(),
            'status': 'backlog'
        }
        backlog.append(item)
        state['improvement_backlog'] = backlog
        return {'status':'ok','backlog_item':item}

TASKS = [DependencyAudit(), MoodCapture(), SelfImprovementBacklog()]
