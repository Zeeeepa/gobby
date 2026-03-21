"""Token-bucket rate limiter for communication channels."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from gobby.config.communications import ChannelDefaults


@dataclass
class _Bucket:
    """Internal state for a single token bucket."""

    tokens: float
    last_refill: float
    rate: float  # tokens per second
    burst: int


class TokenBucketRateLimiter:
    """Token-bucket rate limiter with per-channel tracking."""

    def __init__(
        self,
        default_rate_per_min: int = 30,
        default_burst: int = 5,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            default_rate_per_min: Default tokens per minute.
            default_burst: Default maximum tokens (burst size).
        """
        self._default_rate = default_rate_per_min / 60.0
        self._default_burst = default_burst
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def from_defaults(cls, defaults: ChannelDefaults) -> TokenBucketRateLimiter:
        """Create a rate limiter from ChannelDefaults."""
        return cls(
            default_rate_per_min=defaults.rate_limit_per_minute,
            default_burst=defaults.burst,
        )

    def _get_or_create_bucket(self, channel_id: str) -> _Bucket:
        """Get an existing bucket or create a new one with default settings."""
        if channel_id not in self._buckets:
            self._buckets[channel_id] = _Bucket(
                tokens=float(self._default_burst),
                last_refill=time.monotonic(),
                rate=self._default_rate,
                burst=self._default_burst,
            )
        return self._buckets[channel_id]

    def configure_channel(self, channel_id: str, rate_per_min: int, burst: int) -> None:
        """Configure specific limits for a channel.

        Args:
            channel_id: The ID of the channel.
            rate_per_min: Tokens per minute for this channel.
            burst: Maximum tokens (burst size) for this channel.
        """
        rate = rate_per_min / 60.0
        if channel_id in self._buckets:
            bucket = self._buckets[channel_id]
            bucket.rate = rate
            bucket.burst = burst
            # Cap tokens if new burst is smaller
            bucket.tokens = min(bucket.tokens, float(burst))
        else:
            self._buckets[channel_id] = _Bucket(
                tokens=float(burst),
                last_refill=time.monotonic(),
                rate=rate,
                burst=burst,
            )

    def _refill(self, bucket: _Bucket) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        if elapsed > 0:
            new_tokens = elapsed * bucket.rate
            bucket.tokens = min(float(bucket.burst), bucket.tokens + new_tokens)
            bucket.last_refill = now

    async def check(self, channel_id: str) -> bool:
        """Check if a token is available and consume it if so.

        This follows the token-bucket algorithm, refilling tokens based on elapsed time
        since the last check or refill operation.

        Args:
            channel_id: The ID of the channel to check.

        Returns:
            True if a token was consumed, False otherwise.
        """
        async with self._lock:
            bucket = self._get_or_create_bucket(channel_id)
            self._refill(bucket)

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True
            return False

    async def wait_if_needed(self, channel_id: str) -> None:
        """Wait until a token is available for the channel.

        Args:
            channel_id: The ID of the channel.
        """
        while True:
            async with self._lock:
                bucket = self._get_or_create_bucket(channel_id)
                self._refill(bucket)

                if bucket.tokens >= 1.0:
                    bucket.tokens -= 1.0
                    return

                # Calculate wait time
                needed = 1.0 - bucket.tokens
                wait_time = needed / bucket.rate

            # Sleep outside the lock to allow other channels/checks to proceed
            await asyncio.sleep(wait_time)

    async def reset(self, channel_id: str) -> None:
        """Reset a channel's bucket to full.

        Args:
            channel_id: The ID of the channel.
        """
        async with self._lock:
            if channel_id in self._buckets:
                bucket = self._buckets[channel_id]
                bucket.tokens = float(bucket.burst)
                bucket.last_refill = time.monotonic()

    async def remove_channel(self, channel_id: str) -> None:
        """Remove a channel's bucket configuration.

        Args:
            channel_id: The ID of the channel.
        """
        async with self._lock:
            self._buckets.pop(channel_id, None)
