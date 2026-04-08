"""LLM registry - manages LLM backends."""

import re

from jarvis.config import Config
from jarvis.llm.base import LLMBackend, NullLLMBackend
from jarvis.llm.ollama import OllamaBackend


class LLMRegistry:
    """Registry for LLM backends."""

    def __init__(self, config: Config):
        self.config = config
        self._backends: dict[str, LLMBackend] = {}
        self._default_backend_name = config.llm.backend
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register built-in backends."""
        # Register Null backend (always available)
        self._backends["null"] = NullLLMBackend(
            fallback=self.config.llm.fallback_response
        )

        # Register Ollama (if available)
        if self.config.llm.backend == "ollama":
            self._backends["ollama"] = OllamaBackend(
                url=self.config.llm.url,
                model=self.config.llm.model,
                temperature=self.config.llm.temperature,
            )

    def get_backend(self, name: str | None = None) -> LLMBackend:
        """Get a backend by name, or the default."""
        backend_name = name or self._default_backend_name
        backend = self._backends.get(backend_name)

        if backend is None:
            # Fallback to null
            return self._backends["null"]

        # Check if it's actually available
        if not backend.is_available():
            # Try to fall back
            for fallback_name, fallback_backend in self._backends.items():
                if fallback_name != backend_name and fallback_backend.is_available():
                    return fallback_backend
            # Return null
            return self._backends["null"]

        return backend

    def list_backends(self) -> list[tuple[str, bool]]:
        """List all available backends with availability status."""
        result = []
        for name, backend in self._backends.items():
            result.append((name, backend.is_available()))
        return result


# Global registry instance
_registry: LLMRegistry | None = None


def get_llm_registry(config: Config | None = None) -> LLMRegistry:
    """Get the global LLM registry."""
    global _registry
    if _registry is None:
        from jarvis.config import get_config
        config = config or get_config()
        _registry = LLMRegistry(config)
    return _registry