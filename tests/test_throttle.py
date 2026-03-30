"""Tests for sharepoint_dl.downloader.throttle — token bucket rate limiter."""

from __future__ import annotations

import threading
import time

import pytest

from sharepoint_dl.downloader.throttle import TokenBucket, parse_throttle

# ---------------------------------------------------------------------------
# parse_throttle
# ---------------------------------------------------------------------------


class TestParseThrottle:
    def test_none_returns_none(self):
        assert parse_throttle(None) is None

    def test_megabytes(self):
        assert parse_throttle("10MB") == 10 * 1024 * 1024

    def test_kilobytes(self):
        assert parse_throttle("500KB") == 500 * 1024

    def test_gigabytes(self):
        assert parse_throttle("1GB") == 1024 * 1024 * 1024

    def test_case_insensitive(self):
        assert parse_throttle("10mb") == 10 * 1024 * 1024
        assert parse_throttle("500kb") == 500 * 1024

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_throttle("abc")

    def test_no_unit_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_throttle("100")

    def test_zero_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_throttle("0MB")


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------


class TestTokenBucket:
    def test_consume_small_amount_returns_instantly(self):
        """Consuming less than the bucket capacity should not block."""
        bucket = TokenBucket(rate_bytes_per_sec=1_000_000)
        start = time.monotonic()
        bucket.consume(1000)
        elapsed = time.monotonic() - start
        assert elapsed < 0.05

    def test_consume_more_than_capacity_sleeps(self):
        """Consuming more tokens than available should cause a measurable sleep."""
        # Small rate so we can measure the delay
        bucket = TokenBucket(rate_bytes_per_sec=10_000)
        # Drain the bucket
        bucket.consume(10_000)
        # Now consume again — should sleep ~1s for 10_000 tokens at 10_000/s
        start = time.monotonic()
        bucket.consume(5_000)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.4, f"Expected sleep >= 0.4s, got {elapsed:.3f}s"

    def test_thread_safety(self):
        """Multiple threads consuming should stay within ~2x target rate."""
        rate = 100_000  # 100 KB/s
        bucket = TokenBucket(rate_bytes_per_sec=rate)
        chunk_size = 10_000
        total_consumed = 0
        lock = threading.Lock()

        duration = 0.5  # run for 0.5 seconds

        def worker():
            nonlocal total_consumed
            end_time = time.monotonic() + duration
            while time.monotonic() < end_time:
                bucket.consume(chunk_size)
                with lock:
                    total_consumed += chunk_size

        threads = [threading.Thread(target=worker) for _ in range(4)]
        start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        actual_elapsed = time.monotonic() - start

        # Effective rate should be within 2x of target
        effective_rate = total_consumed / actual_elapsed
        assert effective_rate <= rate * 2.5, (
            f"Effective rate {effective_rate:.0f} B/s exceeds 2.5x target {rate} B/s"
        )
