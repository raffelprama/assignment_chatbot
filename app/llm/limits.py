"""Client-side rate limiting and retry-delay parsing for the Gemini free tier.

Observed on 2026-11-23: the free tier allows 100 embedding requests per minute, and every text in
an `embed_documents` batch counts as one request. Quota errors carry a "retry in Ns" hint.
"""

import asyncio
import re
import time
from collections import deque

_RETRY_HINT = re.compile(r"retry in (\d+(?:\.\d+)?)s", re.IGNORECASE)


def retry_delay_from_error(exc: BaseException) -> float | None:
    match = _RETRY_HINT.search(str(exc))
    return float(match.group(1)) if match else None


class SlidingWindowLimiter:
    """Allow at most `limit` units per `window_s` seconds; `acquire(n)` waits until n units fit."""

    def __init__(self, limit: int, window_s: float = 60.0):
        self._limit = limit
        self._window = window_s
        self._events: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self, units: int = 1) -> None:
        units = min(units, self._limit)
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._events and now - self._events[0] >= self._window:
                    self._events.popleft()
                if len(self._events) + units <= self._limit:
                    self._events.extend([now] * units)
                    return
                await asyncio.sleep(self._window - (now - self._events[0]) + 0.05)
