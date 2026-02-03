import time
from collections import deque
from threading import Lock
from typing import Deque, Dict, Optional, Tuple

from fastapi import Request


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        if limit <= 0 or window_seconds <= 0:
            return True, 0
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = deque()
                self._buckets[key] = bucket
            cutoff = now - window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False, len(bucket)
            bucket.append(now)
            return True, len(bucket)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


rate_limiter = SlidingWindowRateLimiter()


def get_client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def get_user_agent(request: Request) -> Optional[str]:
    return request.headers.get("user-agent") if request else None
