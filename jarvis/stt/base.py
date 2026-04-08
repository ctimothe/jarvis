"""STT backend base protocol."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from jarvis.types import CaptureInfo


@dataclass
class ListenResult:
    """Result of a listen operation."""
    text: str
    capture_info: CaptureInfo


class STTBackend(ABC):
    """Base class for speech-to-text backends."""

    name: str = ""

    @abstractmethod
    def listen(
        self,
        max_record_seconds: int = 30,
        startup_timeout_s: int = 8,
        announce: bool = True,
    ) -> str:
        """Listen for speech and return transcribed text."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available."""
        pass

    def close(self) -> None:
        """Cleanup resources. Override in subclasses."""
        pass


class NullSTTBackend(STTBackend):
    """Null STT that returns empty strings."""

    name = "null"

    def listen(self, max_record_seconds: int = 30, startup_timeout_s: int = 8, announce: bool = True) -> str:
        return ""

    def is_available(self) -> bool:
        return True