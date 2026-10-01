"""Temporary lock after repeated failed logins, per client address and per e-mail.

In memory: enough for one API process (the internal deployment); a restart clears it.
"""

import time
from collections import defaultdict, deque

from app.core.config import settings

_failures: dict[str, deque[float]] = defaultdict(deque)


def _recent(key: str) -> deque[float]:
    window = settings.login_lock_minutes * 60
    stamps = _failures[key]
    while stamps and time.monotonic() - stamps[0] > window:
        stamps.popleft()
    return stamps


def locked_for(*keys: str) -> int:
    """Seconds until a login for any of these keys is allowed again; 0 when not locked."""
    window = settings.login_lock_minutes * 60
    wait = 0
    for key in keys:
        stamps = _recent(key)
        if len(stamps) >= settings.login_max_failures:
            wait = max(wait, int(window - (time.monotonic() - stamps[0])) + 1)
    return wait


def record_failure(*keys: str) -> None:
    for key in keys:
        _recent(key).append(time.monotonic())


def clear(*keys: str) -> None:
    for key in keys:
        _failures.pop(key, None)
