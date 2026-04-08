"""Intent classifier."""

import re
from enum import Enum, auto
from dataclasses import dataclass

from jarvis.config import Config


class Intent(Enum):
    """Possible intents."""
    OPEN_APP = auto()
    MUSIC = auto()
    WORK_MODE = auto()
    SYSTEM = auto()
    SHELL = auto()
    STOP = auto()
    QUESTION = auto()


@dataclass
class Classification:
    """Classification result."""
    intent: Intent
    confidence: float = 1.0
    entities: dict[str, str] = None

    def __post_init__(self):
        if self.entities is None:
            self.entities = {}


class Classifier:
    """Rule-based + optional LLM classifier."""

    def __init__(self, config: Config):
        self.config = config
        self._rules = self._build_rules()
        self._llm_enabled = config.llm.backend != "none"

    def _build_rules(self) -> list[tuple[str, re.Pattern, Intent]]:
        """Build regex-based classification rules."""
        return [
            # STOP
            (r'\b(stop|shut up|quiet|cancel|never ?mind)\b', Intent.STOP),

            # WORK_MODE
            (r'\bwork\s*mode\b', Intent.WORK_MODE),

            # SYSTEM
            (r'\b(sleep|lock|shutdown|restart|reboot)\b', Intent.SYSTEM),

            # OPEN_APP
            (r'\b(open|launch|start)\b', Intent.OPEN_APP),

            # MUSIC
            (r'\b(play|pause|skip|next|previous|shuffle|volume)\b.*\b(spotify|music|song|track|playlist)\b', Intent.MUSIC),
            (r'\bvolume\s+(up|down)\b', Intent.MUSIC),
            (r'^\s*(play|pause|skip|next|previous|shuffle)\b', Intent.MUSIC),

            # SHELL - filesystem
            (r'\b(create|make)\b.*\b(folder|directory|file)\b', Intent.SHELL),
            (r'\b(delete|remove)\b', Intent.SHELL),
            (r'\b(move|copy|rename)\b', Intent.SHELL),
            (r'\b(list|show)\s+(files|folders|directory|dir|in|at)\b', Intent.SHELL),
            (r'\bfind\b', Intent.SHELL),
            (r'\b(disk\s+space|storage|disk\s+usage)\b', Intent.SHELL),

            # SHELL - git
            (r'\bgit\s+status\b', Intent.SHELL),
            (r'\bgit\s+diff\b', Intent.SHELL),
            (r'\bgit\s+log\b', Intent.SHELL),
            (r'\bgit\s+branches\b', Intent.SHELL),
            (r'\bwhat (?:has )?changed since (?:the )?last commit\b', Intent.SHELL),

            # SHELL - system status
            (r'\b(battery|battery\s+health|maximum\s+capacity|cycle\s+count|charging|power adapter)\b', Intent.SHELL),
            (r'\b(volume level|current volume|sound level|mute status)\b', Intent.SHELL),
            (r'\bset\s+(?:the\s+)?volume\s+(?:to|at)\s+\d+\b', Intent.SHELL),
            (r'\b(mute|unmute).*(?:volume|sound|audio)\b', Intent.SHELL),
            (r'\b(now playing|what song|what.?s.*playing|song.*playing|current(?:ly)?.*playing)\b', Intent.SHELL),
            (r'\b(wi[- ]?fi|ssid|network name|network am i on|what network|internet|am i online)\b', Intent.SHELL),
            (r'\b(what time|date today|active app|frontmost app|what app is active|which app is running)\b', Intent.SHELL),

            # SHELL - translation/search
            (r'^\s*translate\b', Intent.SHELL),
            (r'^\s*say this in\b', Intent.SHELL),
            (r'\bsearch\s+for\s+.+\s+in\s+.+', Intent.SHELL),

            # SHELL - app control
            (r'\b(quit|close)\b.*(chrome|browser|safari|firefox|spotify|slack|discord|finder)', Intent.SHELL),
            (r'\b(focus|activate|switch to)\b.*(chrome|browser|safari|firefox|spotify|slack|discord)', Intent.SHELL),
            (r'\bopen\s+url\s+\S+', Intent.SHELL),
        ]

    def classify(self, text: str) -> Intent:
        """Classify text into intent."""
        q = text.lower().strip()

        # First, try rules
        for pattern, intent in self._rules:
            if re.search(pattern, q):
                return intent

        # Check for question patterns
        if re.match(r"^\s*(what|what's|whats|who|where|when|why|how|is|are|can|could|would|do)\b", q):
            return Intent.QUESTION

        # Fall back to LLM if enabled
        if self._llm_enabled:
            return self._classify_llm(text)

        return Intent.QUESTION

    def _classify_llm(self, text: str) -> Intent:
        """Use LLM for classification."""
        # This will use the LLM registry
        from jarvis.llm.registry import get_llm_registry
        llm = get_llm_registry().get_backend()

        if not llm or not llm.is_available():
            return Intent.QUESTION

        system = """Classify the user command into exactly ONE category.
Reply with only the category name. No punctuation.

OPEN - open, launch, or start an application
MUSIC - control Spotify: play, pause, skip, volume
WORK_MODE - activate work mode
SYSTEM - sleep, lock, shutdown, restart
SHELL - file/folder operations, git, system stats
STOP - stop talking / cancel
QUESTION - everything else"""

        try:
            result = llm.complete(
                prompt=text,
                system=system,
                temperature=0.0,
                stop=["\n", " ", ".", ","],
            )
            result = result.strip().upper()
            for intent in Intent:
                if intent.name == result:
                    return intent
        except Exception:
            pass

        return Intent.QUESTION