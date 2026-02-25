#!/usr/bin/env python3
from __future__ import annotations
import json
import datetime
from pathlib import Path
from typing import Dict

ROOT = Path('/Users/ctimothe/Desktop/code/jarvis_v2').resolve()
STATE = ROOT / 'state.json'
LOG = ROOT / 'run_logs' / 'dev_tasks.log'

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
            # Prefer JSON output if available for easier parsing
            cmd = ["python", "-m", "pip", "list", "--outdated", "--format=json"]
            import subprocess
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode == 0:
                try:
                    outdated = __import__('json').loads(proc.stdout) if proc.stdout.strip() else []
                except Exception:
                    outdated = []
            else:
                cmd2 = ["python", "-m", "pip", "list", "--outdated"]
                proc2 = subprocess.run(cmd2, capture_output=True, text=True, check=False)
                outdated = proc2.stdout.splitlines() if proc2.returncode == 0 else []
            return {"status": "ok", "outdated_packages": outdated}
        except Exception as e:
            return {"status": "error", "error": str(e)}

class MoodCapture(Task):
    def __init__(self): super().__init__('mood_capture')
    def run(self, state:Dict[str,object]) -> Dict[str,object]:
        mood = state.get('mood', 'neutral')
        entry = {'timestamp': datetime.datetime.utcnow().isoformat(), 'mood': mood}
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
            'created_at': datetime.datetime.utcnow().isoformat(),
            'status': 'backlog'
        }
        backlog.append(item)
        state['improvement_backlog'] = backlog
        return {'status':'ok','backlog_item':item}

TASKS = [DependencyAudit(), MoodCapture(), SelfImprovementBacklog()]
