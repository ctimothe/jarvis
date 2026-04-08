"""Application control actions."""

import subprocess

from jarvis.actions.base import Action
from jarvis.types import ActionRequest, ActionResult
from jarvis import constants


def _run_safe_process(args: list[str], timeout: int = 10) -> ActionResult:
    """Run a subprocess safely."""
    import time
    started = time.time()
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        duration_ms = int((time.time() - started) * 1000)
        return ActionResult(
            ok=result.returncode == 0,
            return_code=result.returncode,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            duration_ms=duration_ms,
            command_repr=" ".join(args),
        )
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        return ActionResult(False, -1, "", str(exc), duration_ms, " ".join(args))


def _osascript(script: str) -> ActionResult:
    """Run osascript."""
    return _run_safe_process(["osascript", "-e", script])


class OpenAppAction(Action):
    name = constants.ACTION_OPEN_APP
    category = "apps"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        target = request.args.get("app", "")
        if not target:
            return ActionResult(False, 1, "", "No app specified.", 0, "open_app")

        result = _run_safe_process(["open", "-a", target])
        if result.ok:
            return ActionResult(True, 0, f"Opening {target}.", "", result.duration_ms, result.command_repr)

        fallback = _run_safe_process(["open", "-a", target])
        if fallback.ok:
            return ActionResult(True, 0, f"Opening {target}.", "", fallback.duration_ms, fallback.command_repr)

        return ActionResult(False, 1, "", f"I couldn't find an app called {target}.", 0, "open_app")

    def describe(self, request: ActionRequest) -> str:
        return f"open {request.args.get('app', '')}"


class QuitAppAction(Action):
    name = constants.ACTION_QUIT_APP
    category = "apps"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        app = request.args.get("app", "")
        if not app:
            return ActionResult(False, 1, "", "No app specified.", 0, "quit_app")

        script = f'tell application "{app}" to quit'
        result = _osascript(script)
        if result.ok:
            return ActionResult(True, 0, f"Quit {app}.", "", result.duration_ms, result.command_repr)
        return result

    def describe(self, request: ActionRequest) -> str:
        return f"quit app {request.args.get('app', '')}"


class FocusAppAction(Action):
    name = constants.ACTION_FOCUS_APP
    category = "apps"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        app = request.args.get("app", "")
        if not app:
            return ActionResult(False, 1, "", "No app specified.", 0, "focus_app")

        script = f'tell application "{app}" to activate'
        result = _osascript(script)
        if result.ok:
            return ActionResult(True, 0, f"Focused {app}.", "", result.duration_ms, result.command_repr)
        return result

    def describe(self, request: ActionRequest) -> str:
        return f"focus app {request.args.get('app', '')}"


class OpenUrlAction(Action):
    name = constants.ACTION_OPEN_URL
    category = "apps"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        url = request.args.get("url", "")
        if not url:
            return ActionResult(False, 1, "", "No URL specified.", 0, "open_url")

        result = _run_safe_process(["open", url])
        if result.ok:
            return ActionResult(True, 0, f"Opened {url}.", "", result.duration_ms, result.command_repr)
        return result

    def describe(self, request: ActionRequest) -> str:
        return f"open url {request.args.get('url', '')}"