"""Action parser - converts text to ActionRequests."""

import re
import os
from pathlib import Path

from jarvis.types import ActionRequest
from jarvis.actions.base import ActionRegistry
from jarvis import constants


def _normalize_path(raw: str) -> str:
    """Normalize a path string."""
    cleaned = raw.strip().strip("'\"").rstrip(".?!")
    if cleaned.startswith("~"):
        cleaned = os.path.expanduser(cleaned)
    elif not cleaned.startswith("/"):
        cleaned = os.path.join(os.path.expanduser("~"), cleaned)
    return str(Path(cleaned).expanduser().resolve())


def _tokenize_lower(text: str) -> list[str]:
    """Tokenize text to lowercase words."""
    return [w for w in re.sub(r"[^a-z0-9\s]", " ", text.lower()).split() if w]


def _has_close_token(tokens: list[str], targets: list[str], cutoff: float = 0.74) -> bool:
    """Check if any token is close to a target."""
    import difflib
    for token in tokens:
        if difflib.get_close_matches(token, targets, n=1, cutoff=cutoff):
            return True
    return False


class ActionParser:
    """Parses text into ActionRequests."""

    def __init__(self, registry: ActionRegistry):
        self.registry = registry

    def parse(self, text: str) -> ActionRequest | None:
        """Parse text into an ActionRequest."""
        text = text.strip()
        lower = text.lower()
        tokens = _tokenize_lower(text)
        principal = os.getenv("USER", "local_user")

        # Try each known pattern
        parsed = (
            self._parse_translation(text, lower, principal) or
            self._parse_volume(text, lower, principal) or
            self._parse_mute(text, lower, principal) or
            self._parse_system_status(text, lower, tokens, principal) or
            self._parse_git(text, lower, principal) or
            self._parse_filesystem(text, lower, principal) or
            self._parse_app_control(text, lower, principal) or
            self._parse_url(text, text, principal)
        )

        return parsed

    def _parse_translation(self, text: str, lower: str, principal: str):
        """Parse translation requests."""
        # translate "hello" to spanish
        quoted = re.search(r'translate\s+"(.+?)"\s+to\s+([a-zA-Z]+)', text, flags=re.IGNORECASE)
        if quoted:
            return ActionRequest(
                action=constants.ACTION_TRANSLATE_TEXT,
                args={"text": quoted.group(1).strip(), "source_lang": "english", "target_lang": quoted.group(2).strip().lower()},
                principal=principal,
                reason=text,
            )

        # translate hello to spanish
        plain = re.search(r'translate\s+(.+?)\s+to\s+([a-zA-Z]+)$', lower, flags=re.IGNORECASE)
        if plain:
            return ActionRequest(
                action=constants.ACTION_TRANSLATE_TEXT,
                args={"text": plain.group(1).strip().strip("'\""), "source_lang": "english", "target_lang": plain.group(2).strip().lower()},
                principal=principal,
                reason=text,
            )

        # say this in spanish: hello
        say_in = re.search(r'say\s+this\s+in\s+([a-zA-Z]+)\s*[:,-]?\s*(.+)$', lower, flags=re.IGNORECASE)
        if say_in:
            return ActionRequest(
                action=constants.ACTION_TRANSLATE_TEXT,
                args={"text": say_in.group(2).strip().strip("'\""), "source_lang": "english", "target_lang": say_in.group(1).strip().lower()},
                principal=principal,
                reason=text,
            )

        return None

    def _parse_volume(self, text: str, lower: str, principal: str):
        """Parse volume commands."""
        vol_set = re.search(r"\bset\s+(?:the\s+)?volume\s+(?:to|at)\s+(\d+)", lower)
        if vol_set:
            level = max(0, min(100, int(vol_set.group(1))))
            return ActionRequest(
                action=constants.ACTION_SET_VOLUME_LEVEL,
                args={"level": level},
                principal=principal,
                reason=text,
            )
        return None

    def _parse_mute(self, text: str, lower: str, principal: str):
        """Parse mute commands."""
        if re.search(r"\b(mute (?:my )?(?:volume|sound|audio)|turn (?:the )?sound off)\b", lower):
            return ActionRequest(
                action=constants.ACTION_TOGGLE_MUTE,
                args={"mute": True},
                principal=principal,
                reason=text,
            )
        if re.search(r"\b(unmute (?:my )?(?:volume|sound|audio)|turn (?:the )?sound on)\b", lower):
            return ActionRequest(
                action=constants.ACTION_TOGGLE_MUTE,
                args={"mute": False},
                principal=principal,
                reason=text,
            )
        return None

    def _parse_system_status(self, text: str, lower: str, tokens: list[str], principal: str):
        """Parse system status commands."""
        if re.search(r'\b(disk\s+space|storage|disk\s+usage)\b', lower):
            return ActionRequest(action=constants.ACTION_DISK_USAGE, args={}, principal=principal, reason=text)

        if re.search(r'\b(battery|battery\s+health|maximum\s+capacity|cycle\s+count|charging|power adapter|ac attached)\b', lower):
            return ActionRequest(action=constants.ACTION_BATTERY_STATUS, args={}, principal=principal, reason=text)

        if re.search(r'\b(volume level|what.*volume|volume status|current volume|sound level)\b', lower):
            return ActionRequest(action=constants.ACTION_VOLUME_STATUS, args={}, principal=principal, reason=text)

        song_phrase = re.search(r'\b(what song|what.?s.*playing|song.*playing|now playing|currently(?:\s+being)?\s+played|currently.*playing|track playing|current song|being played)\b', lower)
        approx_song_status = (
            ("song" in tokens or "track" in tokens)
            and not lower.strip().startswith("play ")
            and (
                _has_close_token(tokens, ["playing", "played", "currently", "current", "now"], cutoff=0.66)
                or len(tokens) <= 3
            )
        )
        if song_phrase or approx_song_status:
            return ActionRequest(action=constants.ACTION_NOW_PLAYING, args={}, principal=principal, reason=text)

        if re.search(r'\b(wi[- ]?fi|wireless network|network name|network am i on|what network|ssid|internet(?:\s+connection)?|connected to (?:the )?internet|am i online|connected online)\b', lower):
            return ActionRequest(action=constants.ACTION_WIFI_STATUS, args={}, principal=principal, reason=text)

        if re.search(r'\b(what time|time now|current time|date today|today.?s date)\b', lower):
            return ActionRequest(action=constants.ACTION_TIME_STATUS, args={}, principal=principal, reason=text)

        if re.search(r'\b(active app|frontmost app|which app.*open|focused app|what app is active|which app is running|currently running app|active .* currently running)\b', lower):
            return ActionRequest(action=constants.ACTION_ACTIVE_APP, args={}, principal=principal, reason=text)

        return None

    def _parse_git(self, text: str, lower: str, principal: str):
        """Parse git commands."""
        match = re.search(r'\bgit\s+status(?:\s+in\s+(.+))?$', lower)
        if match:
            repo = _normalize_path(match.group(1) or os.getcwd())
            return ActionRequest(action=constants.ACTION_GIT_STATUS, args={"repo": repo}, principal=principal, reason=text)

        if re.search(r'\bgit\s+diff\b', lower):
            repo_match = re.search(r'\bin\s+(.+)$', lower)
            repo = _normalize_path(repo_match.group(1)) if repo_match else os.getcwd()
            return ActionRequest(action=constants.ACTION_GIT_DIFF_STAT, args={"repo": repo}, principal=principal, reason=text)

        if re.search(r'\bgit\s+log\b', lower):
            repo_match = re.search(r'\bin\s+(.+)$', lower)
            repo = _normalize_path(repo_match.group(1)) if repo_match else os.getcwd()
            limit_match = re.search(r'\blast\s+(\d+)\b', lower)
            limit = max(1, min(50, int(limit_match.group(1)) if limit_match else 5))
            return ActionRequest(action=constants.ACTION_GIT_LOG_RECENT, args={"repo": repo, "limit": limit}, principal=principal, reason=text)

        if re.search(r'\bgit\s+branches\b', lower) or re.search(r'\b(list|show)\s+branches\b', lower):
            repo_match = re.search(r'\bin\s+(.+)$', lower)
            repo = _normalize_path(repo_match.group(1)) if repo_match else os.getcwd()
            return ActionRequest(action=constants.ACTION_GIT_BRANCHES, args={"repo": repo}, principal=principal, reason=text)

        recent_changes = re.search(r'\bwhat (?:has )?changed since (?:the )?last commit\b', lower)
        if recent_changes:
            repo_match = re.search(r'\bin\s+(.+)$', lower)
            repo = _normalize_path(repo_match.group(1)) if repo_match else os.getcwd()
            return ActionRequest(action=constants.ACTION_GIT_RECENT_CHANGES, args={"repo": repo}, principal=principal, reason=text)

        search_match = re.search(r'\bsearch\s+for\s+(.+?)\s+in\s+(.+)$', text, flags=re.IGNORECASE)
        if search_match:
            pattern = search_match.group(1).strip().strip("'\"")
            root = _normalize_path(search_match.group(2))
            if pattern:
                return ActionRequest(action=constants.ACTION_PROJECT_SEARCH, args={"pattern": pattern, "path": root}, principal=principal, reason=text)

        return None

    def _parse_filesystem(self, text: str, lower: str, principal: str):
        """Parse filesystem commands."""
        match = re.search(r'\b(?:create|make)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)\s+(?:called\s+)?(.+)$', lower)
        if match:
            return ActionRequest(action=constants.ACTION_CREATE_FOLDER, args={"path": _normalize_path(match.group(1))}, principal=principal, reason=text)

        match = re.search(r'\b(?:create|make)\s+(?:a\s+)?(?:new\s+)?file\s+(?:called\s+)?(.+)$', lower)
        if match:
            return ActionRequest(action=constants.ACTION_CREATE_FILE, args={"path": _normalize_path(match.group(1))}, principal=principal, reason=text)

        match = re.search(r'\b(?:list|show)\s+(?:files\s+)?(?:in|at)?\s*(.+)$', lower)
        if match and match.group(1):
            return ActionRequest(action=constants.ACTION_LIST_PATH, args={"path": _normalize_path(match.group(1))}, principal=principal, reason=text)

        match = re.search(r'\bfind\s+(.+?)\s+in\s+(.+)$', lower)
        if match:
            return ActionRequest(action=constants.ACTION_FIND_NAME, args={"pattern": match.group(1).strip().strip("'\""), "path": _normalize_path(match.group(2))}, principal=principal, reason=text)

        match = re.search(r'\bmove\s+(.+?)\s+to\s+(.+)$', lower)
        if match:
            return ActionRequest(action=constants.ACTION_MOVE_PATH, args={"src": _normalize_path(match.group(1)), "dst": _normalize_path(match.group(2))}, principal=principal, reason=text)

        match = re.search(r'\bcopy\s+(.+?)\s+to\s+(.+)$', lower)
        if match:
            return ActionRequest(action=constants.ACTION_COPY_PATH, args={"src": _normalize_path(match.group(1)), "dst": _normalize_path(match.group(2))}, principal=principal, reason=text)

        match = re.search(r'\brename\s+(.+?)\s+to\s+(.+)$', lower)
        if match:
            return ActionRequest(action=constants.ACTION_RENAME_PATH, args={"src": _normalize_path(match.group(1)), "dst": _normalize_path(match.group(2))}, principal=principal, reason=text)

        match = re.search(r'\b(?:delete|remove)\s+(.+)$', lower)
        if match:
            return ActionRequest(action=constants.ACTION_DELETE_PATH, args={"path": _normalize_path(match.group(1))}, principal=principal, reason=text)

        return None

    def _parse_app_control(self, text: str, lower: str, principal: str):
        """Parse app control commands."""
        if re.search(r'\b(quit|close)\b', lower):
            app = self._match_known_app(lower)
            if app:
                return ActionRequest(action=constants.ACTION_QUIT_APP, args={"app": app}, principal=principal, reason=text)

        if re.search(r'\b(focus|activate|switch to)\b', lower):
            app = self._match_known_app(lower)
            if app:
                return ActionRequest(action=constants.ACTION_FOCUS_APP, args={"app": app}, principal=principal, reason=text)

        return None

    def _parse_url(self, text: str, original: str, principal: str):
        """Parse URL open commands."""
        url_match = re.search(r'\bopen\s+url\s+(\S+)', text, flags=re.IGNORECASE)
        if url_match:
            url = url_match.group(1).strip().strip("'\"")
            if url.lower().startswith(("http://", "https://")):
                return ActionRequest(action=constants.ACTION_OPEN_URL, args={"url": url}, principal=principal, reason=original)
        return None

    def _match_known_app(self, query_lower: str) -> str | None:
        """Match known app names."""
        known_apps = {
            "chrome": "Google Chrome",
            "browser": "Google Chrome",
            "safari": "Safari",
            "firefox": "Firefox",
            "vscode": "Visual Studio Code",
            "visual studio": "Visual Studio Code",
            "code": "Visual Studio Code",
            "terminal": "Terminal",
            "iterm": "iTerm",
            "spotify": "Spotify",
            "music": "Spotify",
            "slack": "Slack",
            "discord": "Discord",
            "finder": "Finder",
            "notes": "Notes",
            "calendar": "Calendar",
            "mail": "Mail",
            "figma": "Figma",
            "xcode": "Xcode",
            "pycharm": "PyCharm",
            "calculator": "Calculator",
            "settings": "System Preferences",
            "activity monitor": "Activity Monitor",
            "photos": "Photos",
            "messages": "Messages",
            "facetime": "FaceTime",
            "whatsapp": "WhatsApp",
            "notion": "Notion",
            "zoom": "zoom.us",
            "teams": "Microsoft Teams",
            "obsidian": "Obsidian",
            "arc": "Arc",
        }
        for key, app in known_apps.items():
            if re.search(rf"\b{re.escape(key)}\b", query_lower):
                return app
        return None