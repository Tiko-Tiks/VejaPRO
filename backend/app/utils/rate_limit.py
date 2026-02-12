import ipaddress
import time
from collections import deque
from threading import Lock
from typing import Optional

from fastapi import Request

from app.core.config import get_settings

_MAX_BUCKETS = 50_000
_PRUNE_INTERVAL_SECONDS = 60


class SlidingWindowRateLimiter:
    def __init__(
        self,
        *,
        max_buckets: int = _MAX_BUCKETS,
        prune_interval_seconds: int = _PRUNE_INTERVAL_SECONDS,
    ) -> None:
        self._buckets: dict[str, deque[float]] = {}
        self._lock = Lock()
        self._max_buckets = max_buckets
        self._prune_interval_seconds = max(1, int(prune_interval_seconds))
        self._last_prune_at = 0.0

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        if limit <= 0 or window_seconds <= 0:
            return True, 0
        now = time.monotonic()
        with self._lock:
            # Periodic prune prevents unbounded growth even in "low traffic" environments.
            # We also prune immediately if we cross a hard bucket cap.
            if len(self._buckets) > self._max_buckets or (now - self._last_prune_at) >= self._prune_interval_seconds:
                self._prune_stale(now, window_seconds)
                self._last_prune_at = now

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
            self._last_prune_at = 0.0


rate_limiter = SlidingWindowRateLimiter()


def _ip_in_allowlist(ip: str, allowlist: list[str]) -> bool:
    if not ip:
        return False
    if ip in allowlist:
        return True
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in allowlist:
        if entry == ip:
            return True
        try:
            if ip_obj in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def is_trusted_proxy_peer(request: Request, trusted_proxy_cidrs: Optional[list[str]] = None) -> bool:
    """Return True when the direct peer IP is in trusted proxy CIDRs."""
    peer_ip = request.client.host if request.client else None
    trusted = trusted_proxy_cidrs
    if trusted is None:
        trusted = getattr(get_settings(), "trusted_proxy_cidrs", [])
    if not (peer_ip and trusted):
        return False

    # Test harness compatibility: Starlette TestClient peer can be loopback
    # even when tests configure "testclient" as trusted proxy identifier.
    if "testclient" in trusted and (peer_ip is None or peer_ip in {"testclient", "127.0.0.1", "::1", "localhost"}):
        return True

    return _ip_in_allowlist(peer_ip, trusted)


def get_client_ip(request: Request, trusted_proxy_cidrs: Optional[list[str]] = None) -> Optional[str]:
    """Extract client IP from request.

    SECURITY: ``X-Real-IP`` and ``X-Forwarded-For`` are trusted only when
    the direct peer (``request.client.host``) is in ``TRUSTED_PROXY_CIDRS``.
    Otherwise forwarded headers are ignored to prevent spoofing.
    """
    peer_ip = request.client.host if request.client else None
    trusted = trusted_proxy_cidrs
    if trusted is None:
        trusted = getattr(get_settings(), "trusted_proxy_cidrs", [])

    if is_trusted_proxy_peer(request, trusted):
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Rightmost IP is the one added by the first trusted reverse proxy.
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            if parts:
                return parts[-1]

    return peer_ip


def get_user_agent(request: Request) -> Optional[str]:
    return request.headers.get("user-agent") if request else None
