from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Small-process limiter; production multi-instance deployments need a shared store."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - max(1, int(window_seconds))
        with self._lock:
            bucket = self._events[str(key)]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= max(1, int(limit)):
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                return False, retry_after
            bucket.append(now)
            return True, 0


rate_limiter = SlidingWindowRateLimiter()

