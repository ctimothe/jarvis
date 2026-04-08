"""Core types for Jarvis."""

from dataclasses import dataclass, field
from typing import Any
import uuid


@dataclass
class ActionRequest:
    """A request to execute an action."""
    action: str
    args: dict[str, Any]
    principal: str
    reason: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=lambda: __import__("time").time())


@dataclass
class PolicyDecision:
    """Result of policy evaluation."""
    allowed: bool
    reason: str
    requires_approval: bool = False


@dataclass
class ActionResult:
    """Result of action execution."""
    ok: bool
    return_code: int
    stdout: str
    stderr: str
    duration_ms: int
    command_repr: str


@dataclass
class ActionJob:
    """A job in the action queue."""
    request: ActionRequest
    done: Any = field(default_factory=lambda: __import__("threading").Event())
    result: ActionResult | None = None


@dataclass
class MissionPlan:
    """A multi-step mission plan."""
    mission_id: str
    requests: list[ActionRequest]
    created_at: float = field(default_factory=lambda: __import__("time").time())


@dataclass
class CaptureInfo:
    """Audio capture metadata."""
    cue_to_speech_start_ms: int = 0
    speech_end_to_transcript_ms: int = 0
    speech_duration_ms: int = 0


@dataclass
class LatencyMetrics:
    """Latency measurements for a turn."""
    cue_to_speech_start_ms: int = 0
    speech_duration_ms: int = 0
    speech_end_to_transcript_ms: int = 0
    transcript_to_response_ms: int = 0
    post_speech_to_response_ms: int = 0
    total_ms: int = 0


@dataclass
class HealthStatus:
    """Health check result for a backend."""
    name: str
    available: bool
    error_message: str | None = None
    latency_ms: int | None = None
    suggestions: list[str] = field(default_factory=list)


@dataclass
class SystemInfo:
    """System information snapshot."""
    battery_percent: int | None = None
    battery_charging: bool = False
    battery_health_percent: int | None = None
    cycle_count: int | None = None
    volume_percent: int = 0
    volume_muted: bool = False
    wifi_ssid: str | None = None
    current_time: str = ""
    active_app: str | None = None
    now_playing: str | None = None