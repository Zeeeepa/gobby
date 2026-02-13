import json
import logging
from datetime import UTC, datetime
from typing import Any

from gobby.storage.database import DatabaseProtocol

from .definitions import WorkflowInstance, WorkflowState

logger = logging.getLogger(__name__)


class WorkflowInstanceManager:
    """Manages CRUD operations for workflow instances (multi-workflow per session)."""

    def __init__(self, db: DatabaseProtocol):
        self.db = db

    def get_instance(self, session_id: str, workflow_name: str) -> WorkflowInstance | None:
        """Get a specific workflow instance by session and workflow name."""
        row = self.db.fetchone(
            "SELECT * FROM workflow_instances WHERE session_id = ? AND workflow_name = ?",
            (session_id, workflow_name),
        )
        if not row:
            return None
        return self._row_to_instance(row)

    def get_active_instances(self, session_id: str) -> list[WorkflowInstance]:
        """Get all enabled workflow instances for a session, sorted by priority."""
        rows = self.db.fetchall(
            "SELECT * FROM workflow_instances WHERE session_id = ? AND enabled = 1 "
            "ORDER BY priority ASC",
            (session_id,),
        )
        return [self._row_to_instance(row) for row in rows]

    def save_instance(self, instance: WorkflowInstance) -> None:
        """Create or update a workflow instance (upsert on session_id + workflow_name)."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            """
            INSERT INTO workflow_instances (
                id, session_id, workflow_name, enabled, priority,
                current_step, step_entered_at, step_action_count, total_action_count,
                variables, context_injected, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, workflow_name) DO UPDATE SET
                enabled = excluded.enabled,
                priority = excluded.priority,
                current_step = excluded.current_step,
                step_entered_at = excluded.step_entered_at,
                step_action_count = excluded.step_action_count,
                total_action_count = excluded.total_action_count,
                variables = excluded.variables,
                context_injected = excluded.context_injected,
                updated_at = excluded.updated_at
            """,
            (
                instance.id,
                instance.session_id,
                instance.workflow_name,
                1 if instance.enabled else 0,
                instance.priority,
                instance.current_step,
                instance.step_entered_at.isoformat() if instance.step_entered_at else None,
                instance.step_action_count,
                instance.total_action_count,
                json.dumps(instance.variables),
                1 if instance.context_injected else 0,
                now,
                now,
            ),
        )

    def delete_instance(self, session_id: str, workflow_name: str) -> None:
        """Delete a workflow instance."""
        self.db.execute(
            "DELETE FROM workflow_instances WHERE session_id = ? AND workflow_name = ?",
            (session_id, workflow_name),
        )

    def set_enabled(self, session_id: str, workflow_name: str, enabled: bool) -> None:
        """Toggle the enabled state of a workflow instance."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "UPDATE workflow_instances SET enabled = ?, updated_at = ? "
            "WHERE session_id = ? AND workflow_name = ?",
            (1 if enabled else 0, now, session_id, workflow_name),
        )

    @staticmethod
    def _row_to_instance(row: Any) -> WorkflowInstance:
        """Convert a database row to a WorkflowInstance."""
        return WorkflowInstance(
            id=row["id"],
            session_id=row["session_id"],
            workflow_name=row["workflow_name"],
            enabled=bool(row["enabled"]),
            priority=row["priority"],
            current_step=row["current_step"],
            step_entered_at=(
                datetime.fromisoformat(row["step_entered_at"])
                if row["step_entered_at"]
                else None
            ),
            step_action_count=row["step_action_count"],
            total_action_count=row["total_action_count"],
            variables=json.loads(row["variables"]) if row["variables"] else {},
            context_injected=bool(row["context_injected"]),
            created_at=(
                datetime.fromisoformat(row["created_at"])
                if row["created_at"]
                else datetime.now(UTC)
            ),
            updated_at=(
                datetime.fromisoformat(row["updated_at"])
                if row["updated_at"]
                else datetime.now(UTC)
            ),
        )


class WorkflowStateManager:
    """
    Manages persistence of WorkflowState and Handoffs.
    """

    def __init__(self, db: DatabaseProtocol):
        self.db = db

    def get_state(self, session_id: str) -> WorkflowState | None:
        row = self.db.fetchone("SELECT * FROM workflow_states WHERE session_id = ?", (session_id,))
        if not row:
            return None

        try:
            return WorkflowState(
                session_id=row["session_id"],
                workflow_name=row["workflow_name"],
                step=row["step"],
                step_entered_at=(
                    datetime.fromisoformat(row["step_entered_at"])
                    if row["step_entered_at"]
                    else datetime.now(UTC)
                ),
                step_action_count=row["step_action_count"],
                total_action_count=row["total_action_count"],
                observations=json.loads(row["observations"]) if row["observations"] else [],
                reflection_pending=bool(row["reflection_pending"]),
                context_injected=bool(row["context_injected"]),
                variables=json.loads(row["variables"]) if row["variables"] else {},
                task_list=json.loads(row["task_list"]) if row["task_list"] else None,
                current_task_index=row["current_task_index"],
                files_modified_this_task=row["files_modified_this_task"],
                updated_at=(
                    datetime.fromisoformat(row["updated_at"])
                    if row["updated_at"]
                    else datetime.now(UTC)
                ),
            )
        except Exception as e:
            logger.error(
                f"Failed to parse workflow state for session {session_id}: {e}", exc_info=True
            )
            return None

    def save_state(self, state: WorkflowState) -> None:
        """Upsert workflow state."""
        self.db.execute(
            """
            INSERT INTO workflow_states (
                session_id, workflow_name, step, step_entered_at,
                step_action_count, total_action_count,
                observations, reflection_pending, context_injected, variables,
                task_list, current_task_index, files_modified_this_task,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                workflow_name = excluded.workflow_name,
                step = excluded.step,
                step_entered_at = excluded.step_entered_at,
                step_action_count = excluded.step_action_count,
                total_action_count = excluded.total_action_count,
                observations = excluded.observations,
                reflection_pending = excluded.reflection_pending,
                context_injected = excluded.context_injected,
                variables = excluded.variables,
                task_list = excluded.task_list,
                current_task_index = excluded.current_task_index,
                files_modified_this_task = excluded.files_modified_this_task,
                updated_at = excluded.updated_at
            """,
            (
                state.session_id,
                state.workflow_name,
                state.step,
                state.step_entered_at.isoformat(),
                state.step_action_count,
                state.total_action_count,
                json.dumps(state.observations),
                1 if state.reflection_pending else 0,
                1 if state.context_injected else 0,
                json.dumps(state.variables),
                json.dumps(state.task_list) if state.task_list else None,
                state.current_task_index,
                state.files_modified_this_task,
                datetime.now(UTC).isoformat(),
            ),
        )

    def merge_variables(self, session_id: str, updates: dict[str, Any]) -> bool:
        """Atomically merge variable updates into existing state.

        Uses BEGIN IMMEDIATE to serialize the read-modify-write,
        preventing concurrent evaluations from clobbering each other.

        Returns:
            True if the merge succeeded, False if the session was not found.
        """
        if not updates:
            return True
        with self.db.transaction_immediate() as conn:
            row = conn.execute(
                "SELECT variables FROM workflow_states WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                logger.warning(
                    "merge_variables: no workflow state found for session %s", session_id
                )
                return False
            current = json.loads(row["variables"]) if row["variables"] else {}
            current.update(updates)
            conn.execute(
                "UPDATE workflow_states SET variables = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(current), datetime.now(UTC).isoformat(), session_id),
            )
            return True

    def update_orchestration_lists(
        self,
        session_id: str,
        *,
        remove_from_spawned: set[str] | None = None,
        append_to_spawned: list[dict[str, Any]] | None = None,
        append_to_completed: list[dict[str, Any]] | None = None,
        append_to_failed: list[dict[str, Any]] | None = None,
        replace_spawned: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Atomically update orchestration tracking lists.

        Uses BEGIN IMMEDIATE to serialize the read-modify-write,
        preventing concurrent poll_agent_status and orchestrate_ready_tasks
        from clobbering each other's list updates.

        Args:
            session_id: The orchestrator session whose state to update.
            remove_from_spawned: Session IDs to remove from spawned_agents.
            append_to_spawned: New agent dicts to append to spawned_agents.
            append_to_completed: Agent dicts to append to completed_agents.
            append_to_failed: Agent dicts to append to failed_agents.
            replace_spawned: If set, replaces spawned_agents entirely
                (takes precedence over remove_from_spawned).

        Returns:
            True if the update succeeded, False if session not found.
        """
        with self.db.transaction_immediate() as conn:
            row = conn.execute(
                "SELECT variables FROM workflow_states WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                logger.warning(
                    "update_orchestration_lists: no workflow state for session %s",
                    session_id,
                )
                return False

            variables = json.loads(row["variables"]) if row["variables"] else {}

            # Update spawned_agents
            if replace_spawned is not None:
                variables["spawned_agents"] = replace_spawned
            elif remove_from_spawned:
                current = variables.get("spawned_agents", [])
                variables["spawned_agents"] = [
                    a for a in current if a.get("session_id") not in remove_from_spawned
                ]

            if append_to_spawned:
                current = variables.get("spawned_agents", [])
                current.extend(append_to_spawned)
                variables["spawned_agents"] = current

            # Update completed_agents
            if append_to_completed:
                current = variables.get("completed_agents", [])
                current.extend(append_to_completed)
                variables["completed_agents"] = current

            # Update failed_agents
            if append_to_failed:
                current = variables.get("failed_agents", [])
                current.extend(append_to_failed)
                variables["failed_agents"] = current

            conn.execute(
                "UPDATE workflow_states SET variables = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(variables), datetime.now(UTC).isoformat(), session_id),
            )
            return True

    def check_and_reserve_slots(
        self,
        session_id: str,
        max_concurrent: int,
        requested: int,
    ) -> int:
        """Atomically check capacity and reserve spawn slots.

        Prevents concurrent orchestrate_ready_tasks calls from both seeing
        capacity and both spawning, exceeding max_concurrent.

        Uses _reserved_slots counter in variables to track pending spawns.
        Caller MUST call release_reserved_slots after spawning completes
        (whether success or failure).

        Args:
            session_id: Orchestrator session ID.
            max_concurrent: Maximum concurrent agents allowed.
            requested: Number of slots requested.

        Returns:
            Number of slots actually reserved (0 if at capacity).
        """
        with self.db.transaction_immediate() as conn:
            row = conn.execute(
                "SELECT variables FROM workflow_states WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return 0

            variables = json.loads(row["variables"]) if row["variables"] else {}
            spawned_count = len(variables.get("spawned_agents", []))
            reserved: int = int(variables.get("_reserved_slots") or 0)
            total_active = spawned_count + reserved
            available = max(0, max_concurrent - total_active)
            slots: int = min(available, requested)

            if slots > 0:
                variables["_reserved_slots"] = reserved + slots
                conn.execute(
                    "UPDATE workflow_states SET variables = ?, updated_at = ? WHERE session_id = ?",
                    (json.dumps(variables), datetime.now(UTC).isoformat(), session_id),
                )

            return slots

    def release_reserved_slots(self, session_id: str, count: int) -> None:
        """Release reserved spawn slots after spawning completes or fails.

        Args:
            session_id: Orchestrator session ID.
            count: Number of slots to release.
        """
        if count <= 0:
            return
        with self.db.transaction_immediate() as conn:
            row = conn.execute(
                "SELECT variables FROM workflow_states WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return

            variables = json.loads(row["variables"]) if row["variables"] else {}
            current_reserved: int = int(variables.get("_reserved_slots") or 0)
            variables["_reserved_slots"] = max(0, current_reserved - count)
            conn.execute(
                "UPDATE workflow_states SET variables = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(variables), datetime.now(UTC).isoformat(), session_id),
            )

    def delete_state(self, session_id: str) -> None:
        """
        Clear step workflow state while preserving lifecycle variables.

        This clears workflow_name, step, and related step-tracking fields,
        but keeps the `variables` JSON which contains lifecycle workflow
        state like unlocked_tools, task_claimed, etc.

        Uses '__ended__' placeholder instead of NULL to satisfy NOT NULL constraints.
        """
        self.db.execute(
            """
            UPDATE workflow_states SET
                workflow_name = '__ended__',
                step = '__ended__',
                step_entered_at = NULL,
                step_action_count = 0,
                total_action_count = 0,
                observations = '[]',
                reflection_pending = 0,
                context_injected = 0,
                task_list = NULL,
                current_task_index = 0,
                files_modified_this_task = 0,
                updated_at = ?
            WHERE session_id = ?
            """,
            (datetime.now(UTC).isoformat(), session_id),
        )
