"""Ollama LLM backend."""

import time
import requests

from jarvis.llm.base import LLMBackend, LLMResponse


class OllamaBackend(LLMBackend):
    """Ollama LLM backend."""

    name = "ollama"

    def __init__(self, url: str = "http://localhost:11434", model: str = "llama3.1:8b", temperature: float = 0.3):
        self.url = url
        self.model = model
        self.temperature = temperature

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 200,
        stop: list[str] | None = None,
    ) -> str:
        """Complete using Ollama."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": 0.9,
                "stop": stop or ["User:", "Human:", "\nUser", "\nHuman", "Assistant:"],
            },
        }

        try:
            start = time.time()
            response = requests.post(f"{self.url}/api/chat", json=payload, timeout=40)
            duration_ms = int((time.time() - start) * 1000)

            if response.status_code == 200:
                data = response.json()
                content = data.get("message", {}).get("content", "").strip()
                # Clean up any leftover prompt artifacts
                content = self._clean_response(content)
                return content
            else:
                return f"Ollama error {response.status_code}."
        except requests.exceptions.Timeout:
            return "The AI took too long, please try again."
        except Exception as e:
            return f"AI error: {e}"

    def _clean_response(self, content: str) -> str:
        """Clean up response from model artifacts."""
        import re
        # Remove any remaining User: or Human: prompts
        content = re.split(r'\n(?:User|Human|Assistant)\s*:', content, maxsplit=1)[0].strip()
        return content

    def is_available(self) -> bool:
        """Check if Ollama is running."""
        try:
            response = requests.get(f"{self.url}/api/tags", timeout=3)
            return response.status_code == 200
        except Exception:
            return False