"""Retry with exponential backoff for calls that fault transiently.

Model providers rate-limit and occasionally 5xx. In a demo one failed call
ends the run; in production it must be absorbed. This wraps a call so it retries
on the errors that are worth retrying, backs off between attempts, and gives up
loudly only after the budget is exhausted.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

log = logging.getLogger("conductor.resilience")
T = TypeVar("T")

# Substrings that mark a fault as transient and therefore worth retrying.
_RETRYABLE = (
    "throttl", "rate limit", "ratelimit", "429", "503", "500", "502", "504",
    "timeout", "timed out", "temporarily", "overloaded", "unavailable",
    "event loop cycle failed", "connection reset", "connection aborted",
)


def is_retryable(exc: Exception) -> bool:
    s = f"{type(exc).__name__}: {exc}".lower()
    return any(m in s for m in _RETRYABLE)


def with_retry(fn: Callable[[], T], *, max_retries: int = 5, base: float = 1.5,
               cap: float = 30.0, on_retry: Callable[[int, Exception], None] | None = None) -> T:
    """Call fn(); on a retryable error wait base**attempt (± jitter, capped) and
    try again, up to max_retries. Non-retryable errors raise immediately."""
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if attempt >= max_retries or not is_retryable(exc):
                raise
            delay = min(cap, base ** attempt) * (0.7 + 0.6 * random.random())
            attempt += 1
            if on_retry:
                on_retry(attempt, exc)
            log.warning("retry %d/%d after %.1fs: %s", attempt, max_retries, delay,
                        str(exc)[:120])
            time.sleep(delay)
