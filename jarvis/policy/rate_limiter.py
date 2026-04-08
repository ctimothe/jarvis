"""Rate limiter for actions."""

import time
import threading


class RateLimiter:
    """Fixed-window rate limiter."""

    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self._lock = threading.Lock()
        self._state: dict[str, tuple[int, int]] = {}

    def allow(self, principal: str) -> tuple[bool, int]:
        """Check if action is allowed. Returns (allowed, retry_after_seconds)."""
        now_min = int(time.time() // 60)
        with self._lock:
            minute, count = self._state.get(principal, (now_min, 0))
            if minute != now_min:
                minute, count = now_min, 0
            if count >= self.max_per_minute:
                retry_after = 60 - int(time.time() % 60)
                return False, max(retry_after, 1)
            self._state[principal] = (minute, count + 1)
        return True, 0