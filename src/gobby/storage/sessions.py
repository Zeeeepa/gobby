"""Local session storage manager."""

from __future__ import annotations

import builtins
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from gobby.storage.database import DatabaseProtocol

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
    agent_depth: int = 0  # 0 = human-initiated, 1+ = agent-spawned
    spawned_by_agent_id: str | None = None  # ID of agent that spawned this session
    # Terminal pickup metadata fields
    workflow_name: str | None = None  # Workflow to activate on terminal pickup
    agent_run_id: str | None = None  # Link back to agent run record
    context_injected: bool = False  # Whether context was injected into prompt
    original_prompt: str | None = None  # Original prompt for terminal mode
    # Usage tracking fields
    usage_input_tokens: int = 0
    usage_output_tokens: int = 0
    usage_cache_creation_tokens: int = 0
    usage_cache_read_tokens: int = 0
    usage_total_cost_usd: float = 0.0
    model: str | None = None  # LLM model used (e.g., "claude-3-5-sonnet-20241022")
    # Terminal context (JSON blob with tty, parent_pid, term_session_id, etc.)
    terminal_context: dict[str, Any] | None = None
    # Global sequence number
    seq_num: int | None = None
    # Edit history tracking
    had_edits: bool = False

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
            agent_depth=row["agent_depth"] or 0,
            spawned_by_agent_id=row["spawned_by_agent_id"],
            workflow_name=row["workflow_name"],
            agent_run_id=row["agent_run_id"],
            context_injected=bool(row["context_injected"]),
            original_prompt=row["original_prompt"],
            usage_input_tokens=row["usage_input_tokens"] or 0,
            usage_output_tokens=row["usage_output_tokens"] or 0,
            usage_cache_creation_tokens=row["usage_cache_creation_tokens"] or 0,
            usage_cache_read_tokens=row["usage_cache_read_tokens"] or 0,
            usage_total_cost_usd=row["usage_total_cost_usd"] or 0.0,
            model=row["model"] if "model" in row.keys() else None,
            terminal_context=cls._parse_terminal_context(row["terminal_context"]),
            seq_num=row["seq_num"] if "seq_num" in row.keys() else None,
            had_edits=bool(row["had_edits"]) if "had_edits" in row.keys() else False,
        )

    @classmethod
    def _parse_terminal_context(cls, raw: str | None) -> dict[str, Any] | None:
        """Parse terminal_context JSON, returning None on malformed data.

        Args:
            raw: Raw JSON string or None

        Returns:
            Parsed dict or None if parsing fails or input is None
        """
        if not raw:
            return None
        try:
            result: dict[str, Any] = json.loads(raw)
            return result
        except json.JSONDecodeError:
            logger.warning("Failed to parse terminal_context JSON, returning None")
            return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ref": f"#{self.seq_num}" if self.seq_num else self.id[:8],
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
            "agent_depth": self.agent_depth,
            "spawned_by_agent_id": self.spawned_by_agent_id,
            "workflow_name": self.workflow_name,
            "agent_run_id": self.agent_run_id,
            "context_injected": self.context_injected,
            "original_prompt": self.original_prompt,
            "usage_input_tokens": self.usage_input_tokens,
            "usage_output_tokens": self.usage_output_tokens,
            "usage_cache_creation_tokens": self.usage_cache_creation_tokens,
            "usage_cache_read_tokens": self.usage_cache_read_tokens,
            "usage_total_cost_usd": self.usage_total_cost_usd,
            "terminal_context": self.terminal_context,
            "had_edits": self.had_edits,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "seq_num": self.seq_num,
            "id": self.id,  # UUID at end for backwards compat
        }


class LocalSessionManager:
    """Manager for local session storage."""

    def __init__(self, db: DatabaseProtocol):
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
        agent_depth: int = 0,
        spawned_by_agent_id: str | None = None,
        terminal_context: dict[str, Any] | None = None,
        workflow_name: str | None = None,
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
            agent_depth: Nesting depth (0 = human-initiated, 1+ = agent-spawned)
            spawned_by_agent_id: ID of the agent that spawned this session

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
            session = self.get(existing.id)
            if session is None:
                raise RuntimeError(f"Session {existing.id} disappeared during update")
            return session

        # New session - create it
        session_id = str(uuid.uuid4())

        # Retry loop for seq_num assignment
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Get next seq_num (per-project)
                max_seq_row = self.db.fetchone(
                    "SELECT MAX(seq_num) as max_seq FROM sessions WHERE project_id = ?",
                    (project_id,),
                )
                next_seq_num = ((max_seq_row["max_seq"] if max_seq_row else None) or 0) + 1

                self.db.execute(
                    """
                    INSERT INTO sessions (
                        id, external_id, machine_id, source, project_id, title,
                        jsonl_path, git_branch, parent_session_id,
                        agent_depth, spawned_by_agent_id, terminal_context,
                        workflow_name, status, created_at, updated_at, seq_num, had_edits
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, 0)
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
                        agent_depth,
                        spawned_by_agent_id,
                        json.dumps(terminal_context) if terminal_context else None,
                        workflow_name,
                        now,
                        now,
                        next_seq_num,
                    ),
                )
                break
            except Exception as e:
                # Check for unique constraint violation on seq_num
                if (
                    "UNIQUE constraint failed: sessions.seq_num" in str(e)
                    and attempt < max_retries - 1
                ):
                    logger.warning(f"Seq_num collision ({next_seq_num}), retrying...")
                    continue
                raise

        logger.debug(f"Created new session {session_id} for external_id={external_id}")

        session = self.get(session_id)
        if session is None:
            raise RuntimeError(f"Session {session_id} not found after creation")
        return session

    def get(self, session_id: str) -> Session | None:
        """Get session by ID."""
        row = self.db.fetchone("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return Session.from_row(row) if row else None

    def resolve_session_reference(self, ref: str, project_id: str | None = None) -> str:
        """
        Resolve a session reference to a UUID.

        Supports:
        - #N: Project-scoped Sequence Number (e.g., #1) - requires project_id
        - N: Integer string treated as #N (e.g., "1")
        - UUID: Full UUID
        - Prefix: UUID prefix (must be unambiguous)

        Args:
            ref: Session reference string
            project_id: Project ID for project-scoped #N lookup.
                If not provided, falls back to global lookup for backwards compat.

        Returns:
            Resolved Session UUID

        Raises:
            ValueError: If not found or ambiguous
        """
        if not ref:
            raise ValueError("Empty session reference")

        # #N or N format: seq_num lookup
        seq_num_ref = ref
        if ref.startswith("#"):
            seq_num_ref = ref[1:]

        if seq_num_ref.isdigit():
            seq_num = int(seq_num_ref)
            if project_id:
                # Project-scoped lookup
                row = self.db.fetchone(
                    "SELECT id FROM sessions WHERE project_id = ? AND seq_num = ?",
                    (project_id, seq_num),
                )
            else:
                # Fallback to global lookup for backwards compat
                row = self.db.fetchone("SELECT id FROM sessions WHERE seq_num = ?", (seq_num,))
            if not row:
                raise ValueError(f"Session #{seq_num} not found")
            return str(row["id"])

        # Full UUID check
        try:
            uuid_obj = uuid.UUID(ref)
            # Verify the session exists in the database
            row = self.db.fetchone("SELECT id FROM sessions WHERE id = ?", (str(uuid_obj),))
            if not row:
                raise ValueError(f"Session '{ref}' not found")
            return str(uuid_obj)
        except ValueError:
            pass  # Not a valid UUID, try prefix

        # Prefix matching
        rows = self.db.fetchall("SELECT id FROM sessions WHERE id LIKE ? LIMIT 5", (f"{ref}%",))
        if not rows:
            raise ValueError(f"Session '{ref}' not found")
        if len(rows) > 1:
            matches = [str(r["id"]) for r in rows]
            raise ValueError(f"Ambiguous session '{ref}' matches: {', '.join(matches[:3])}...")

        return str(rows[0]["id"])

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

    def find_children(self, parent_session_id: str) -> list[Session]:
        """
        Find all child sessions of a parent.

        Args:
            parent_session_id: The parent session ID.

        Returns:
            List of child Session objects.
        """
        rows = self.db.fetchall(
            """
            SELECT * FROM sessions
            WHERE parent_session_id = ?
            ORDER BY created_at ASC
            """,
            (parent_session_id,),
        )
        return [Session.from_row(row) for row in rows]

    def update_status(self, session_id: str, status: str) -> Session | None:
        """Update session status."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, session_id),
        )
        return self.get(session_id)

    def mark_had_edits(self, session_id: str) -> Session | None:
        """Mark session as having edits."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "UPDATE sessions SET had_edits = 1, updated_at = ? WHERE id = ?",
            (now, session_id),
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

    def update_model(self, session_id: str, model: str) -> Session | None:
        """Update session model (LLM model used)."""
        now = datetime.now(UTC).isoformat()
        with self.db.transaction():
            self.db.execute(
                "UPDATE sessions SET model = ?, updated_at = ? WHERE id = ?",
                (model, now, session_id),
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

    def update(
        self,
        session_id: str,
        *,
        external_id: str | None = None,
        jsonl_path: str | None = None,
        status: str | None = None,
        title: str | None = None,
        git_branch: str | None = None,
    ) -> Session | None:
        """
        Update multiple session fields at once.

        Args:
            session_id: Session ID to update
            external_id: New external ID (optional)
            jsonl_path: New transcript path (optional)
            status: New status (optional)
            title: New title (optional)
            git_branch: New git branch (optional)

        Returns:
            Updated Session or None if not found
        """
        values: dict[str, Any] = {}

        if external_id is not None:
            values["external_id"] = external_id
        if jsonl_path is not None:
            values["jsonl_path"] = jsonl_path
        if status is not None:
            values["status"] = status
        if title is not None:
            values["title"] = title
        if git_branch is not None:
            values["git_branch"] = git_branch

        if not values:
            return self.get(session_id)

        values["updated_at"] = datetime.now(UTC).isoformat()

        self.db.safe_update("sessions", values, "id = ?", (session_id,))
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

        # nosec B608: where_clause built from hardcoded condition strings, values parameterized
        rows = self.db.fetchall(
            f"""
            SELECT * FROM sessions
            WHERE {where_clause}
            ORDER BY updated_at DESC
            LIMIT ?
            """,  # nosec B608
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

        # nosec B608: where_clause built from hardcoded condition strings, values parameterized
        result = self.db.fetchone(
            f"SELECT COUNT(*) as count FROM sessions WHERE {where_clause}",  # nosec B608
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

    def update_usage(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int,
        cache_read_tokens: int,
        total_cost_usd: float,
    ) -> bool:
        """Update session usage statistics."""
        query = """
        UPDATE sessions
        SET
            usage_input_tokens = ?,
            usage_output_tokens = ?,
            usage_cache_creation_tokens = ?,
            usage_cache_read_tokens = ?,
            usage_total_cost_usd = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """
        try:
            with self.db.transaction():
                cursor = self.db.execute(
                    query,
                    (
                        input_tokens,
                        output_tokens,
                        cache_creation_tokens,
                        cache_read_tokens,
                        total_cost_usd,
                        session_id,
                    ),
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update session usage {session_id}: {e}")
            return False

    def add_cost(self, session_id: str, cost_usd: float) -> bool:
        """
        Add cost to the session's usage_total_cost_usd.

        This is used for internal agent runs that track cost via CostInfo.
        Unlike update_usage which overwrites, this method adds to the existing cost.

        Args:
            session_id: Session ID to update.
            cost_usd: Cost in USD to add.

        Returns:
            True if update succeeded, False otherwise.
        """
        if cost_usd <= 0:
            return True  # Nothing to add

        query = """
        UPDATE sessions
        SET
            usage_total_cost_usd = COALESCE(usage_total_cost_usd, 0) + ?,
            updated_at = datetime('now')
        WHERE id = ?
        """
        try:
            with self.db.transaction():
                cursor = self.db.execute(query, (cost_usd, session_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to add cost to session {session_id}: {e}")
            return False

    def get_sessions_since(
        self, since: datetime, project_id: str | None = None
    ) -> builtins.list[Session]:
        """
        Get sessions created since a given timestamp.

        Used for aggregating usage over a time period (e.g., daily budget tracking).

        Args:
            since: Datetime to query from (sessions created after this time)
            project_id: Optional project ID to filter by

        Returns:
            List of sessions created since the given timestamp
        """
        since_str = since.isoformat()

        if project_id:
            rows = self.db.fetchall(
                """
                SELECT * FROM sessions
                WHERE created_at >= ?
                AND project_id = ?
                ORDER BY created_at DESC
                """,
                (since_str, project_id),
            )
        else:
            rows = self.db.fetchall(
                """
                SELECT * FROM sessions
                WHERE created_at >= ?
                ORDER BY created_at DESC
                """,
                (since_str,),
            )

        return [Session.from_row(row) for row in rows]

    def update_terminal_pickup_metadata(
        self,
        session_id: str,
        workflow_name: str | None = None,
        agent_run_id: str | None = None,
        context_injected: bool | None = None,
        original_prompt: str | None = None,
    ) -> Session | None:
        """
        Update terminal pickup metadata for a session.

        These fields are used when a terminal-mode agent picks up its
        prepared state via hooks on session start.

        Args:
            session_id: Session ID to update.
            workflow_name: Workflow to activate on terminal pickup.
            agent_run_id: Link back to the agent run record.
            context_injected: Whether context was injected into prompt.
            original_prompt: Original prompt for the agent.

        Returns:
            Updated session or None if not found.
        """
        values: dict[str, Any] = {}

        if workflow_name is not None:
            values["workflow_name"] = workflow_name
        if agent_run_id is not None:
            values["agent_run_id"] = agent_run_id
        if context_injected is not None:
            values["context_injected"] = 1 if context_injected else 0
        if original_prompt is not None:
            values["original_prompt"] = original_prompt

        if not values:
            return self.get(session_id)

        values["updated_at"] = datetime.now(UTC).isoformat()

        self.db.safe_update("sessions", values, "id = ?", (session_id,))
        return self.get(session_id)
