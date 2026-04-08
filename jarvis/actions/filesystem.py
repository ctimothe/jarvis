"""Filesystem actions."""

import subprocess
import time
import os
from pathlib import Path

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


class CreateFolderAction(Action):
    name = constants.ACTION_CREATE_FOLDER
    category = "fs"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        return _run_safe_process(["mkdir", "-p", request.args["path"]])

    def describe(self, request: ActionRequest) -> str:
        return f"create folder {request.args.get('path', '')}"


class CreateFileAction(Action):
    name = constants.ACTION_CREATE_FILE
    category = "fs"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        return _run_safe_process(["touch", request.args["path"]])

    def describe(self, request: ActionRequest) -> str:
        return f"create file {request.args.get('path', '')}"


class ListPathAction(Action):
    name = constants.ACTION_LIST_PATH
    category = "fs"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        return _run_safe_process(["ls", "-la", request.args["path"]])

    def describe(self, request: ActionRequest) -> str:
        return f"list {request.args.get('path', '')}"


class FindNameAction(Action):
    name = constants.ACTION_FIND_NAME
    category = "fs"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        return _run_safe_process(
            ["find", request.args["path"], "-maxdepth", "4", "-name", request.args["pattern"]]
        )

    def describe(self, request: ActionRequest) -> str:
        return f"find {request.args.get('pattern', '')} in {request.args.get('path', '')}"


class MovePathAction(Action):
    name = constants.ACTION_MOVE_PATH
    category = "fs"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        return _run_safe_process(["mv", request.args["src"], request.args["dst"]])

    def describe(self, request: ActionRequest) -> str:
        return f"move {request.args.get('src', '')} to {request.args.get('dst', '')}"


class CopyPathAction(Action):
    name = constants.ACTION_COPY_PATH
    category = "fs"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        return _run_safe_process(["cp", "-R", request.args["src"], request.args["dst"]])

    def describe(self, request: ActionRequest) -> str:
        return f"copy {request.args.get('src', '')} to {request.args.get('dst', '')}"


class RenamePathAction(Action):
    name = constants.ACTION_RENAME_PATH
    category = "fs"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        return _run_safe_process(["mv", request.args["src"], request.args["dst"]])

    def describe(self, request: ActionRequest) -> str:
        return f"rename {request.args.get('src', '')} to {request.args.get('dst', '')}"


class DeletePathAction(Action):
    name = constants.ACTION_DELETE_PATH
    category = "fs"
    requires_approval = True
    is_destructive = True

    def execute(self, request: ActionRequest) -> ActionResult:
        script = f'tell app "Finder" to delete POSIX file "{request.args["path"]}"'
        return _run_safe_process(["osascript", "-e", script])

    def describe(self, request: ActionRequest) -> str:
        path = request.args.get("path", "")
        shortened = path if len(path) <= 80 else path[:77] + "..."
        return f"delete {shortened}"


class DiskUsageAction(Action):
    name = constants.ACTION_DISK_USAGE
    category = "fs"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        home = os.path.expanduser("~")
        return _run_safe_process(["df", "-h", home])

    def describe(self, request: ActionRequest) -> str:
        return "check disk usage"