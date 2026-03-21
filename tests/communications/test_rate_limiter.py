"""Tests for TokenBucketRateLimiter."""

from __future__ import annotations

import asyncio
import time
import pytest
from gobby.communications.rate_limiter import TokenBucketRateLimiter
from gobby.config.communications import ChannelDefaults

@pytest.mark.asyncio
async def test_rate_limiter_check():
    # 60 tokens per min = 1 token per sec. Burst = 2.
    limiter = TokenBucketRateLimiter(default_rate_per_min=60, default_burst=2)

    # First check consumes one token
    assert limiter.check("chan-1") is True
    # Second check consumes the second burst token
    assert limiter.check("chan-1") is True
    # Third check fails (empty)
    assert limiter.check("chan-1") is False

@pytest.mark.asyncio
async def test_rate_limiter_refill():
    # 600 tokens per min = 10 tokens per sec.
    limiter = TokenBucketRateLimiter(default_rate_per_min=600, default_burst=1)

    assert limiter.check("chan-1") is True
    assert limiter.check("chan-1") is False

    # Wait for refill (0.1s should give 1 token)
    await asyncio.sleep(0.15)
    assert limiter.check("chan-1") is True

@pytest.mark.asyncio
async def test_rate_limiter_wait():
    # 60 tokens per min = 1 token per sec.
    limiter = TokenBucketRateLimiter(default_rate_per_min=60, default_burst=1)

    # Consume initial token
    assert limiter.check("chan-1") is True

    start = time.monotonic()
    # Should wait ~1s
    await limiter.wait_if_needed("chan-1")
    end = time.monotonic()

    assert end - start >= 0.9

@pytest.mark.asyncio
async def test_rate_limiter_configure():
    limiter = TokenBucketRateLimiter(default_rate_per_min=1, default_burst=1)

    # Configure channel with high rate
    limiter.configure_channel("fast-chan", rate_per_min=6000, burst=10)

    for _ in range(10):
        assert limiter.check("fast-chan") is True
    assert limiter.check("fast-chan") is False

@pytest.mark.asyncio
async def test_rate_limiter_reset_remove():
    limiter = TokenBucketRateLimiter(default_rate_per_min=60, default_burst=1)

    assert limiter.check("chan-1") is True
    assert limiter.check("chan-1") is False

    limiter.reset("chan-1")
    assert limiter.check("chan-1") is True

    limiter.remove_channel("chan-1")
    # Should re-create with defaults
    assert limiter.check("chan-1") is True
