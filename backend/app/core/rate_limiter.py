"""Sliding-window counter for failed login attempts per key (SPEC-BE-039).

In-memory and per-process; swap for Redis when running several workers. Only failures are
recorded (the middleware calls record() after a 401), so successful logins never count.
"""
import math
import time
from collections import defaultdict, deque
from threading import Lock

from app.config import get_settings

settings = get_settings()


class RateLimiter:
    def __init__(self, limit: int | None = None, window_minutes: int | None = None):
        self.limit = limit or settings.RATE_LIMIT_LOGIN_ATTEMPTS
        self.window_seconds = (window_minutes or settings.RATE_LIMIT_LOGIN_WINDOW_MINUTES) * 60
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, hits: deque[float], now: float) -> None:
        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()

    def retry_after(self, key: str) -> int:
        """0 when `key` may proceed; otherwise whole seconds until its oldest failure expires."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            self._prune(hits, now)
            if len(hits) < self.limit:
                return 0
            return max(1, math.ceil(hits[0] + self.window_seconds - now))

    def record(self, key: str) -> None:
        """Record one failure for `key`."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            self._prune(hits, now)
            hits.append(now)


rate_limiter = RateLimiter()
