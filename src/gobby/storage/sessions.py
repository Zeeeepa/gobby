"""Local session storage manager."""

from __future__ import annotations

import builtins
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from gobby.storage.database import LocalDatabase

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Session data model."""

    id: str
    external_id: str
    machine_id: str
    source: str
    project_id: str  # Required - sessions must belong to a project
    title: str | None
    status: str
    jsonl_path: str | None
    summary_path: str | None
    summary_markdown: str | None
    compact_markdown: str | None  # Handoff context for compaction
    git_branch: str | None
    parent_session_id: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: Any) -> Session:
        """Create Session from database row."""
        return cls(
            id=row["id"],
            external_id=row["external_id"],
            machine_id=row["machine_id"],
            source=row["source"],
            project_id=row["project_id"],
            title=row["title"],
            status=row["status"],
            jsonl_path=row["jsonl_path"],
            summary_path=row["summary_path"],
            summary_markdown=row["summary_markdown"],
            compact_markdown=row["compact_markdown"],
            git_branch=row["git_branch"],
            parent_session_id=row["parent_session_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "external_id": self.external_id,
            "machine_id": self.machine_id,
            "source": self.source,
            "project_id": self.project_id,
            "title": self.title,
            "status": self.status,
            "jsonl_path": self.jsonl_path,
            "summary_path": self.summary_path,
            "summary_markdown": self.summary_markdown,
            "compact_markdown": self.compact_markdown,
            "git_branch": self.git_branch,
            "parent_session_id": self.parent_session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class LocalSessionManager:
    """Manager for local session storage."""

    def __init__(self, db: LocalDatabase):
        """Initialize with database connection."""
        self.db = db

    def register(
        self,
        external_id: str,
        machine_id: str,
        source: str,
        project_id: str,
        title: str | None = None,
        jsonl_path: str | None = None,
        git_branch: str | None = None,
        parent_session_id: str | None = None,
    ) -> Session:
        """
        Register a new session or return existing one.

        Looks up by (external_id, machine_id, project_id, source) to find if this
        exact session already exists (e.g., daemon restarted mid-session). If found,
        returns the existing session. Otherwise creates a new one.

        Args:
            external_id: External session identifier (e.g., Claude Code's session ID)
            machine_id: Machine identifier
            source: CLI source (claude_code, codex, gemini)
            project_id: Project ID (required - sessions must belong to a project)
            title: Optional session title
            jsonl_path: Path to transcript file
            git_branch: Git branch name
            parent_session_id: Parent session for handoff

        Returns:
            Session instance
        """
        now = datetime.now(UTC).isoformat()

        # Check if this exact session already exists (daemon restart case)
        existing = self.find_by_external_id(external_id, machine_id, project_id, source)
        if existing:
            # Session exists - update metadata and return it
            self.db.execute(
                """
                UPDATE sessions SET
                    title = COALESCE(?, title),
                    jsonl_path = COALESCE(?, jsonl_path),
                    git_branch = COALESCE(?, git_branch),
                    parent_session_id = COALESCE(?, parent_session_id),
                    status = 'active',
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    title,
                    jsonl_path,
                    git_branch,
                    parent_session_id,
                    now,
                    existing.id,
                ),
            )
            logger.debug(f"Reusing existing session {existing.id} for external_id={external_id}")
            return self.get(existing.id)  # type: ignore

        # New session - create it
        session_id = str(uuid.uuid4())
        self.db.execute(
            """
            INSERT INTO sessions (
                id, external_id, machine_id, source, project_id, title,
                jsonl_path, git_branch, parent_session_id,
                status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                session_id,
                external_id,
                machine_id,
                source,
                project_id,
                title,
                jsonl_path,
                git_branch,
                parent_session_id,
                now,
                now,
            ),
        )
        logger.debug(f"Created new session {session_id} for external_id={external_id}")

        return self.get(session_id)  # type: ignore

    def get(self, session_id: str) -> Session | None:
        """Get session by ID."""
        row = self.db.fetchone("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return Session.from_row(row) if row else None

    def find_current(
        self,
        external_id: str,
        machine_id: str,
        source: str,
    ) -> Session | None:
        """Find current session by external_id, machine_id, and source."""
        row = self.db.fetchone(
            """
            SELECT * FROM sessions
            WHERE external_id = ? AND machine_id = ? AND source = ?
            """,
            (external_id, machine_id, source),
        )
        return Session.from_row(row) if row else None

    def find_by_external_id(
        self,
        external_id: str,
        machine_id: str,
        project_id: str,
        source: str,
    ) -> Session | None:
        """
        Find session by external_id, machine_id, project_id, and source.

        This is the primary lookup for reconnecting to an existing session
        after daemon restart. The external_id (e.g., Claude Code's session ID)
        is stable within a session.

        Args:
            external_id: External session identifier
            machine_id: Machine identifier
            project_id: Project identifier
            source: CLI source (claude, gemini, codex)

        Returns:
            Session if found, None otherwise.
        """
        row = self.db.fetchone(
            """
            SELECT * FROM sessions
            WHERE external_id = ? AND machine_id = ? AND project_id = ? AND source = ?
            """,
            (external_id, machine_id, project_id, source),
        )
        return Session.from_row(row) if row else None

    def find_parent(
        self,
        machine_id: str,
        project_id: str,
        source: str | None = None,
        status: str = "handoff_ready",
    ) -> Session | None:
        """
        Find most recent parent session with specific status.

        Args:
            machine_id: Machine identifier
            project_id: Project identifier
            source: Optional source identifier to filter by
            status: Status to filter by (default: handoff_ready)

        Returns:
            Session object or None
        """
        query = "SELECT * FROM sessions WHERE machine_id = ? AND status = ? AND project_id = ?"
        params: list[Any] = [machine_id, status, project_id]

        if source:
            query += " AND source = ?"
            params.append(source)

        query += " ORDER BY updated_at DESC LIMIT 1"

        row = self.db.fetchone(query, tuple(params))
        return Session.from_row(row) if row else None

    def update_status(self, session_id: str, status: str) -> Session | None:
        """Update session status."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, session_id),
        )
        return self.get(session_id)

    def update_title(self, session_id: str, title: str) -> Session | None:
        """Update session title."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, session_id),
        )
        return self.get(session_id)

    def update_summary(
        self,
        session_id: str,
        summary_path: str | None = None,
        summary_markdown: str | None = None,
    ) -> Session | None:
        """Update session summary."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            """
            UPDATE sessions
            SET summary_path = COALESCE(?, summary_path),
                summary_markdown = COALESCE(?, summary_markdown),
                updated_at = ?
            WHERE id = ?
            """,
            (summary_path, summary_markdown, now, session_id),
        )
        return self.get(session_id)

    def update_compact_markdown(self, session_id: str, compact_markdown: str) -> Session | None:
        """Update session compact handoff markdown."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            """
            UPDATE sessions
            SET compact_markdown = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (compact_markdown, now, session_id),
        )
        return self.get(session_id)

    def update_parent_session_id(self, session_id: str, parent_session_id: str) -> Session | None:
        """Update parent session ID."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "UPDATE sessions SET parent_session_id = ?, updated_at = ? WHERE id = ?",
            (parent_session_id, now, session_id),
        )
        return self.get(session_id)

    def list(
        self,
        project_id: str | None = None,
        status: str | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[Session]:
        """
        List sessions with optional filters.

        Args:
            project_id: Filter by project
            status: Filter by status
            source: Filter by CLI source
            limit: Maximum number of results

        Returns:
            List of Session instances
        """
        conditions = []
        params: list[Any] = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if source:
            conditions.append("source = ?")
            params.append(source)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        rows = self.db.fetchall(
            f"""
            SELECT * FROM sessions
            WHERE {where_clause}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        )
        return [Session.from_row(row) for row in rows]

    def count(
        self,
        project_id: str | None = None,
        status: str | None = None,
        source: str | None = None,
    ) -> int:
        """
        Count sessions with optional filters.

        Args:
            project_id: Filter by project
            status: Filter by status
            source: Filter by CLI source

        Returns:
            Count of matching sessions
        """
        conditions = []
        params: list[Any] = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if source:
            conditions.append("source = ?")
            params.append(source)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        result = self.db.fetchone(
            f"SELECT COUNT(*) as count FROM sessions WHERE {where_clause}",
            tuple(params),
        )
        return result["count"] if result else 0

    def count_by_status(self) -> dict[str, int]:
        """
        Count sessions grouped by status.

        Returns:
            Dictionary mapping status to count
        """
        rows = self.db.fetchall("SELECT status, COUNT(*) as count FROM sessions GROUP BY status")
        return {row["status"]: row["count"] for row in rows}

    def delete(self, session_id: str) -> bool:
        """Delete session by ID."""
        cursor = self.db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return bool(cursor.rowcount and cursor.rowcount > 0)

    def expire_stale_sessions(self, timeout_hours: int = 24) -> int:
        """
        Mark sessions as expired if they've been inactive for too long.

        Args:
            timeout_hours: Hours of inactivity before expiring

        Returns:
            Number of sessions expired
        """
        now = datetime.now(UTC).isoformat()
        cursor = self.db.execute(
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

    def pause_inactive_active_sessions(self, timeout_minutes: int = 30) -> int:
        """
        Mark active sessions as paused if they've been inactive for too long.

        This catches orphaned sessions that never received an AFTER_AGENT hook
        (e.g., Claude Code crashed mid-response).

        Args:
            timeout_minutes: Minutes of inactivity before pausing

        Returns:
            Number of sessions paused
        """
        now = datetime.now(UTC).isoformat()
        cursor = self.db.execute(
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

    def get_pending_transcript_sessions(self, limit: int = 10) -> builtins.list[Session]:
        """
        Get sessions that need transcript processing.

        These are expired sessions with transcript_processed = FALSE.

        Args:
            limit: Maximum sessions to return

        Returns:
            List of sessions needing processing
        """
        rows = self.db.fetchall(
            """
            SELECT * FROM sessions
            WHERE status = 'expired'
            AND transcript_processed = FALSE
            AND jsonl_path IS NOT NULL
            ORDER BY updated_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [Session.from_row(row) for row in rows]

    def mark_transcript_processed(self, session_id: str) -> Session | None:
        """
        Mark a session's transcript as fully processed.

        Args:
            session_id: Session ID

        Returns:
            Updated session or None if not found
        """
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "UPDATE sessions SET transcript_processed = TRUE, updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        return self.get(session_id)

    def reset_transcript_processed(self, session_id: str) -> Session | None:
        """
        Reset transcript_processed flag when a session is resumed.

        Args:
            session_id: Session ID

        Returns:
            Updated session or None if not found
        """
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "UPDATE sessions SET transcript_processed = FALSE, updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        return self.get(session_id)
