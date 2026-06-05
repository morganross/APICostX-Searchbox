"""In-memory request rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import DefaultDict, Deque

from fastapi import HTTPException


class InMemoryRateLimiter:
    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._buckets: DefaultDict[str, Deque[float]] = defaultdict(deque)

    @property
    def bucket_count(self) -> int:
        return len(self._buckets)

    def check(self, bucket_key: str, limit_per_minute: int) -> None:
        if limit_per_minute <= 0:
            return
        now = self._clock()
        bucket = self._buckets[bucket_key]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= limit_per_minute:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        bucket.append(now)
