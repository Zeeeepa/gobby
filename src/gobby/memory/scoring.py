"""Scoring helpers for memory search ranking."""

from __future__ import annotations

import math
from datetime import UTC, datetime


def temporal_decay(
    updated_at: str,
    half_life_days: float,
    now: datetime | None = None,
) -> float:
    """Return a multiplicative decay factor in (0, 1] based on memory age.

    Uses a half-life model: ``factor = 0.5 ^ (age_days / half_life_days)``.

    Args:
        updated_at: ISO-format timestamp of last memory update.
        half_life_days: Number of days after which the factor reaches 0.5.
            Set to 0 (or negative) to disable decay (returns 1.0).
        now: Reference time for age calculation. Defaults to ``datetime.now(UTC)``.

    Returns:
        Decay factor between 0 (exclusive) and 1 (inclusive).
        Returns 1.0 on parse failure or when decay is disabled.
    """
    if half_life_days <= 0:
        return 1.0
    try:
        updated = datetime.fromisoformat(updated_at)
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        if now is None:
            now = datetime.now(UTC)
        age_days = max((now - updated).total_seconds() / 86400.0, 0.0)
        return math.pow(0.5, age_days / half_life_days)
    except (ValueError, TypeError):
        return 1.0
