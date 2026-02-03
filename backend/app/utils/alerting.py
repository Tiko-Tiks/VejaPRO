import logging
import time
from collections import deque
from threading import Lock
from typing import Deque, Dict, Optional


DEFAULT_WINDOW_SECONDS = 3600
DEFAULT_THRESHOLDS = {
    "SMS_CONFIRMATION_FAILED": 5,
    "SMS_CONFIRMATION_FINAL_PAYMENT_MISSING": 5,
    "SMS_SEND_FAILED": 5,
    "TWILIO_SIGNATURE_INVALID": 5,
    "RATE_LIMIT_BLOCKED": 20,
}


class AuditAlertTracker:
    def __init__(self, window_seconds: int, thresholds: Dict[str, int]) -> None:
        self._window_seconds = window_seconds
        self._thresholds = thresholds
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = Lock()

    def record(self, action: str, metadata: Optional[dict] = None) -> None:
        if action not in self._thresholds:
            return
        limit = self._thresholds[action]
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(action)
            if bucket is None:
                bucket = deque()
                self._buckets[action] = bucket
            cutoff = now - self._window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            bucket.append(now)
            if len(bucket) == limit:
                logging.warning(
                    "ALERT audit_action=%s count=%s window_seconds=%s metadata=%s",
                    action,
                    len(bucket),
                    self._window_seconds,
                    metadata or {},
                )


alert_tracker = AuditAlertTracker(DEFAULT_WINDOW_SECONDS, DEFAULT_THRESHOLDS)
