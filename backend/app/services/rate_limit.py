"""In-memory rate limits (sliding window). The app runs as one process, so memory is the simplest shared place.

A restart clears the counts; that is fine, the limits only slow down abuse. Nothing here is logged with an IP
address or email: only which limit was hit.
"""

import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

MAX_KEYS = 10_000  # above this, keys with no recent hits are dropped


class RateLimiter:
    def __init__(self, name: str, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.name = name
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        return hits

    def hit(self, key: str, cost: int = 1) -> float | None:
        """Count `cost` hits for `key` if they fit. Returns None if allowed, else seconds until they would fit."""
        with self._lock:
            now = self.clock()
            if len(self._hits) > MAX_KEYS:
                for stale in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
                    del self._hits[stale]
            hits = self._recent(key, now)
            if len(hits) + cost > self.limit:
                if cost > self.limit or not hits:
                    return self.window
                # The oldest hits that must expire before `cost` more fit.
                needed = len(hits) + cost - self.limit
                return max(hits[needed - 1] + self.window - now, 1.0)
            hits.extend([now] * cost)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# The limits (#41). Per IP address: many mobile users in India share one public IP, so these are generous.
SIGN_IN_STARTS = RateLimiter("sign-in", limit=20, window_seconds=10 * 60)
SIGN_IN_CALLBACKS = RateLimiter("sign-in callback", limit=20, window_seconds=10 * 60)
INVITE_CHECKS = RateLimiter("invite check", limit=20, window_seconds=10 * 60)
# Per account.
INVITE_CREATES = RateLimiter("invite creation", limit=30, window_seconds=60 * 60)
UPLOADED_FILES = RateLimiter("uploads", limit=100, window_seconds=60 * 60)

ALL_LIMITERS = (SIGN_IN_STARTS, SIGN_IN_CALLBACKS, INVITE_CHECKS, INVITE_CREATES, UPLOADED_FILES)


def is_limited(limiter: RateLimiter, key: str, cost: int = 1) -> float | None:
    retry_after = limiter.hit(key, cost)
    if retry_after is not None:
        logger.warning("Rate limit reached: %s", limiter.name)
    return retry_after


def enforce(limiter: RateLimiter, key: str, message: str, cost: int = 1) -> None:
    """Raise 429 (with Retry-After) if `key` is over the limit; `message` gets "Try again in N minutes." added."""
    retry_after = is_limited(limiter, key, cost)
    if retry_after is not None:
        minutes = max(1, math.ceil(retry_after / 60))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"{message} Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )
