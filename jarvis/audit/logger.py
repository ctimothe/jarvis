"""Audit logger - optional logging for debugging and metrics."""

import json
import time
from pathlib import Path
from typing import Any

from jarvis.config import Config


class AuditLogger:
    """Optional audit and metrics logger."""

    def __init__(self, config: Config):
        self.config = config
        self._audit_dir = config.home_dir / ".jarvis_audit"
        self._audit_file = self._audit_dir / "audit.jsonl"
        self._metrics_file = self._audit_dir / "metrics.jsonl"

    def _ensure_dir(self) -> None:
        if self.config.privacy.audit_enabled:
            self._audit_dir.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, data: dict[str, Any]) -> None:
        """Log an event (only if audit_enabled)."""
        if not self.config.privacy.audit_enabled:
            return

        self._ensure_dir()
        payload = {
            "ts": time.time(),
            "event": event,
            **data,
        }
        with open(self._audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def metric(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Log a metric (only if metrics_enabled)."""
        if not self.config.privacy.metrics_enabled:
            return

        self._ensure_dir()
        payload = {
            "ts": time.time(),
            "name": name,
            "value": value,
            "tags": tags or {},
        }
        with open(self._metrics_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def log_action_request(self, request, decision) -> None:
        """Log an action request."""
        self.log("action_requested", {
            "request_id": request.request_id,
            "action": request.action,
            "principal": request.principal,
            "reason": request.reason,
            "allowed": decision.allowed,
            "reason_text": decision.reason,
        })

    def log_action_executed(self, request, result) -> None:
        """Log action execution result."""
        self.log("action_executed", {
            "request_id": request.request_id,
            "action": request.action,
            "ok": result.ok,
            "return_code": result.return_code,
            "duration_ms": result.duration_ms,
        })