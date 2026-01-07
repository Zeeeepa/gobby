import hashlib
import json
import logging
import os
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from gobby.storage.database import LocalDatabase

logger = logging.getLogger(__name__)

# Priority name to numeric value mapping
PRIORITY_MAP = {"low": 3, "medium": 2, "high": 1, "critical": 0}


def normalize_priority(priority: int | str | None) -> int:
    """Convert priority to numeric value for sorting."""
    if priority is None:
        return 999
    if isinstance(priority, str):
        # Check if it's a named priority
        if priority.lower() in PRIORITY_MAP:
            return PRIORITY_MAP[priority.lower()]
        # Try to parse as int
        try:
            return int(priority)
        except ValueError:
            return 999
    return int(priority)


UNSET: Any = object()


@dataclass
class Task:
    id: str
    project_id: str
    title: str
    status: Literal["open", "in_progress", "closed", "failed", "escalated", "needs_decomposition"]
    priority: int
    task_type: str  # bug, feature, task, epic, chore
    created_at: str
    updated_at: str
    # Optional fields
    description: str | None = None
    parent_task_id: str | None = None
    created_in_session_id: str | None = None
    closed_in_session_id: str | None = None
    closed_commit_sha: str | None = None
    closed_at: str | None = None
    assignee: str | None = None
    labels: list[str] | None = None
    closed_reason: str | None = None
    validation_status: Literal["pending", "valid", "invalid"] | None = None
    validation_feedback: str | None = None
    test_strategy: str | None = None
    complexity_score: int | None = None
    estimated_subtasks: int | None = None
    expansion_context: str | None = None
    validation_criteria: str | None = None
    use_external_validator: bool = False
    validation_fail_count: int = 0
    validation_override_reason: str | None = None  # Why agent bypassed validation
    # Workflow integration fields
    workflow_name: str | None = None
    verification: str | None = None
    sequence_order: int | None = None
    # Commit linking
    commits: list[str] | None = None
    # Escalation fields
    escalated_at: str | None = None
    escalation_reason: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Task":
        """Convert database row to Task object."""
        labels_json = row["labels"]
        labels = json.loads(labels_json) if labels_json else []

        # Handle optional columns that might not exist yet if migration pending
        keys = row.keys()

        return cls(
            id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            status=row["status"],
            priority=normalize_priority(row["priority"]),
            task_type=row["type"],  # DB column is 'type'
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            description=row["description"],
            parent_task_id=row["parent_task_id"],
            created_in_session_id=row["created_in_session_id"]
            if "created_in_session_id" in keys
            else (row["discovered_in_session_id"] if "discovered_in_session_id" in keys else None),
            closed_in_session_id=row["closed_in_session_id"]
            if "closed_in_session_id" in keys
            else None,
            closed_commit_sha=row["closed_commit_sha"] if "closed_commit_sha" in keys else None,
            closed_at=row["closed_at"] if "closed_at" in keys else None,
            assignee=row["assignee"],
            labels=labels,
            closed_reason=row["closed_reason"],
            validation_status=row["validation_status"] if "validation_status" in keys else None,
            validation_feedback=row["validation_feedback"]
            if "validation_feedback" in keys
            else None,
            test_strategy=row["test_strategy"] if "test_strategy" in keys else None,
            complexity_score=row["complexity_score"] if "complexity_score" in keys else None,
            estimated_subtasks=row["estimated_subtasks"] if "estimated_subtasks" in keys else None,
            expansion_context=row["expansion_context"] if "expansion_context" in keys else None,
            validation_criteria=row["validation_criteria"]
            if "validation_criteria" in keys
            else None,
            use_external_validator=bool(row["use_external_validator"])
            if "use_external_validator" in keys
            else False,
            validation_fail_count=row["validation_fail_count"]
            if "validation_fail_count" in keys
            else 0,
            validation_override_reason=row["validation_override_reason"]
            if "validation_override_reason" in keys
            else None,
            workflow_name=row["workflow_name"] if "workflow_name" in keys else None,
            verification=row["verification"] if "verification" in keys else None,
            sequence_order=row["sequence_order"] if "sequence_order" in keys else None,
            commits=json.loads(row["commits"]) if "commits" in keys and row["commits"] else None,
            escalated_at=row["escalated_at"] if "escalated_at" in keys else None,
            escalation_reason=row["escalation_reason"] if "escalation_reason" in keys else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert Task to dictionary."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "type": self.task_type,  # Use 'type' for API compatibility
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "description": self.description,
            "parent_task_id": self.parent_task_id,
            "created_in_session_id": self.created_in_session_id,
            "closed_in_session_id": self.closed_in_session_id,
            "closed_commit_sha": self.closed_commit_sha,
            "closed_at": self.closed_at,
            "assignee": self.assignee,
            "labels": self.labels,
            "closed_reason": self.closed_reason,
            "validation_status": self.validation_status,
            "validation_feedback": self.validation_feedback,
            "test_strategy": self.test_strategy,
            "complexity_score": self.complexity_score,
            "estimated_subtasks": self.estimated_subtasks,
            "expansion_context": self.expansion_context,
            "validation_criteria": self.validation_criteria,
            "use_external_validator": self.use_external_validator,
            "validation_fail_count": self.validation_fail_count,
            "validation_override_reason": self.validation_override_reason,
            "workflow_name": self.workflow_name,
            "verification": self.verification,
            "sequence_order": self.sequence_order,
            "commits": self.commits,
            "escalated_at": self.escalated_at,
            "escalation_reason": self.escalation_reason,
        }

    def to_brief(self) -> dict[str, Any]:
        """Convert Task to brief discovery format for list operations.

        Returns only essential fields needed for task discovery.
        Use get_task() with to_dict() for full task details.

        This follows the progressive disclosure pattern used for MCP tools:
        - list_tasks() returns brief format (8 fields)
        - get_task() returns full format (33 fields)
        """
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "type": self.task_type,
            "parent_task_id": self.parent_task_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskIDCollisionError(Exception):
    """Raised when a unique task ID cannot be generated."""

    pass


def generate_task_id(project_id: str, salt: str = "") -> str:
    """
    Generate a hash-based task ID.
    Format: gt-{hash} where hash is 6 hex chars.
    """
    # Use high-precision timestamp and random bytes
    # project_id is included to reduce collisions across projects
    data = f"{time.time_ns()}{os.urandom(8).hex()}{project_id}{salt}"
    hash_hex = hashlib.sha256(data.encode()).hexdigest()[:6]
    return f"gt-{hash_hex}"


def order_tasks_hierarchically(tasks: list[Task]) -> list[Task]:
    """
    Reorder tasks so parents appear before their children.

    The ordering is: parent -> children (recursively), then next parent -> children, etc.
    Root tasks (no parent) are sorted by priority ASC, then created_at ASC.
    Children are sorted by priority ASC, then created_at ASC within their parent.

    Returns a new list with tasks ordered hierarchically.
    """
    if not tasks:
        return []

    # Build lookup structures
    task_by_id: dict[str, Task] = {t.id: t for t in tasks}
    children_by_parent: dict[str | None, list[Task]] = {}

    for task in tasks:
        parent_id = task.parent_task_id
        # Only group under parent if parent is in the result set
        if parent_id and parent_id not in task_by_id:
            parent_id = None
        if parent_id not in children_by_parent:
            children_by_parent[parent_id] = []
        children_by_parent[parent_id].append(task)

    # Sort children within each parent group by priority ASC, created_at ASC
    for children in children_by_parent.values():
        children.sort(key=lambda t: (normalize_priority(t.priority), t.created_at))

    # Build result with DFS traversal
    result: list[Task] = []

    def add_with_children(task: Task) -> None:
        result.append(task)
        for child in children_by_parent.get(task.id, []):
            add_with_children(child)

    # Start with root tasks (no parent or parent not in result set)
    for root_task in children_by_parent.get(None, []):
        add_with_children(root_task)

    return result


# ...


class LocalTaskManager:
    def __init__(self, db: LocalDatabase):
        self.db = db
        self._change_listeners: list[Callable[[], Any]] = []

    def add_change_listener(self, listener: Callable[[], Any]) -> None:
        """Add a listener to be called when tasks change."""
        self._change_listeners.append(listener)

    def _notify_listeners(self) -> None:
        """Notify all listeners of a change."""
        for listener in self._change_listeners:
            try:
                listener()
            except Exception as e:
                logger.error(f"Error in task change listener: {e}")

    def create_task(
        self,
        project_id: str,
        title: str,
        description: str | None = None,
        parent_task_id: str | None = None,
        created_in_session_id: str | None = None,
        priority: int = 2,
        task_type: str = "task",
        assignee: str | None = None,
        labels: list[str] | None = None,
        test_strategy: str | None = None,
        complexity_score: int | None = None,
        estimated_subtasks: int | None = None,
        expansion_context: str | None = None,
        validation_criteria: str | None = None,
        use_external_validator: bool = False,
        workflow_name: str | None = None,
        verification: str | None = None,
        sequence_order: int | None = None,
    ) -> Task:
        """Create a new task with collision handling."""
        max_retries = 3
        now = datetime.now(UTC).isoformat()

        # Serialize labels
        labels_json = json.dumps(labels) if labels else None
        task_id = ""

        # Default validation status
        validation_status = "pending" if validation_criteria else None

        for attempt in range(max_retries + 1):
            try:
                task_id = generate_task_id(project_id, salt=str(attempt))

                with self.db.transaction() as conn:
                    conn.execute(
                        """
                        INSERT INTO tasks (
                            id, project_id, title, description, parent_task_id,
                            created_in_session_id, priority, type, assignee,
                            labels, status, created_at, updated_at,
                            validation_status, test_strategy, complexity_score,
                            estimated_subtasks, expansion_context,
                            validation_criteria, use_external_validator, validation_fail_count,
                            workflow_name, verification, sequence_order
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                        """,
                        (
                            task_id,
                            project_id,
                            title,
                            description,
                            parent_task_id,
                            created_in_session_id,
                            priority,
                            task_type,  # DB column is 'type'
                            assignee,
                            labels_json,
                            now,
                            now,
                            validation_status,
                            test_strategy,
                            complexity_score,
                            estimated_subtasks,
                            expansion_context,
                            validation_criteria,
                            use_external_validator,
                            workflow_name,
                            verification,
                            sequence_order,
                        ),
                    )

                logger.debug(f"Created task {task_id} in project {project_id}")

                # Auto-transition parent from needs_decomposition to open
                if parent_task_id:
                    parent = self.db.fetchone(
                        "SELECT status FROM tasks WHERE id = ?",
                        (parent_task_id,),
                    )
                    if parent and parent["status"] == "needs_decomposition":
                        now = datetime.now(UTC).isoformat()
                        conn.execute(
                            "UPDATE tasks SET status = 'open', updated_at = ? WHERE id = ?",
                            (now, parent_task_id),
                        )
                        logger.debug(
                            f"Auto-transitioned parent task {parent_task_id} from "
                            "needs_decomposition to open"
                        )

                self._notify_listeners()
                return self.get_task(task_id)

            except sqlite3.IntegrityError as e:
                # Check if it's a primary key violation (ID collision)
                if "UNIQUE constraint failed: tasks.id" in str(e) or "tasks.id" in str(e):
                    if attempt == max_retries:
                        raise TaskIDCollisionError(
                            f"Failed to generate unique task ID after {max_retries} retries"
                        ) from e
                    logger.warning(f"Task ID collision for {task_id}, retrying...")
                    continue
                raise e

        raise TaskIDCollisionError("Unreachable")

    def get_task(self, task_id: str) -> Task:
        """Get a task by ID."""
        row = self.db.fetchone("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not row:
            raise ValueError(f"Task {task_id} not found")
        return Task.from_row(row)

    def find_task_by_prefix(self, prefix: str) -> Task | None:
        """Find a task by ID prefix. Returns None if no match or multiple matches."""
        # First try exact match
        row = self.db.fetchone("SELECT * FROM tasks WHERE id = ?", (prefix,))
        if row:
            return Task.from_row(row)

        # Try prefix match
        rows = self.db.fetchall("SELECT * FROM tasks WHERE id LIKE ?", (f"{prefix}%",))
        if len(rows) == 1:
            return Task.from_row(rows[0])
        return None

    def find_tasks_by_prefix(self, prefix: str) -> list[Task]:
        """Find all tasks matching an ID prefix."""
        rows = self.db.fetchall("SELECT * FROM tasks WHERE id LIKE ?", (f"{prefix}%",))
        return [Task.from_row(row) for row in rows]

    def update_task(
        self,
        task_id: str,
        title: str | None | Any = UNSET,
        description: str | None | Any = UNSET,
        status: str | None | Any = UNSET,
        priority: int | None | Any = UNSET,
        task_type: str | None | Any = UNSET,
        assignee: str | None | Any = UNSET,
        labels: list[str] | None | Any = UNSET,
        parent_task_id: str | None | Any = UNSET,
        validation_status: str | None | Any = UNSET,
        validation_feedback: str | None | Any = UNSET,
        test_strategy: str | None | Any = UNSET,
        complexity_score: int | None | Any = UNSET,
        estimated_subtasks: int | None | Any = UNSET,
        expansion_context: str | None | Any = UNSET,
        validation_criteria: str | None | Any = UNSET,
        use_external_validator: bool | None | Any = UNSET,
        validation_fail_count: int | None | Any = UNSET,
        workflow_name: str | None | Any = UNSET,
        verification: str | None | Any = UNSET,
        sequence_order: int | None | Any = UNSET,
        escalated_at: str | None | Any = UNSET,
        escalation_reason: str | None | Any = UNSET,
    ) -> Task:
        """Update task fields."""
        # Validate status transitions from needs_decomposition
        if status is not UNSET and status in ("in_progress", "closed"):
            current_task = self.get_task(task_id)
            if current_task.status == "needs_decomposition":
                # Check if task has subtasks (required to transition out of needs_decomposition)
                children = self.db.fetchone(
                    "SELECT COUNT(*) as count FROM tasks WHERE parent_task_id = ?",
                    (task_id,),
                )
                has_children = children and children["count"] > 0
                if not has_children:
                    raise ValueError(
                        f"Cannot transition task {task_id} from 'needs_decomposition' to '{status}'. "
                        "Task must be decomposed into subtasks first."
                    )

        updates = []
        params: list[Any] = []

        if title is not UNSET:
            updates.append("title = ?")
            params.append(title)
        if description is not UNSET:
            updates.append("description = ?")
            params.append(description)
        if status is not UNSET:
            updates.append("status = ?")
            params.append(status)
        if priority is not UNSET:
            updates.append("priority = ?")
            params.append(priority)
        if task_type is not UNSET:
            updates.append("type = ?")  # DB column is 'type'
            params.append(task_type)
        if assignee is not UNSET:
            updates.append("assignee = ?")
            params.append(assignee)
        if labels is not UNSET:
            updates.append("labels = ?")
            # Handle None labels by setting to empty list or NULL?
            # Existing code: json.dumps(labels) if labels else None.
            # If labels is explicitly None, maybe we want NULL?
            # Or empty list []?
            # Schema usually uses '[]' for empty.
            if labels is None:
                params.append("[]")
            else:
                params.append(json.dumps(labels))
        if parent_task_id is not UNSET:
            updates.append("parent_task_id = ?")
            # Explicit None means clear parent
            params.append(parent_task_id)
        if validation_status is not UNSET:
            updates.append("validation_status = ?")
            params.append(validation_status)
        if validation_feedback is not UNSET:
            updates.append("validation_feedback = ?")
            params.append(validation_feedback)
        if test_strategy is not UNSET:
            updates.append("test_strategy = ?")
            params.append(test_strategy)
        if complexity_score is not UNSET:
            updates.append("complexity_score = ?")
            params.append(complexity_score)
        if estimated_subtasks is not UNSET:
            updates.append("estimated_subtasks = ?")
            params.append(estimated_subtasks)
        if expansion_context is not UNSET:
            updates.append("expansion_context = ?")
            params.append(expansion_context)
        if validation_criteria is not UNSET:
            updates.append("validation_criteria = ?")
            params.append(validation_criteria)
        if use_external_validator is not UNSET:
            updates.append("use_external_validator = ?")
            params.append(use_external_validator)
        if validation_fail_count is not UNSET:
            updates.append("validation_fail_count = ?")
            params.append(validation_fail_count)
        if workflow_name is not UNSET:
            updates.append("workflow_name = ?")
            params.append(workflow_name)
        if verification is not UNSET:
            updates.append("verification = ?")
            params.append(verification)
        if sequence_order is not UNSET:
            updates.append("sequence_order = ?")
            params.append(sequence_order)
        if escalated_at is not UNSET:
            updates.append("escalated_at = ?")
            params.append(escalated_at)
        if escalation_reason is not UNSET:
            updates.append("escalation_reason = ?")
            params.append(escalation_reason)

        if not updates:
            return self.get_task(task_id)

        updates.append("updated_at = ?")
        params.append(datetime.now(UTC).isoformat())

        params.append(task_id)  # for WHERE clause

        sql = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"

        with self.db.transaction() as conn:
            cursor = conn.execute(sql, tuple(params))
            if cursor.rowcount == 0:
                raise ValueError(f"Task {task_id} not found")

        self._notify_listeners()
        return self.get_task(task_id)

    def close_task(
        self,
        task_id: str,
        reason: str | None = None,
        force: bool = False,
        closed_in_session_id: str | None = None,
        closed_commit_sha: str | None = None,
        validation_override_reason: str | None = None,
    ) -> Task:
        """Close a task.

        Args:
            task_id: The task ID to close
            reason: Optional reason for closing
            force: If True, close even if there are open children (default: False)
            closed_in_session_id: Session ID where task was closed
            closed_commit_sha: Git commit SHA at time of closing
            validation_override_reason: Why agent bypassed validation (if applicable)

        Raises:
            ValueError: If task not found or has open children (and force=False)
        """
        # Check for open children unless force=True
        if not force:
            open_children = self.db.fetchall(
                "SELECT id, title FROM tasks WHERE parent_task_id = ? AND status != 'closed'",
                (task_id,),
            )
            if open_children:
                child_list = ", ".join(f"{c['id']} ({c['title']})" for c in open_children[:3])
                if len(open_children) > 3:
                    child_list += f" and {len(open_children) - 3} more"
                raise ValueError(
                    f"Cannot close task {task_id}: has {len(open_children)} open child task(s): {child_list}"
                )

        now = datetime.now(UTC).isoformat()
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """UPDATE tasks SET
                    status = 'closed',
                    closed_reason = ?,
                    closed_at = ?,
                    closed_in_session_id = ?,
                    closed_commit_sha = ?,
                    validation_override_reason = ?,
                    updated_at = ?
                WHERE id = ?""",
                (
                    reason,
                    now,
                    closed_in_session_id,
                    closed_commit_sha,
                    validation_override_reason,
                    now,
                    task_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Task {task_id} not found")

        # Update any associated worktrees to merged status (outside transaction)
        # This is best-effort and should not roll back the task close
        try:
            self.db.execute(
                """UPDATE worktrees SET status = 'merged', updated_at = ?
                WHERE task_id = ? AND status = 'active'""",
                (now, task_id),
            )
        except Exception as wt_err:
            # Worktree update is best-effort, don't fail task close
            logger.debug(f"Failed to update worktree status for task {task_id}: {wt_err}")

        self._notify_listeners()
        return self.get_task(task_id)

    def reopen_task(
        self,
        task_id: str,
        reason: str | None = None,
    ) -> Task:
        """Reopen a closed task.

        Args:
            task_id: The task ID to reopen
            reason: Optional reason for reopening

        Raises:
            ValueError: If task not found or not closed
        """
        task = self.get_task(task_id)
        if task.status != "closed":
            raise ValueError(f"Task {task_id} is not closed (status: {task.status})")

        now = datetime.now(UTC).isoformat()

        # Build description update if reason provided
        new_description = task.description or ""
        if reason:
            reopen_note = f"\n\n[Reopened: {reason}]"
            new_description = new_description + reopen_note

        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE tasks SET
                    status = 'open',
                    closed_reason = NULL,
                    closed_at = NULL,
                    closed_in_session_id = NULL,
                    closed_commit_sha = NULL,
                    description = ?,
                    updated_at = ?
                WHERE id = ?""",
                (new_description if reason else task.description, now, task_id),
            )

        # Reactivate any merged or abandoned worktrees for this task (outside transaction)
        # This is best-effort and should not roll back the task reopen
        try:
            self.db.execute(
                """UPDATE worktrees SET status = 'active', updated_at = ?
                WHERE task_id = ? AND status IN ('merged', 'abandoned')""",
                (now, task_id),
            )
        except Exception as wt_err:
            # Worktree update is best-effort, don't fail task reopen
            logger.debug(f"Failed to reactivate worktree for task {task_id}: {wt_err}")

        self._notify_listeners()
        return self.get_task(task_id)

    def add_label(self, task_id: str, label: str) -> Task:
        """Add a label to a task if not present."""
        task = self.get_task(task_id)
        labels = task.labels or []
        if label not in labels:
            labels.append(label)
            return self.update_task(task_id, labels=labels)
        return task

    def remove_label(self, task_id: str, label: str) -> Task:
        """Remove a label from a task if present."""
        task = self.get_task(task_id)
        labels = task.labels or []
        if label in labels:
            labels.remove(label)
            return self.update_task(task_id, labels=labels)
        return task

    def link_commit(self, task_id: str, commit_sha: str) -> Task:
        """Link a commit SHA to a task.

        Adds the commit SHA to the task's commits array if not already present.

        Args:
            task_id: The task ID to link the commit to.
            commit_sha: The git commit SHA to link.

        Returns:
            Updated Task object.

        Raises:
            ValueError: If task not found.
        """
        task = self.get_task(task_id)  # Raises if not found
        commits = task.commits or []
        if commit_sha not in commits:
            commits.append(commit_sha)
            # Update the commits column in the database
            now = datetime.now(UTC).isoformat()
            with self.db.transaction() as conn:
                conn.execute(
                    "UPDATE tasks SET commits = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(commits), now, task_id),
                )
            self._notify_listeners()
            return self.get_task(task_id)
        return task

    def unlink_commit(self, task_id: str, commit_sha: str) -> Task:
        """Unlink a commit SHA from a task.

        Removes the commit SHA from the task's commits array if present.

        Args:
            task_id: The task ID to unlink the commit from.
            commit_sha: The git commit SHA to unlink.

        Returns:
            Updated Task object.

        Raises:
            ValueError: If task not found.
        """
        task = self.get_task(task_id)  # Raises if not found
        commits = task.commits or []
        if commit_sha in commits:
            commits.remove(commit_sha)
            # Update the commits column in the database
            now = datetime.now(UTC).isoformat()
            commits_json = json.dumps(commits) if commits else None
            with self.db.transaction() as conn:
                conn.execute(
                    "UPDATE tasks SET commits = ?, updated_at = ? WHERE id = ?",
                    (commits_json, now, task_id),
                )
            self._notify_listeners()
            return self.get_task(task_id)
        return task

    def delete_task(self, task_id: str, cascade: bool = False) -> bool:
        """Delete a task. If cascade is True, delete children recursively.

        Returns:
            True if task was deleted, False if task not found.
        """
        # Check if task exists first
        existing = self.db.fetchone("SELECT 1 FROM tasks WHERE id = ?", (task_id,))
        if not existing:
            return False

        if not cascade:
            # Check for children
            row = self.db.fetchone("SELECT 1 FROM tasks WHERE parent_task_id = ?", (task_id,))
            if row:
                raise ValueError(f"Task {task_id} has children. Use cascade=True to delete.")

        if cascade:
            # Recursive delete
            # Find all children
            children = self.db.fetchall("SELECT id FROM tasks WHERE parent_task_id = ?", (task_id,))
            for child in children:
                self.delete_task(child["id"], cascade=True)

        with self.db.transaction() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._notify_listeners()
        return True

    def list_tasks(
        self,
        project_id: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        assignee: str | None = None,
        task_type: str | None = None,
        label: str | None = None,
        parent_task_id: str | None = None,
        title_like: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks with filtering.

        Results are ordered hierarchically: parents appear before their children,
        with siblings sorted by priority ASC, then created_at ASC.
        """
        query = "SELECT * FROM tasks WHERE 1=1"
        params: list[Any] = []

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        if assignee:
            query += " AND assignee = ?"
            params.append(assignee)
        if task_type:
            query += " AND type = ?"  # DB column is 'type'
            params.append(task_type)
        if label:
            # tasks.labels is a JSON list. We use json_each to find if the label is in the list.
            # Example: WHERE EXISTS (SELECT 1 FROM json_each(tasks.labels) WHERE value = ?)
            query += " AND EXISTS (SELECT 1 FROM json_each(tasks.labels) WHERE value = ?)"
            params.append(label)
        if parent_task_id:
            query += " AND parent_task_id = ?"
            params.append(parent_task_id)
        if title_like:
            query += " AND title LIKE ?"
            params.append(f"%{title_like}%")

        # Fetch with base ordering, then apply hierarchical sort in Python
        query += " ORDER BY priority ASC, created_at ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.db.fetchall(query, tuple(params))
        tasks = [Task.from_row(row) for row in rows]
        return order_tasks_hierarchically(tasks)

    def list_ready_tasks(
        self,
        project_id: str | None = None,
        priority: int | None = None,
        task_type: str | None = None,
        assignee: str | None = None,
        parent_task_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks that are open and not blocked by any open blocking dependency.

        A task is ready if:
        1. It is open
        2. It has no open blocking dependencies
        3. Its parent (if any) is also ready (recursive check up the chain)

        Results are ordered hierarchically: parents appear before their children,
        with siblings sorted by priority ASC, then created_at ASC.

        Note: The limit is applied AFTER hierarchical ordering to ensure coherent
        tree structures. We fetch all ready tasks, order them hierarchically,
        then return the first N tasks in tree traversal order.
        """
        # Use recursive CTE to find tasks with ready parent chains
        # Note: "blocked by own children" is a completion block, not a work block.
        # Parent tasks should still be considered "ready" even if blocked by children.
        query = """
        WITH RECURSIVE ready_tasks AS (
            -- Base case: open tasks with no parent and no external blocking deps
            SELECT t.id FROM tasks t
            WHERE t.status = 'open'
            AND t.parent_task_id IS NULL
            AND NOT EXISTS (
                SELECT 1 FROM task_dependencies d
                JOIN tasks blocker ON d.depends_on = blocker.id
                WHERE d.task_id = t.id
                  AND d.dep_type = 'blocks'
                  AND blocker.status != 'closed'
                  -- Exclude parent blocked by own children (completion block, not work block)
                  -- Use COALESCE to handle NULL parent_task_id (NULL != x returns NULL, not TRUE)
                  AND COALESCE(blocker.parent_task_id, '') != t.id
            )

            UNION ALL

            -- Recursive case: open tasks whose parent is ready and no external blocking deps
            SELECT t.id FROM tasks t
            JOIN ready_tasks rt ON t.parent_task_id = rt.id
            WHERE t.status = 'open'
            AND NOT EXISTS (
                SELECT 1 FROM task_dependencies d
                JOIN tasks blocker ON d.depends_on = blocker.id
                WHERE d.task_id = t.id
                  AND d.dep_type = 'blocks'
                  AND blocker.status != 'closed'
                  -- Exclude parent blocked by own children (completion block, not work block)
                  AND COALESCE(blocker.parent_task_id, '') != t.id
            )
        )
        SELECT t.* FROM tasks t
        JOIN ready_tasks rt ON t.id = rt.id
        WHERE 1=1
        """
        params: list[Any] = []

        if project_id:
            query += " AND t.project_id = ?"
            params.append(project_id)
        if priority:
            query += " AND t.priority = ?"
            params.append(priority)
        if task_type:
            query += " AND t.type = ?"  # DB column is 'type'
            params.append(task_type)
        if assignee:
            query += " AND t.assignee = ?"
            params.append(assignee)
        if parent_task_id:
            query += " AND t.parent_task_id = ?"
            params.append(parent_task_id)

        # Fetch all matching tasks (no SQL limit) so we can order hierarchically first
        # Use a safety cap to prevent runaway queries
        internal_limit = 1000
        query += " ORDER BY t.priority ASC, t.created_at ASC LIMIT ?"
        params.append(internal_limit)

        rows = self.db.fetchall(query, tuple(params))
        tasks = [Task.from_row(row) for row in rows]

        # Order hierarchically, then apply user's limit/offset
        ordered = order_tasks_hierarchically(tasks)
        return ordered[offset : offset + limit] if limit else ordered

    def list_blocked_tasks(
        self,
        project_id: str | None = None,
        parent_task_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks that are blocked by at least one open blocking dependency.

        Only considers "external" blockers - excludes parent tasks being blocked
        by their own children (which is a "completion" block, not a "work" block).

        Results are ordered hierarchically: parents appear before their children,
        with siblings sorted by priority ASC, then created_at ASC.

        Note: The limit is applied AFTER hierarchical ordering to ensure coherent
        tree structures.
        """
        query = """
        SELECT t.* FROM tasks t
        WHERE t.status = 'open'
        AND EXISTS (
            SELECT 1 FROM task_dependencies d
            JOIN tasks blocker ON d.depends_on = blocker.id
            WHERE d.task_id = t.id
              AND d.dep_type = 'blocks'
              AND blocker.status != 'closed'
              -- Exclude parent blocked by own children (completion block, not work block)
              -- Use COALESCE to handle NULL parent_task_id (NULL != x returns NULL, not TRUE)
              AND COALESCE(blocker.parent_task_id, '') != t.id
        )
        """
        params: list[Any] = []

        if project_id:
            query += " AND t.project_id = ?"
            params.append(project_id)
        if parent_task_id:
            query += " AND t.parent_task_id = ?"
            params.append(parent_task_id)

        # Fetch all matching tasks (no SQL limit) so we can order hierarchically first
        internal_limit = 1000
        query += " ORDER BY t.priority ASC, t.created_at ASC LIMIT ?"
        params.append(internal_limit)

        rows = self.db.fetchall(query, tuple(params))
        tasks = [Task.from_row(row) for row in rows]

        # Order hierarchically, then apply user's limit/offset
        ordered = order_tasks_hierarchically(tasks)
        return ordered[offset : offset + limit] if limit else ordered

    def list_workflow_tasks(
        self,
        workflow_name: str,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks associated with a workflow, ordered by sequence_order.

        Args:
            workflow_name: The workflow name to filter by
            project_id: Optional project ID filter
            status: Optional status filter ('open', 'in_progress', 'closed')
            limit: Maximum tasks to return
            offset: Pagination offset

        Returns:
            List of tasks ordered by sequence_order (nulls last), then created_at
        """
        query = "SELECT * FROM tasks WHERE workflow_name = ?"
        params: list[Any] = [workflow_name]

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if status:
            query += " AND status = ?"
            params.append(status)

        # Order by sequence_order (nulls last), then created_at
        query += " ORDER BY COALESCE(sequence_order, 999999) ASC, created_at ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.db.fetchall(query, tuple(params))
        return [Task.from_row(row) for row in rows]

    def count_tasks(
        self,
        project_id: str | None = None,
        status: str | None = None,
    ) -> int:
        """
        Count tasks with optional filters.

        Args:
            project_id: Filter by project
            status: Filter by status

        Returns:
            Count of matching tasks
        """
        query = "SELECT COUNT(*) as count FROM tasks WHERE 1=1"
        params: list[Any] = []

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if status:
            query += " AND status = ?"
            params.append(status)

        result = self.db.fetchone(query, tuple(params))
        return result["count"] if result else 0

    def count_by_status(self, project_id: str | None = None) -> dict[str, int]:
        """
        Count tasks grouped by status.

        Args:
            project_id: Optional project filter

        Returns:
            Dictionary mapping status to count
        """
        query = "SELECT status, COUNT(*) as count FROM tasks"
        params: list[Any] = []

        if project_id:
            query += " WHERE project_id = ?"
            params.append(project_id)

        query += " GROUP BY status"

        rows = self.db.fetchall(query, tuple(params))
        return {row["status"]: row["count"] for row in rows}

    def count_ready_tasks(self, project_id: str | None = None) -> int:
        """
        Count tasks that are open and not blocked by any external blocking dependency.

        Excludes parent tasks blocked by their own children (completion block, not work block).

        Args:
            project_id: Optional project filter

        Returns:
            Count of ready tasks
        """
        query = """
        SELECT COUNT(*) as count FROM tasks t
        WHERE t.status = 'open'
        AND NOT EXISTS (
            SELECT 1 FROM task_dependencies d
            JOIN tasks blocker ON d.depends_on = blocker.id
            WHERE d.task_id = t.id
              AND d.dep_type = 'blocks'
              AND blocker.status != 'closed'
              -- Exclude parent blocked by own children (completion block, not work block)
              -- Use COALESCE to handle NULL parent_task_id (NULL != x returns NULL, not TRUE)
              AND COALESCE(blocker.parent_task_id, '') != t.id
        )
        """
        params: list[Any] = []

        if project_id:
            query += " AND t.project_id = ?"
            params.append(project_id)

        result = self.db.fetchone(query, tuple(params))
        return result["count"] if result else 0

    def count_blocked_tasks(self, project_id: str | None = None) -> int:
        """
        Count tasks that are blocked by at least one external blocking dependency.

        Excludes parent tasks blocked by their own children (completion block, not work block).

        Args:
            project_id: Optional project filter

        Returns:
            Count of blocked tasks
        """
        query = """
        SELECT COUNT(*) as count FROM tasks t
        WHERE t.status = 'open'
        AND EXISTS (
            SELECT 1 FROM task_dependencies d
            JOIN tasks blocker ON d.depends_on = blocker.id
            WHERE d.task_id = t.id
              AND d.dep_type = 'blocks'
              AND blocker.status != 'closed'
              -- Exclude parent blocked by own children (completion block, not work block)
              -- Use COALESCE to handle NULL parent_task_id (NULL != x returns NULL, not TRUE)
              AND COALESCE(blocker.parent_task_id, '') != t.id
        )
        """
        params: list[Any] = []

        if project_id:
            query += " AND t.project_id = ?"
            params.append(project_id)

        result = self.db.fetchone(query, tuple(params))
        return result["count"] if result else 0

    def create_task_with_decomposition(
        self,
        project_id: str,
        title: str,
        description: str | None = None,
        auto_decompose: bool = True,
        parent_task_id: str | None = None,
        created_in_session_id: str | None = None,
        priority: int = 2,
        task_type: str = "task",
        assignee: str | None = None,
        labels: list[str] | None = None,
        test_strategy: str | None = None,
        complexity_score: int | None = None,
        estimated_subtasks: int | None = None,
        expansion_context: str | None = None,
        validation_criteria: str | None = None,
        use_external_validator: bool = False,
        workflow_name: str | None = None,
        verification: str | None = None,
        sequence_order: int | None = None,
    ) -> dict[str, Any]:
        """Create a task with optional auto-decomposition of multi-step descriptions.

        When auto_decompose=True (default), descriptions with multiple steps
        (numbered lists, bullet points, etc.) are automatically broken down
        into a parent task plus subtasks.

        Args:
            project_id: Project ID
            title: Task title
            description: Task description (analyzed for multi-step patterns)
            auto_decompose: Whether to auto-decompose multi-step descriptions
            parent_task_id: Optional parent task ID (for nested tasks)
            created_in_session_id: Session ID where task was created
            priority: Task priority (1=high, 2=medium, 3=low)
            task_type: Task type (task, bug, feature, epic)
            assignee: Optional assignee
            labels: Optional labels list
            test_strategy: Testing strategy
            complexity_score: Complexity score
            estimated_subtasks: Estimated number of subtasks
            expansion_context: Additional context for expansion
            validation_criteria: Validation criteria for completion
            use_external_validator: Whether to use external validator
            workflow_name: Workflow name
            verification: Verification steps
            sequence_order: Sequence order in parent

        Returns:
            Dict with auto_decomposed flag and either:
            - {auto_decomposed: True, parent_task: {...}, subtasks: [...]}
            - {auto_decomposed: False, task: {...}}
        """
        from gobby.storage.task_dependencies import TaskDependencyManager
        from gobby.tasks.auto_decompose import detect_multi_step, extract_steps

        # Check if description has multi-step content
        is_multi_step = detect_multi_step(description) if description else False

        if not is_multi_step:
            # Single-step task: create normally
            task = self.create_task(
                project_id=project_id,
                title=title,
                description=description,
                parent_task_id=parent_task_id,
                created_in_session_id=created_in_session_id,
                priority=priority,
                task_type=task_type,
                assignee=assignee,
                labels=labels,
                test_strategy=test_strategy,
                complexity_score=complexity_score,
                estimated_subtasks=estimated_subtasks,
                expansion_context=expansion_context,
                validation_criteria=validation_criteria,
                use_external_validator=use_external_validator,
                workflow_name=workflow_name,
                verification=verification,
                sequence_order=sequence_order,
            )
            return {"auto_decomposed": False, "task": task.to_dict()}

        if not auto_decompose:
            # Multi-step but opt-out: create with needs_decomposition status
            task = self.create_task(
                project_id=project_id,
                title=title,
                description=description,
                parent_task_id=parent_task_id,
                created_in_session_id=created_in_session_id,
                priority=priority,
                task_type=task_type,
                assignee=assignee,
                labels=labels,
                test_strategy=test_strategy,
                complexity_score=complexity_score,
                estimated_subtasks=estimated_subtasks,
                expansion_context=expansion_context,
                validation_criteria=validation_criteria,
                use_external_validator=use_external_validator,
                workflow_name=workflow_name,
                verification=verification,
                sequence_order=sequence_order,
            )
            # Update status to needs_decomposition
            task = self.update_task(task.id, status="needs_decomposition")
            return {"auto_decomposed": False, "task": task.to_dict()}

        # Multi-step with auto_decompose=True: create parent + subtasks
        # Extract steps from description
        steps = extract_steps(description)

        # Create parent task (keep original description for context)
        parent_task = self.create_task(
            project_id=project_id,
            title=title,
            description=description,
            parent_task_id=parent_task_id,
            created_in_session_id=created_in_session_id,
            priority=priority,
            task_type=task_type,
            assignee=assignee,
            labels=labels,
            test_strategy=test_strategy,
            complexity_score=complexity_score,
            estimated_subtasks=len(steps),
            expansion_context=expansion_context,
            validation_criteria=validation_criteria,
            use_external_validator=use_external_validator,
            workflow_name=workflow_name,
            verification=verification,
            sequence_order=sequence_order,
        )

        # Create subtasks
        dep_manager = TaskDependencyManager(self.db)
        subtasks: list[dict[str, Any]] = []

        for idx, step in enumerate(steps):
            subtask = self.create_task(
                project_id=project_id,
                title=step["title"],
                description=step.get("description"),
                parent_task_id=parent_task.id,
                created_in_session_id=created_in_session_id,
                priority=priority,
                task_type="task",  # Subtasks are always type "task"
                assignee=assignee,
                labels=labels,
                sequence_order=idx,
            )
            subtasks.append(subtask.to_dict())

            # Add sequential dependency (step N+1 is blocked by step N)
            depends_on_indices = step.get("depends_on")
            if depends_on_indices:
                for dep_idx in depends_on_indices:
                    if 0 <= dep_idx < len(subtasks) - 1:  # -1 because current task is already appended
                        dep_manager.add_dependency(
                            subtask.id, subtasks[dep_idx]["id"], "blocks"
                        )

        return {
            "auto_decomposed": True,
            "parent_task": parent_task.to_dict(),
            "subtasks": subtasks,
        }
