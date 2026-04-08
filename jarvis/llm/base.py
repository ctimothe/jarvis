"""LLM backend base classes and protocols."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Response from an LLM backend."""
    content: str
    model: str
    duration_ms: int
    tokens: int | None = None


class LLMBackend(ABC):
    """Base class for LLM backends."""

    name: str = ""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 200,
        stop: list[str] | None = None,
    ) -> str:
        """Complete a prompt and return the response text."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available."""
        pass

    def configure(self, **kwargs) -> None:
        """Configure the backend. Override in subclasses."""
        pass


class NullLLMBackend(LLMBackend):
    """Null backend that always returns a fallback message."""

    name = "null"

    def __init__(self, fallback: str = "AI is unavailable."):
        self._fallback = fallback

    def complete(self, prompt: str, system: str | None = None, temperature: float = 0.3, max_tokens: int = 200, stop: list[str] | None = None) -> str:
        return self._fallback

    def is_available(self) -> bool:
        return True