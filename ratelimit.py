"""Small in-memory sliding-window rate limiter (per process)."""
import threading
import time
from collections import deque
from typing import Tuple


class RateLimiter:
    def __init__(self, limit: int, window: int = 60, max_keys: int = 10000):
        self.limit = limit
        self.window = window
        self.max_keys = max_keys
        self._hits = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> Tuple[bool, int, int]:
        """Returns (allowed, remaining, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()

            if len(hits) >= self.limit:
                return False, 0, int(self.window - (now - hits[0])) + 1

            hits.append(now)
            if len(self._hits) > self.max_keys:
                self._prune(now)
            return True, self.limit - len(hits), 0

    def _prune(self, now: float) -> None:
        for key in [k for k, h in self._hits.items() if not h or now - h[-1] >= self.window]:
            del self._hits[key]
