"""Validation history management for Task System V2.

Provides storage and retrieval of validation iteration history.
"""

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gobby.tasks.validation_models import Issue

if TYPE_CHECKING:
    from gobby.storage.database import LocalDatabase

logger = logging.getLogger(__name__)


@dataclass
class ValidationIteration:
    """Represents a single validation iteration for a task.

    Attributes:
        id: Database ID of the iteration record
        task_id: ID of the task being validated
        iteration: Iteration number (1-based)
        status: Validation status ("valid", "invalid", "error")
        feedback: Human-readable feedback from validator
        issues: List of Issue objects found during validation
        context_type: Type of context provided (e.g., "git_diff", "code_review")
        context_summary: Summary of the context provided
        validator_type: Type of validator used (e.g., "llm", "external_webhook")
        created_at: Timestamp when iteration was recorded
    """

    id: int
    task_id: str
    iteration: int
    status: str
    feedback: str | None = None
    issues: list[Issue] | None = None
    context_type: str | None = None
    context_summary: str | None = None
    validator_type: str | None = None
    created_at: str | None = None


class ValidationHistoryManager:
    """Manages validation iteration history for tasks.

    Stores and retrieves validation history from the task_validation_history table.
    """

    def __init__(self, db: "LocalDatabase"):
        """Initialize ValidationHistoryManager.

        Args:
            db: LocalDatabase instance for database operations.
        """
        self.db = db

    def record_iteration(
        self,
        task_id: str,
        iteration: int,
        status: str,
        feedback: str | None = None,
        issues: list[Issue] | None = None,
        context_type: str | None = None,
        context_summary: str | None = None,
        validator_type: str | None = None,
    ) -> None:
        """Record a validation iteration for a task.

        Args:
            task_id: ID of the task being validated.
            iteration: Iteration number (1-based).
            status: Validation status ("valid", "invalid", "error").
            feedback: Human-readable feedback from validator.
            issues: List of Issue objects found during validation.
            context_type: Type of context provided.
            context_summary: Summary of the context provided.
            validator_type: Type of validator used.
        """
        # Serialize issues to JSON
        issues_json = None
        if issues:
            issues_json = json.dumps([issue.to_dict() for issue in issues])

        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO task_validation_history
                   (task_id, iteration, status, feedback, issues, context_type,
                    context_summary, validator_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    iteration,
                    status,
                    feedback,
                    issues_json,
                    context_type,
                    context_summary,
                    validator_type,
                ),
            )

        logger.debug(
            f"Recorded validation iteration {iteration} for task {task_id}: {status}"
        )

    def get_iteration_history(self, task_id: str) -> list[ValidationIteration]:
        """Get all validation iterations for a task.

        Args:
            task_id: ID of the task to get history for.

        Returns:
            List of ValidationIteration objects ordered by iteration number.
        """
        rows = self.db.fetchall(
            """SELECT * FROM task_validation_history
               WHERE task_id = ?
               ORDER BY iteration ASC""",
            (task_id,),
        )

        return [self._row_to_iteration(row) for row in rows]

    def get_latest_iteration(self, task_id: str) -> ValidationIteration | None:
        """Get the most recent validation iteration for a task.

        Args:
            task_id: ID of the task to get latest iteration for.

        Returns:
            Latest ValidationIteration or None if no history exists.
        """
        row = self.db.fetchone(
            """SELECT * FROM task_validation_history
               WHERE task_id = ?
               ORDER BY iteration DESC
               LIMIT 1""",
            (task_id,),
        )

        if row:
            return self._row_to_iteration(row)
        return None

    def clear_history(self, task_id: str) -> None:
        """Remove all validation history for a task.

        Args:
            task_id: ID of the task to clear history for.
        """
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM task_validation_history WHERE task_id = ?",
                (task_id,),
            )

        logger.debug(f"Cleared validation history for task {task_id}")

    def _row_to_iteration(self, row) -> ValidationIteration:
        """Convert a database row to a ValidationIteration object.

        Args:
            row: Database row from task_validation_history.

        Returns:
            ValidationIteration object.
        """
        # Parse issues from JSON
        issues = None
        issues_json = row["issues"]
        if issues_json:
            issues_data = json.loads(issues_json)
            issues = [Issue.from_dict(d) for d in issues_data]

        return ValidationIteration(
            id=row["id"],
            task_id=row["task_id"],
            iteration=row["iteration"],
            status=row["status"],
            feedback=row["feedback"],
            issues=issues,
            context_type=row["context_type"],
            context_summary=row["context_summary"],
            validator_type=row["validator_type"],
            created_at=row["created_at"],
        )
