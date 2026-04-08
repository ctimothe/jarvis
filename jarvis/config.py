"""Configuration management for Jarvis."""

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class STTConfig:
    """Speech-to-text configuration."""
    backend: str = "auto"  # apple, whisper, google, auto
    model: str = "tiny.en"
    compute: str = "int8"
    vad_aggressiveness: int = 2
    silence_end_ms: int = 280
    partial_max_updates: int = 10
    partial_min_ms: int = 800
    partial_interval_ms: int = 450
    beam_size: int = 3
    best_of: int = 3


@dataclass
class TTSConfig:
    """Text-to-speech configuration."""
    backend: str = "auto"  # macos, espeak, pyttsx3, auto
    rate: int = 185
    voice: str | None = None


@dataclass
class LLMConfig:
    """LLM configuration."""
    backend: str = "ollama"  # ollama, openai, anthropic, none
    model: str = "llama3.1:8b"
    temperature: float = 0.3
    url: str = "http://localhost:11434"
    fallback_response: str = "AI is unavailable."
    max_tokens: int = 200


@dataclass
class PrivacyConfig:
    """Privacy configuration."""
    audit_enabled: bool = False
    metrics_enabled: bool = False


@dataclass
class SecurityConfig:
    """Security configuration."""
    require_approval_for_destructive: bool = True
    rate_limit_per_minute: int = 20
    max_action_timeout_seconds: int = 20


@dataclass
class WebConfig:
    """Web dashboard configuration."""
    enabled: bool = False
    port: int = 8080
    password: str | None = None
    host: str = "localhost"


@dataclass
class TriggerConfig:
    """Trigger configuration."""
    mode: str = "hotkey"  # hotkey, wake, hybrid
    hotkey: str = "cmd+shift+j"
    wake_backend: str = "openwakeword"  # openwakeword, stt_phrase
    wake_threshold: float = 0.55
    wake_poll_seconds: float = 0.8
    wake_min_interval_ms: int = 1200
    wake_guard_ms: int = 1800


@dataclass
class AppleSTTConfig:
    """Apple Speech configuration."""
    language: str = "en-US"
    timeout_padding_s: int = 4
    silence_end_ms: int = 420
    min_speech_ms: int = 170
    energy_floor: float = 0.010
    energy_multiplier: float = 2.0
    force_helper: bool = False


@dataclass
class Config:
    """Main configuration."""
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    web: WebConfig = field(default_factory=WebConfig)
    trigger: TriggerConfig = field(default_factory=TriggerConfig)
    apple_stt: AppleSTTConfig = field(default_factory=AppleSTTConfig)

    # Non-configurable computed values
    platform: str = field(init=False)
    home_dir: Path = field(init=False)

    def __post_init__(self):
        self.platform = platform.system()
        self.home_dir = Path.home()

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from env vars and config file."""
        config = cls()

        # Load from environment variables
        cls._load_env(config)

        # Load from config file (override env)
        cls._load_file(config)

        return config

    @classmethod
    def _load_env(cls, config: "Config") -> None:
        """Load configuration from environment variables."""
        # STT
        if stt_backend := os.getenv("JARVIS_STT_BACKEND"):
            config.stt.backend = stt_backend.strip()
        if stt_model := os.getenv("JARVIS_LOCAL_STT_MODEL"):
            config.stt.model = stt_model.strip()
        if vad_profile := os.getenv("JARVIS_VAD_PROFILE"):
            config.stt.vad_aggressiveness = {"fast": 2, "balanced": 2, "robust": 3}.get(
                vad_profile.strip(), 2
            )
            config.stt.silence_end_ms = {"fast": 280, "balanced": 420, "robust": 620}.get(
                vad_profile.strip(), 280
            )

        # TTS
        if tts_backend := os.getenv("JARVIS_TTS_BACKEND"):
            config.tts.backend = tts_backend.strip()

        # LLM
        if llm_backend := os.getenv("JARVIS_LLM_BACKEND"):
            config.llm.backend = llm_backend.strip()
        if llm_model := os.getenv("JARVIS_LLM_MODEL"):
            config.llm.model = llm_model.strip()
        if llm_url := os.getenv("OLLAMA_URL"):
            config.llm.url = llm_url.strip()

        # Privacy
        if os.getenv("JARVIS_AUDIT", "").strip() == "1":
            config.privacy.audit_enabled = True
        if os.getenv("JARVIS_METRICS", "").strip() == "1":
            config.privacy.metrics_enabled = True

        # Trigger
        if trigger_mode := os.getenv("JARVIS_TRIGGER_MODE"):
            config.trigger.mode = trigger_mode.strip()
        if wake_backend := os.getenv("JARVIS_WAKEWORD_BACKEND"):
            config.trigger.wake_backend = wake_backend.strip()
        if wake_threshold := os.getenv("JARVIS_WAKEWORD_THRESHOLD"):
            config.trigger.wake_threshold = float(wake_threshold)

        # Web
        if web_port := os.getenv("JARVIS_WEB_PORT"):
            config.web.port = int(web_port)
        if web_password := os.getenv("JARVIS_WEB_PASSWORD"):
            config.web.password = web_password.strip()
        if web_enabled := os.getenv("JARVIS_WEB_ENABLED"):
            config.web.enabled = web_enabled.strip() == "1"

    @classmethod
    def _load_file(cls, config: "Config") -> None:
        """Load configuration from config file."""
        config_path = config.home_dir / ".jarvis" / "config.yaml"
        if not config_path.exists():
            return

        try:
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}

            # Deep merge
            cls._merge_dict(config, data)
        except Exception:
            pass

    @classmethod
    def _merge_dict(cls, config: "Config", data: dict) -> None:
        """Merge dict into config dataclass."""
        for key, value in data.items():
            if hasattr(config, key):
                attr = getattr(config, key)
                if isinstance(attr, dataclass) and isinstance(value, dict):
                    for subkey, subvalue in value.items():
                        if hasattr(attr, subkey):
                            setattr(attr, subkey, subvalue)
                else:
                    setattr(config, key, value)

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dict."""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, dataclass):
                result[key] = {k: v for k, v in value.__dict__.items() if not k.startswith("_")}
            else:
                result[key] = value
        return result

    def save(self, path: Path | None = None) -> None:
        """Save configuration to file."""
        config_path = path or self.home_dir / ".jarvis" / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False)

    @property
    def is_macos(self) -> bool:
        return self.platform == "Darwin"

    @property
    def is_linux(self) -> bool:
        return self.platform == "Linux"

    @property
    def is_windows(self) -> bool:
        return self.platform == "Windows"


# Default config instance
_default_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance (lazy singleton)."""
    global _default_config
    if _default_config is None:
        _default_config = Config.load()
    return _default_config


def reset_config() -> Config:
    """Reset the global config (useful for testing)."""
    global _default_config
    _default_config = Config.load()
    return _default_config