from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitVerdict:
    allowed: bool
    remaining: int
    retry_after: int
    limit: int


class FixedWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int, max_tracked_keys: int = 10000) -> None:
        self._limit = limit
        self._window = window_seconds
        self._max_keys = max_tracked_keys
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[int, int]] = {}

    def _evict_expired(self, now_window: int) -> None:
        stale = [key for key, (start, _) in self._windows.items() if start < now_window]
        for key in stale:
            del self._windows[key]

    def check(self, key: str, now: float | None = None) -> RateLimitVerdict:
        timestamp = now if now is not None else time.time()
        window_start = int(timestamp // self._window)
        reset_at = (window_start + 1) * self._window
        retry_after = max(1, int(reset_at - timestamp))

        with self._lock:
            if len(self._windows) >= self._max_keys:
                self._evict_expired(window_start)

            start, count = self._windows.get(key, (window_start, 0))
            if start != window_start:
                start, count = window_start, 0

            if count >= self._limit:
                self._windows[key] = (start, count)
                return RateLimitVerdict(
                    allowed=False, remaining=0, retry_after=retry_after, limit=self._limit
                )

            count += 1
            self._windows[key] = (start, count)
            return RateLimitVerdict(
                allowed=True,
                remaining=self._limit - count,
                retry_after=retry_after,
                limit=self._limit,
            )

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()

    @property
    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._windows)
