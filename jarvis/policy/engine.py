"""Policy engine - evaluates action requests against security policies."""

import os
from pathlib import Path

from jarvis.config import Config
from jarvis.types import ActionRequest, PolicyDecision as TypePolicyDecision
from jarvis import constants
from jarvis.policy.rate_limiter import RateLimiter


class PolicyEngine:
    """Evaluates action requests against security policies."""

    def __init__(self, config: Config):
        self.config = config
        self.rate_limiter = RateLimiter(config.security.rate_limit_per_minute)
        self._protected_paths = constants.PROTECTED_PATHS

    def evaluate(self, request: ActionRequest, consume_rate_limit: bool = True) -> TypePolicyDecision:
        """Evaluate if the action should be allowed."""
        # Check rate limit
        if consume_rate_limit:
            allowed, retry_after = self.rate_limiter.allow(request.principal)
            if not allowed:
                return TypePolicyDecision(False, f"rate limit exceeded; retry in {retry_after}s")

        # Check if action is supported
        if request.action not in constants.SUPPORTED_ACTIONS:
            return TypePolicyDecision(False, f"unsupported action: {request.action}")

        # Check path protections
        check_paths = self._get_check_paths(request)
        for path in check_paths:
            if self._is_protected(path):
                return TypePolicyDecision(False, f"protected path blocked: {path}")

        # Check write scope restriction
        if request.action in constants.WRITE_ACTIONS:
            for path in check_paths:
                if not self._is_under_home(path):
                    return TypePolicyDecision(False, f"write action outside home blocked: {path}")

        # Check git scope restriction
        if request.action in {
            constants.ACTION_GIT_STATUS,
            constants.ACTION_GIT_DIFF_STAT,
            constants.ACTION_GIT_LOG_RECENT,
            constants.ACTION_GIT_BRANCHES,
            constants.ACTION_GIT_RECENT_CHANGES,
        }:
            repo = request.args.get("repo", "")
            if repo and not self._is_under_home(repo):
                return TypePolicyDecision(False, "git command outside home blocked")

        # Check project search scope
        if request.action == constants.ACTION_PROJECT_SEARCH:
            root = request.args.get("path", "")
            if root and not self._is_under_home(root):
                return TypePolicyDecision(False, "project search outside home blocked")

        # Check if approval is required for destructive actions
        requires_approval = request.action in constants.DESTRUCTIVE_ACTIONS and self.config.security.require_approval_for_destructive

        return TypePolicyDecision(True, "allowed", requires_approval=requires_approval)

    def _get_check_paths(self, request: ActionRequest) -> list[str]:
        """Get paths to check from request args."""
        paths = []
        for key in ("path", "src", "dst", "repo"):
            value = request.args.get(key)
            if isinstance(value, str):
                paths.append(value)
        return paths

    def _is_protected(self, path: str) -> bool:
        """Check if path is protected."""
        resolved = str(Path(path).resolve())
        for protected in self._protected_paths:
            if resolved == protected or resolved.startswith(protected + "/"):
                return True
        return False

    def _is_under_home(self, path: str) -> bool:
        """Check if path is under user's home directory."""
        if not path:
            return True
        resolved = str(Path(path).resolve())
        home_resolved = str(Path.home().resolve())
        return resolved == home_resolved or resolved.startswith(home_resolved + "/")


class PolicyDecision:
    """Result of policy evaluation."""

    def __init__(self, allowed: bool, reason: str, requires_approval: bool = False):
        self.allowed = allowed
        self.reason = reason
        self.requires_approval = requires_approval