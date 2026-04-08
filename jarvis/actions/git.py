"""Git actions."""

import subprocess
import time
import re

from jarvis.actions.base import Action
from jarvis.types import ActionRequest, ActionResult
from jarvis import constants


def _run_safe_process(args: list[str], timeout: int = constants.ACTION_TIMEOUT_SECONDS) -> ActionResult:
    """Run a subprocess safely with limits."""
    started = time.time()
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration_ms = int((time.time() - started) * 1000)
        return ActionResult(
            ok=result.returncode == 0,
            return_code=result.returncode,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            duration_ms=duration_ms,
            command_repr=" ".join(args),
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - started) * 1000)
        return ActionResult(False, -1, "", f"Timed out after {timeout}s", duration_ms, " ".join(args))
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        return ActionResult(False, -1, "", str(exc), duration_ms, " ".join(args))


class GitStatusAction(Action):
    name = constants.ACTION_GIT_STATUS
    category = "git"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        return _run_safe_process(["git", "-C", request.args["repo"], "status", "--short"])

    def describe(self, request: ActionRequest) -> str:
        return f"git status in {request.args.get('repo', '')}"


class GitDiffAction(Action):
    name = constants.ACTION_GIT_DIFF_STAT
    category = "git"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        return _run_safe_process(["git", "-C", request.args["repo"], "diff", "--stat"])

    def describe(self, request: ActionRequest) -> str:
        return f"git diff stat in {request.args.get('repo', '')}"


class GitLogAction(Action):
    name = constants.ACTION_GIT_LOG_RECENT
    category = "git"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        limit = request.args.get("limit", 5)
        return _run_safe_process(["git", "-C", request.args["repo"], "log", f"-n{limit}", "--oneline"])

    def describe(self, request: ActionRequest) -> str:
        limit = request.args.get("limit", 5)
        return f"git log last {limit} in {request.args.get('repo', '')}"


class GitBranchesAction(Action):
    name = constants.ACTION_GIT_BRANCHES
    category = "git"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        return _run_safe_process(["git", "-C", request.args["repo"], "branch", "--all", "--color=never"])

    def describe(self, request: ActionRequest) -> str:
        return f"git branches in {request.args.get('repo', '')}"


class GitRecentChangesAction(Action):
    name = constants.ACTION_GIT_RECENT_CHANGES
    category = "git"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        return _run_safe_process(["git", "-C", request.args["repo"], "diff", "--stat", "HEAD~1..HEAD"])

    def describe(self, request: ActionRequest) -> str:
        return f"recent changes since last commit in {request.args.get('repo', '')}"


class ProjectSearchAction(Action):
    name = constants.ACTION_PROJECT_SEARCH
    category = "dev"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        return _run_safe_process(
            ["rg", "--max-count", "200", "--no-heading", "--color", "never",
             request.args["pattern"], request.args["path"]],
            timeout=constants.ACTION_TIMEOUT_SECONDS,
        )

    def describe(self, request: ActionRequest) -> str:
        return f"search '{request.args.get('pattern', '')}' in {request.args.get('path', '')}"