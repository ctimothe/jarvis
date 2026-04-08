"""Plugin base classes."""

from abc import ABC, abstractmethod
from typing import Any


class Plugin(ABC):
    """Base class for all plugins."""

    name: str = ""
    version: str = "1.0.0"

    @abstractmethod
    def register(self, app: "JarvisApp") -> None:
        """Register the plugin with the Jarvis app."""
        pass

    def configure(self, config: dict[str, Any]) -> None:
        """Configure the plugin with settings."""
        pass

    def initialize(self) -> None:
        """Initialize the plugin. Called after registration."""
        pass

    def shutdown(self) -> None:
        """Cleanup when shutting down."""
        pass


class ActionPlugin(Plugin):
    """Plugin that adds custom actions."""

    @abstractmethod
    def get_actions(self) -> list:
        """Return list of action instances to register."""
        pass


class STTPlugin(Plugin):
    """Plugin that adds a custom STT backend."""

    @abstractmethod
    def get_backend(self):
        """Return an STT backend instance."""
        pass


class TTSPlugin(Plugin):
    """Plugin that adds a custom TTS backend."""

    @abstractmethod
    def get_backend(self):
        """Return a TTS backend instance."""
        pass


class LLMPlugin(Plugin):
    """Plugin that adds a custom LLM backend."""

    @abstractmethod
    def get_backend(self):
        """Return an LLM backend instance."""
        pass


class JarvisApp:
    """Main application that plugins register with."""

    def __init__(self):
        self._actions = {}
        self._stt_backends = {}
        self._tts_backends = {}
        self._llm_backends = {}

    def register_action(self, action) -> None:
        """Register an action."""
        self._actions[action.name] = action

    def register_stt(self, name: str, backend) -> None:
        """Register an STT backend."""
        self._stt_backends[name] = backend

    def register_tts(self, name: str, backend) -> None:
        """Register a TTS backend."""
        self._tts_backends[name] = backend

    def register_llm(self, name: str, backend) -> None:
        """Register an LLM backend."""
        self._llm_backends[name] = backend