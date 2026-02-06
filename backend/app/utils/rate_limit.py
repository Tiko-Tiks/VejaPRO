import time
from collections import deque
from threading import Lock
from typing import Deque, Dict, Optional, Tuple

from fastapi import Request

_MAX_BUCKETS = 50_000


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        if limit <= 0 or window_seconds <= 0:
            return True, 0
        now = time.monotonic()
        with self._lock:
            # Prune stale buckets periodically to prevent memory leak
            if len(self._buckets) > _MAX_BUCKETS:
                self._prune_stale(now, window_seconds)

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

    def _prune_stale(self, now: float, window_seconds: int) -> None:
        """Remove buckets that have no recent entries (called under lock)."""
        stale_keys = []
        for key, bucket in self._buckets.items():
            cutoff = now - window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if not bucket:
                stale_keys.append(key)
        for key in stale_keys:
            del self._buckets[key]

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


rate_limiter = SlidingWindowRateLimiter()


def get_client_ip(request: Request) -> Optional[str]:
    """Extract client IP from request.

    Uses X-Real-IP (set by Nginx) first, then falls back to the
    **rightmost** entry in X-Forwarded-For (the IP seen by the first
    trusted proxy), and finally request.client.host.
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Rightmost IP is the one added by the first trusted reverse proxy
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]

    return request.client.host if request.client else None


def get_user_agent(request: Request) -> Optional[str]:
    return request.headers.get("user-agent") if request else None
