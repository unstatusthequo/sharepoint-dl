"""Token bucket bandwidth throttle — shared across all download workers."""

from __future__ import annotations

import re
import threading
import time

# ---------------------------------------------------------------------------
# Parse CLI throttle string (e.g. "10MB", "500KB")
# ---------------------------------------------------------------------------

_THROTTLE_RE = re.compile(r"^(\d+)(KB|MB|GB)$", re.IGNORECASE)

_UNITS: dict[str, int] = {
    "KB": 1024,
    "MB": 1024 * 1024,
    "GB": 1024 * 1024 * 1024,
}


def parse_throttle(value: str | None) -> int | None:
    """Parse a human-friendly throttle string into bytes per second.

    Args:
        value: String like "10MB", "500KB", "1GB", or None.

    Returns:
        Bytes per second, or None if value is None.

    Raises:
        ValueError: If value cannot be parsed or is zero.
    """
    if value is None:
        return None

    m = _THROTTLE_RE.match(value.strip())
    if not m:
        raise ValueError(f"Invalid throttle value: {value!r}. Use format like 10MB, 500KB, 1GB.")

    amount = int(m.group(1))
    unit = m.group(2).upper()

    result = amount * _UNITS[unit]
    if result == 0:
        raise ValueError("Throttle rate must be greater than zero.")
    return result


# ---------------------------------------------------------------------------
# Token Bucket
# ---------------------------------------------------------------------------


class TokenBucket:
    """Thread-safe token bucket for aggregate bandwidth limiting.

    A single instance is shared across all download workers. Each worker
    calls ``consume(chunk_size)`` after writing a chunk; the bucket sleeps
    when tokens are exhausted to maintain the target rate.

    When no throttle is needed, callers simply skip the call::

        if throttle:
            throttle.consume(len(chunk))
    """

    def __init__(self, rate_bytes_per_sec: int) -> None:
        self._rate = float(rate_bytes_per_sec)
        self._tokens = float(rate_bytes_per_sec)  # start full (1s burst)
        self._max_tokens = float(rate_bytes_per_sec)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, amount: int) -> None:
        """Consume *amount* tokens, sleeping if the bucket is empty.

        Args:
            amount: Number of bytes (tokens) to consume.
        """
        sleep_time = 0.0

        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._max_tokens,
                self._tokens + elapsed * self._rate,
            )
            self._last_refill = now

            if self._tokens >= amount:
                self._tokens -= amount
                return

            # Not enough tokens — compute required sleep and advance
            # the refill timestamp into the future so other threads
            # waiting on the lock see the reserved time.
            deficit = amount - self._tokens
            sleep_time = deficit / self._rate
            self._tokens = 0.0
            self._last_refill = now + sleep_time

        # Sleep outside the lock so other threads can enter and
        # compute their own (later) wait times.
        time.sleep(sleep_time)
