#!/usr/bin/env python3
"""
Jarvis v2 - Bounded autonomous task runner scaffold
- Safe, bounded loop
- Simple self-improvement task skeleton
- Logs progress to run_logs/
- Can be interrupted gracefully
"""

from __future__ import annotations
import logging
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import subprocess
import shutil
import re
import os # For path joining and existence checks

ROOT = Path("/Users/ctimothe/Desktop/code/jarvis_v2").resolve()
LOG_DIR = ROOT / "run_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "runner.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(str(LOG_FILE)), logging.StreamHandler()],
)

STATE_FILE = ROOT / "state.json"

# Helper to find Python executable
def get_python_executable():
    return shutil.which("python") or shutil.which("python3") or "python" # Fallback

# --- Base Task Structure ---
class Task:
    def __init__(self, name: str):
        self.name = name
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
    def describe(self) -> str:
        return f"Task: {self.name}"

# --- Dynamically Imported Tasks ---
DEV_TASKS_AVAILABLE = False
try:
    # Ensure the dev_tasks module is importable
    from dev_tasks import DependencyAudit, MoodCapture, SelfImprovementBacklog
    DEV_TASKS_AVAILABLE = True
    logging.info("Successfully imported custom tasks from dev_tasks.py")
except ImportError as e:
    logging.error(f"Failed to import tasks from dev_tasks. Error: {e}. Please ensure dev_tasks.py and its dependencies are correct.")
    # Define dummy classes as fallbacks if import fails
    class DependencyAudit(Task):
        def __init__(self): super().__init__('dependency_audit')
        def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "error", "error": "Task module not loaded or failed to import"}
    class MoodCapture(Task):
        def __init__(self): super().__init__('mood_capture')
        def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "error", "error": "Task module not loaded or failed to import"}
    class SelfImprovementBacklog(Task):
        def __init__(self): super().__init__('self_improvement_backlog')
        def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "error", "error": "Task module not loaded or failed to import"}

# --- Placeholder Tasks for Base Functionality ---
class LintTask(Task):
    def __init__(self): super().__init__("lint")
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "improvement": "lint-check-complete", "details": "Placeholder lint check"}

class PruneEnvTask(Task):
    def __init__(self): super().__init__("prune_env")
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "improvement": "env-audit-complete", "details": "Placeholder env prune"}

class FetchAPITask(Task):
    def __init__(self): super().__init__("fetch_api")
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        summary = {"note": "Simulated API fetch - no network in this sandbox", "fetched_at": datetime.datetime.utcnow().isoformat()}
        return {"status": "ok", "summary": summary}

# --- Task List ---
# Dynamically build TASKS list based on available imports
TASKS: List[Task] = [LintTask(), PruneEnvTask(), FetchAPITask()]
if DEV_TASKS_AVAILABLE:
    TASKS.append(DependencyAudit())
    TASKS.append(MoodCapture())
    TASKS.append(SelfImprovementBacklog())
else:
    logging.warning("Custom dev_tasks not available. Runner will only use placeholder tasks.")


# ----------------------------
# State management
# ----------------------------
def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure essential keys exist, add if missing, and provide defaults
                data['version'] = data.get('version', 1)
                data['pos'] = data.get('pos', 0)
                data['history'] = data.get('history', [])
                data['mood'] = data.get('mood', 'neutral') # Initialize or preserve mood
                data['mood_history'] = data.get('mood_history', [])
                data['improvement_backlog'] = data.get('improvement_backlog', [])
                return data
        except Exception as e:
            logging.warning(f"Failed to load state from {STATE_FILE}: {e}. Initializing fresh state.")
    # Initialize state with default values if file not found or corrupted
    return {
        "version": 1,
        "pos": 0,
        "history": [],
        "mood": "neutral", # Default mood
        "mood_history": [],
        "improvement_backlog": []
    }

def save_state(state: Dict[str, Any]) -> None:
    try:
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save state to {STATE_FILE}: {e}")

# ----------------------------
# Run loop
# ----------------------------
def main():
    logging.info("Jarvis v2 runner starting...")
    state = load_state()
    pos = state.get("pos", 0)

    MAX_STEPS_PER_RUN = 10 # Number of tasks to execute in a single pass

    steps_taken_in_this_run = 0
    try:
        # Ensure pos is within bounds of available tasks, or reset to 0 if it's past the end
        if pos >= len(TASKS) and len(TASKS) > 0:
            logging.warning(f"Current position {pos} is beyond task list length {len(TASKS)}. Resetting to 0 for new tasks.")
            pos = 0
            state["pos"] = 0

        while pos < len(TASKS) and steps_taken_in_this_run < MAX_STEPS_PER_RUN:
            task_to_run = TASKS[pos]
            logging.info(f"Starting task {pos+1}/{len(TASKS)}: {task_to_run.describe()}")
            
            result = task_to_run.run(state) 

            entry = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "task": task_to_run.name,
                "result": result,
            }
            state["history"].append(entry)

            if result.get("status") != "ok":
                logging.warning(f"Task '{task_to_run.name}' reported non-ok status: {result.get('error', result.get('status'))}. Breaking loop.")
                break # Stop on first non-ok task

            pos += 1 # Move to next task index
            state["pos"] = pos # Update resume position
            save_state(state) # Save state after each successful task
            steps_taken_in_this_run += 1 # Increment counter for current run

        logging.info("Run loop finished this pass. %d tasks executed.", steps_taken_in_this_run)
    except KeyboardInterrupt:
        logging.info("Interrupted by user. Saving state and exiting gracefully.")
        save_state(state) 
        return
    except Exception as e:
        logging.exception(f"Unexpected error occurred during task execution: {e}")
        save_state(state) 

    logging.info("Jarvis v2 runner finished this pass. Next run will resume from task position %d.", pos)

if __name__ == "__main__":
    main()
