"""Local pipeline execution storage manager."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from gobby.storage.database import DatabaseProtocol
from gobby.utils.id import generate_prefixed_id
from gobby.workflows.pipeline_state import (
    ExecutionStatus,
    PipelineExecution,
    StepExecution,
    StepStatus,
)

logger = logging.getLogger(__name__)


class LocalPipelineExecutionManager:
    """Manager for local pipeline execution storage."""

    def __init__(self, db: DatabaseProtocol, project_id: str):
        """Initialize with database connection and project context.

        Args:
            db: Database connection
            project_id: Project ID for scoping executions
        """
        self.db = db
        self.project_id = project_id

    def create_execution(
        self,
        pipeline_name: str,
        inputs_json: str | None = None,
        session_id: str | None = None,
        parent_execution_id: str | None = None,
    ) -> PipelineExecution:
        """Create a new pipeline execution.

        Args:
            pipeline_name: Name of the pipeline being executed
            inputs_json: JSON string of input parameters
            session_id: Session that triggered the execution
            parent_execution_id: Parent execution for nested pipelines

        Returns:
            Created PipelineExecution instance
        """
        execution_id = generate_prefixed_id("pe")
        now = datetime.now(UTC).isoformat()

        self.db.execute(
            """
            INSERT INTO pipeline_executions (
                id, pipeline_name, project_id, status, inputs_json,
                session_id, parent_execution_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id,
                pipeline_name,
                self.project_id,
                ExecutionStatus.PENDING.value,
                inputs_json,
                session_id,
                parent_execution_id,
                now,
                now,
            ),
        )

        execution = self.get_execution(execution_id)
        if execution is None:
            raise RuntimeError(f"Execution {execution_id} not found after creation")
        return execution

    def get_execution(self, execution_id: str) -> PipelineExecution | None:
        """Get execution by ID.

        Args:
            execution_id: Execution UUID

        Returns:
            PipelineExecution or None if not found
        """
        row = self.db.fetchone(
            "SELECT * FROM pipeline_executions WHERE id = ?",
            (execution_id,),
        )
        return PipelineExecution.from_row(row) if row else None

    def update_execution_status(
        self,
        execution_id: str,
        status: ExecutionStatus,
        resume_token: str | None = None,
        outputs_json: str | None = None,
    ) -> PipelineExecution | None:
        """Update execution status.

        Args:
            execution_id: Execution UUID
            status: New status
            resume_token: Resume token for approval gates
            outputs_json: JSON string of outputs (for completed status)

        Returns:
            Updated PipelineExecution or None if not found
        """
        now = datetime.now(UTC).isoformat()
        completed_at = now if status == ExecutionStatus.COMPLETED else None

        self.db.execute(
            """
            UPDATE pipeline_executions
            SET status = ?, resume_token = ?, outputs_json = ?,
                completed_at = COALESCE(?, completed_at), updated_at = ?
            WHERE id = ?
            """,
            (
                status.value,
                resume_token,
                outputs_json,
                completed_at,
                now,
                execution_id,
            ),
        )

        return self.get_execution(execution_id)

    def list_executions(
        self,
        status: ExecutionStatus | None = None,
        pipeline_name: str | None = None,
        limit: int = 50,
    ) -> list[PipelineExecution]:
        """List executions for the project.

        Args:
            status: Filter by status
            pipeline_name: Filter by pipeline name
            limit: Maximum number of results

        Returns:
            List of PipelineExecution instances
        """
        query = "SELECT * FROM pipeline_executions WHERE project_id = ?"
        params: list[Any] = [self.project_id]

        if status is not None:
            query += " AND status = ?"
            params.append(status.value)

        if pipeline_name is not None:
            query += " AND pipeline_name = ?"
            params.append(pipeline_name)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self.db.fetchall(query, tuple(params))
        return [PipelineExecution.from_row(row) for row in rows]

    def get_execution_by_resume_token(self, token: str) -> PipelineExecution | None:
        """Get execution by resume token.

        Args:
            token: Resume token

        Returns:
            PipelineExecution or None if not found
        """
        row = self.db.fetchone(
            "SELECT * FROM pipeline_executions WHERE resume_token = ?",
            (token,),
        )
        return PipelineExecution.from_row(row) if row else None

    def resolve_execution_reference(self, ref: str) -> str:
        """Resolve an execution reference to a UUID.

        Supports:
        - Full UUID: pe-abc123... or UUID format
        - UUID prefix: pe-abc1 (matches by prefix)

        Args:
            ref: Execution reference

        Returns:
            Execution UUID

        Raises:
            ValueError: If reference cannot be resolved
        """
        # Try exact match first
        execution = self.get_execution(ref)
        if execution:
            return execution.id

        # Try prefix match
        row = self.db.fetchone(
            "SELECT id FROM pipeline_executions WHERE id LIKE ? AND project_id = ?",
            (f"{ref}%", self.project_id),
        )
        if row:
            result: str = row["id"]
            return result

        raise ValueError(f"Cannot resolve execution reference: {ref}")

    # Step execution methods

    def create_step_execution(
        self,
        execution_id: str,
        step_id: str,
        input_json: str | None = None,
    ) -> StepExecution:
        """Create a new step execution.

        Args:
            execution_id: Parent pipeline execution ID
            step_id: Step ID from pipeline definition
            input_json: JSON string of step input

        Returns:
            Created StepExecution instance
        """
        self.db.execute(
            """
            INSERT INTO step_executions (
                execution_id, step_id, status, input_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                execution_id,
                step_id,
                StepStatus.PENDING.value,
                input_json,
            ),
        )

        # Get the created step by execution_id and step_id (unique combination)
        row = self.db.fetchone(
            "SELECT * FROM step_executions WHERE execution_id = ? AND step_id = ?",
            (execution_id, step_id),
        )
        if row is None:
            raise RuntimeError(f"Step {step_id} not found after creation")
        return StepExecution.from_row(row)

    def update_step_execution(
        self,
        step_execution_id: int,
        status: StepStatus | None = None,
        output_json: str | None = None,
        error: str | None = None,
        approval_token: str | None = None,
        approved_by: str | None = None,
    ) -> StepExecution | None:
        """Update a step execution.

        Args:
            step_execution_id: Step execution ID (integer)
            status: New status
            output_json: JSON string of step output
            error: Error message (for failed status)
            approval_token: Token for approval gate
            approved_by: Who approved the step

        Returns:
            Updated StepExecution or None if not found
        """
        now = datetime.now(UTC).isoformat()

        # Build update parts dynamically
        updates = ["updated_at = ?"]
        params: list[Any] = [now]

        if status is not None:
            updates.append("status = ?")
            params.append(status.value)

            # Set timestamps based on status
            if status == StepStatus.RUNNING:
                updates.append("started_at = COALESCE(started_at, ?)")
                params.append(now)
            elif status in (StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED):
                updates.append("completed_at = COALESCE(completed_at, ?)")
                params.append(now)

        if output_json is not None:
            updates.append("output_json = ?")
            params.append(output_json)

        if error is not None:
            updates.append("error = ?")
            params.append(error)

        if approval_token is not None:
            updates.append("approval_token = ?")
            params.append(approval_token)

        if approved_by is not None:
            updates.append("approved_by = ?")
            params.append(approved_by)
            updates.append("approved_at = ?")
            params.append(now)

        params.append(step_execution_id)

        # Note: step_executions doesn't have updated_at column, remove it
        updates = [u for u in updates if not u.startswith("updated_at")]
        params = params[1:]  # Remove the now that was for updated_at

        # Re-add timestamps
        if status is not None:
            if status == StepStatus.RUNNING:
                if "started_at = COALESCE(started_at, ?)" not in updates:
                    updates.append("started_at = COALESCE(started_at, ?)")
                    params.insert(-1, now)
            elif status in (StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED):
                if "completed_at = COALESCE(completed_at, ?)" not in updates:
                    updates.append("completed_at = COALESCE(completed_at, ?)")
                    params.insert(-1, now)

        self.db.execute(
            f"UPDATE step_executions SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )

        row = self.db.fetchone(
            "SELECT * FROM step_executions WHERE id = ?",
            (step_execution_id,),
        )
        return StepExecution.from_row(row) if row else None

    def get_step_by_approval_token(self, token: str) -> StepExecution | None:
        """Get step execution by approval token.

        Args:
            token: Approval token

        Returns:
            StepExecution or None if not found
        """
        row = self.db.fetchone(
            "SELECT * FROM step_executions WHERE approval_token = ?",
            (token,),
        )
        return StepExecution.from_row(row) if row else None

    def get_steps_for_execution(self, execution_id: str) -> list[StepExecution]:
        """Get all steps for an execution.

        Args:
            execution_id: Pipeline execution ID

        Returns:
            List of StepExecution instances
        """
        rows = self.db.fetchall(
            "SELECT * FROM step_executions WHERE execution_id = ? ORDER BY id",
            (execution_id,),
        )
        return [StepExecution.from_row(row) for row in rows]
