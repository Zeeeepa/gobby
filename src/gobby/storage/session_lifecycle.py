"""Session lifecycle operations.

Standalone functions for expiring and pausing inactive sessions.
Extracted from LocalSessionManager as part of the Strangler Fig
decomposition.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


def expire_stale_sessions(db: DatabaseProtocol, timeout_hours: int = 24) -> int:
    """
    Mark sessions as expired if they've been inactive for too long.

    Args:
        db: Database connection.
        timeout_hours: Hours of inactivity before expiring.

    Returns:
        Number of sessions expired.
    """
    now = datetime.now(UTC).isoformat()
    cursor = db.execute(
        """
        UPDATE sessions
        SET status = 'expired', updated_at = ?
        WHERE status IN ('active', 'paused', 'handoff_ready')
        AND datetime(updated_at) < datetime('now', 'utc', ? || ' hours')
        """,
        (now, f"-{timeout_hours}"),
    )
    count = cursor.rowcount or 0
    if count > 0:
        logger.info(f"Expired {count} stale sessions (>{timeout_hours}h inactive)")
    return count


def pause_inactive_active_sessions(db: DatabaseProtocol, timeout_minutes: int = 30) -> int:
    """
    Mark active sessions as paused if they've been inactive for too long.

    This catches orphaned sessions that never received an AFTER_AGENT hook
    (e.g., Claude Code crashed mid-response).

    Args:
        db: Database connection.
        timeout_minutes: Minutes of inactivity before pausing.

    Returns:
        Number of sessions paused.
    """
    now = datetime.now(UTC).isoformat()
    cursor = db.execute(
        """
        UPDATE sessions
        SET status = 'paused', updated_at = ?
        WHERE status = 'active'
        AND datetime(updated_at) < datetime('now', 'utc', ? || ' minutes')
        """,
        (now, f"-{timeout_minutes}"),
    )
    count = cursor.rowcount or 0
    if count > 0:
        logger.info(f"Paused {count} inactive active sessions (>{timeout_minutes}m)")
    return count
