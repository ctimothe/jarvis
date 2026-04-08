"""Action base classes and protocols."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from jarvis.types import ActionRequest, ActionResult


class Action(ABC):
    """Base class for all actions."""

    name: str = ""
    category: str = ""
    requires_approval: bool = False
    is_destructive: bool = False

    @abstractmethod
    def execute(self, request: ActionRequest) -> ActionResult:
        """Execute the action with the given request."""
        pass

    def validate_args(self, args: dict[str, Any]) -> bool:
        """Validate action arguments. Override in subclasses."""
        return True

    def describe(self, request: ActionRequest) -> str:
        """Return a human-readable description of the action."""
        return f"{self.name}: {request.args}"

    def supports(self, action_name: str) -> bool:
        """Check if this action handles the given action name."""
        return self.name == action_name


class ActionRegistry:
    """Registry of all available actions."""

    def __init__(self):
        self._actions: dict[str, Action] = {}

    def register(self, action: Action) -> None:
        """Register an action."""
        self._actions[action.name] = action

    def get(self, name: str) -> Action | None:
        """Get an action by name."""
        return self._actions.get(name)

    def list_all(self) -> list[Action]:
        """List all registered actions."""
        return list(self._actions.values())

    def execute(self, request: ActionRequest) -> ActionResult:
        """Execute an action by name."""
        action = self.get(request.action)
        if not action:
            return ActionResult(
                ok=False,
                return_code=-1,
                stdout="",
                stderr=f"Unknown action: {request.action}",
                duration_ms=0,
                command_repr=request.action,
            )

        # Validate args
        if not action.validate_args(request.args):
            return ActionResult(
                ok=False,
                return_code=1,
                stdout="",
                stderr="Invalid arguments",
                duration_ms=0,
                command_repr=request.action,
            )

        return action.execute(request)

    def parse(self, text: str) -> ActionRequest | None:
        """Parse text into an ActionRequest using registered actions."""
        # This will be implemented in the parser
        from jarvis.actions.parser import ActionParser
        parser = ActionParser(self)
        return parser.parse(text)


# Global registry instance
_registry: ActionRegistry | None = None


def get_action_registry() -> ActionRegistry:
    """Get the global action registry."""
    global _registry
    if _registry is None:
        _registry = ActionRegistry()
        _register_default_actions(_registry)
    return _registry


def _register_default_actions(registry: ActionRegistry) -> None:
    """Register all built-in actions."""
    from jarvis.actions.filesystem import (
        CreateFolderAction,
        CreateFileAction,
        ListPathAction,
        FindNameAction,
        MovePathAction,
        CopyPathAction,
        RenamePathAction,
        DeletePathAction,
    )
    from jarvis.actions.git import (
        GitStatusAction,
        GitDiffAction,
        GitLogAction,
        GitBranchesAction,
        GitRecentChangesAction,
        ProjectSearchAction,
    )
    from jarvis.actions.system import (
        BatteryStatusAction,
        VolumeStatusAction,
        SetVolumeAction,
        ToggleMuteAction,
        NowPlayingAction,
        WifiStatusAction,
        TimeStatusAction,
        ActiveAppAction,
        TranslateTextAction,
    )
    from jarvis.actions.apps import (
        OpenAppAction,
        QuitAppAction,
        FocusAppAction,
        OpenUrlAction,
    )

    actions = [
        # Filesystem
        CreateFolderAction(),
        CreateFileAction(),
        ListPathAction(),
        FindNameAction(),
        MovePathAction(),
        CopyPathAction(),
        RenamePathAction(),
        DeletePathAction(),
        # Git
        GitStatusAction(),
        GitDiffAction(),
        GitLogAction(),
        GitBranchesAction(),
        GitRecentChangesAction(),
        ProjectSearchAction(),
        # System
        BatteryStatusAction(),
        VolumeStatusAction(),
        SetVolumeAction(),
        ToggleMuteAction(),
        NowPlayingAction(),
        WifiStatusAction(),
        TimeStatusAction(),
        ActiveAppAction(),
        TranslateTextAction(),
        # Apps
        OpenAppAction(),
        QuitAppAction(),
        FocusAppAction(),
        OpenUrlAction(),
    ]

    for action in actions:
        registry.register(action)