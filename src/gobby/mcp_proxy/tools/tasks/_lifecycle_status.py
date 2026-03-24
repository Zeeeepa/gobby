"""Status transition handlers for task lifecycle.

Handles reopen, escalate, mark_task_review_approved, and mark_task_needs_review
tool registrations.
"""

import logging
from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.tasks._context import RegistryContext
from gobby.mcp_proxy.tools.tasks._notifications import notify_parent_on_status_change
from gobby.mcp_proxy.tools.tasks._resolution import resolve_task_id_for_mcp
from gobby.storage.tasks import TaskNotFoundError
from gobby.storage.worktrees import LocalWorktreeManager

logger = logging.getLogger(__name__)


def register_reopen_task(registry: InternalToolRegistry, ctx: RegistryContext) -> None:
    """Register the reopen_task tool on the given registry."""

    def reopen_task(task_id: str, reason: str | None = None) -> dict[str, Any]:
        """Reopen a task to open status.

        Works on any non-open status. Clears assignee, closed fields,
        and resets validation_fail_count.

        Args:
            task_id: Task reference (#N, path, or UUID)
            reason: Optional reason for reopening
        """
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}

        # Capture assignee before reopen clears it (needed for session variable cleanup)
        task = ctx.task_manager.get_task(resolved_id)
        prior_assignee = task.assignee if task else None

        try:
            ctx.task_manager.reopen_task(resolved_id, reason=reason)

            # Remove from claimed_tasks session variable for the prior assignee
            if prior_assignee:
                try:
                    from gobby.workflows.task_claim_state import remove_claimed_task

                    session_vars = ctx.session_var_manager.get_variables(prior_assignee)
                    merge_dict = remove_claimed_task(session_vars, resolved_id)
                    ctx.session_var_manager.merge_variables(prior_assignee, merge_dict)
                    logger.debug(
                        f"Removed task {resolved_id} from claimed_tasks for session {prior_assignee} on reopen",
                    )
                except Exception as e:
                    logger.debug(f"Best-effort claimed_tasks cleanup on reopen failed: {e}")

            # Update session-task link to reflect reopen
            if prior_assignee:
                try:
                    ctx.session_task_manager.link_task(prior_assignee, resolved_id, "reopened")
                except Exception as e:
                    logger.debug(f"Best-effort session link update on reopen failed: {e}")

            # Reactivate any associated worktrees that were marked merged/abandoned
            try:
                from gobby.storage.worktrees import WorktreeStatus

                worktree_manager = LocalWorktreeManager(ctx.task_manager.db)
                wt = worktree_manager.get_by_task(resolved_id)
                if wt and wt.status in (
                    WorktreeStatus.MERGED.value,
                    WorktreeStatus.ABANDONED.value,
                ):
                    worktree_manager.update(wt.id, status=WorktreeStatus.ACTIVE.value)
            except Exception as e:
                logger.debug(f"Best-effort reopen worktree update failed: {e}")

            return {}
        except ValueError as e:
            return {"error": str(e)}

    registry.register(
        name="reopen_task",
        description="Reopen a task to open status. Works on any non-open status. Clears assignee, closed fields, and resets validation. Optionally appends a reopen reason to the description.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference to reopen: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason for reopening the task",
                    "default": None,
                },
            },
            "required": ["task_id"],
        },
        func=reopen_task,
    )


def register_escalate_task(registry: InternalToolRegistry, ctx: RegistryContext) -> None:
    """Register the escalate_task tool on the given registry."""

    def escalate_task(
        task_id: str,
        reason: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Escalate a task for human intervention.

        Sets status to 'escalated' with a reason and timestamp. Use when
        the task cannot be completed by the agent and needs human attention.

        Args:
            task_id: Task reference (#N, path, or UUID)
            reason: Why the task is being escalated
            session_id: Optional session ID for tracking

        Returns:
            Empty dict on success, or error dict with details.
        """
        from datetime import UTC, datetime

        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}

        task = ctx.task_manager.get_task(resolved_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        if task.status in ("escalated", "closed"):
            return {"error": f"Cannot escalate task with status '{task.status}'."}

        ctx.task_manager.update_task(
            resolved_id,
            status="escalated",
            escalated_at=datetime.now(UTC).isoformat(),
            escalation_reason=reason,
        )

        notify_parent_on_status_change(
            ctx.task_manager.db,
            resolved_id,
            "escalated",
            task_ref=f"#{task.seq_num}" if task.seq_num else None,
        )

        # Link task to session (best-effort)
        if session_id:
            resolved_session_id = session_id
            try:
                resolved_session_id = ctx.resolve_session_id(session_id)
            except ValueError:
                pass
            try:
                ctx.session_task_manager.link_task(resolved_session_id, resolved_id, "escalated")
            except Exception as e:
                logger.debug(f"Best-effort escalation linking failed: {e}")

        return {}

    registry.register(
        name="escalate_task",
        description="Escalate a task for human intervention. Sets status to 'escalated'. Use when the task cannot be completed and needs human attention.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
                "reason": {
                    "type": "string",
                    "description": "Why the task is being escalated (e.g., 'blocked by external dependency', 'needs architectural decision')",
                },
                "session_id": {
                    "type": "string",
                    "description": "Your session ID (accepts #N, N, UUID, or prefix). Optional.",
                    "default": None,
                },
            },
            "required": ["task_id", "reason"],
        },
        func=escalate_task,
    )


def register_mark_task_review_approved(
    registry: InternalToolRegistry, ctx: RegistryContext
) -> None:
    """Register the mark_task_review_approved tool on the given registry."""

    def mark_task_review_approved(
        task_id: str,
        session_id: str,
        approval_notes: str | None = None,
    ) -> dict[str, Any]:
        """Approve a task after review.

        Sets status to 'review_approved', indicating the review gate has passed.
        Accepts tasks in 'needs_review', 'in_progress', or 'escalated' status.

        Args:
            task_id: Task reference (#N, path, or UUID)
            session_id: Session ID approving the task
            approval_notes: Optional notes about the approval

        Returns:
            Empty dict on success, or error dict with details.
        """
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
        except TaskNotFoundError as e:
            return {"error": str(e)}
        except ValueError as e:
            return {"error": str(e)}

        task = ctx.task_manager.get_task(resolved_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        # Validate: current status must be needs_review, in_progress, or escalated
        if task.status not in ("needs_review", "in_progress", "escalated"):
            return {
                "error": f"Cannot approve task with status '{task.status}'. "
                "Task must be in 'needs_review', 'in_progress', or 'escalated' status to approve."
            }

        # Resolve session_id
        try:
            resolved_session_id = ctx.resolve_session_id(session_id)
        except ValueError as e:
            return {"error": f"Cannot resolve session '{session_id}': {e}"}

        # Build update kwargs
        update_kwargs: dict[str, Any] = {"status": "review_approved"}

        # Append approval notes to description if provided
        if approval_notes:
            current_desc = task.description or ""
            approval_section = f"\n\n[Approval Notes]\n{approval_notes}"
            update_kwargs["description"] = current_desc + approval_section

        # Update task status to review_approved
        updated = ctx.task_manager.update_task(resolved_id, **update_kwargs)
        if not updated:
            return {"error": f"Failed to approve task {task_id}"}

        notify_parent_on_status_change(
            ctx.task_manager.db,
            resolved_id,
            "review_approved",
            task_ref=f"#{task.seq_num}" if task.seq_num else None,
        )

        # Link task to session (best-effort)
        try:
            ctx.session_task_manager.link_task(resolved_session_id, resolved_id, "review_approved")
        except Exception:
            pass  # nosec B110 # best-effort linking

        return {}

    registry.register(
        name="mark_task_review_approved",
        description="Approve a task after review. Sets status to 'review_approved' (review gate passed). Accepts tasks in 'needs_review', 'in_progress', or 'escalated' status.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
                "session_id": {
                    "type": "string",
                    "description": "Your session ID (accepts #N, N, UUID, or prefix). The session approving the task.",
                },
                "approval_notes": {
                    "type": "string",
                    "description": "Optional notes about the approval.",
                    "default": None,
                },
            },
            "required": ["task_id", "session_id"],
        },
        func=mark_task_review_approved,
    )


def register_mark_task_needs_review(registry: InternalToolRegistry, ctx: RegistryContext) -> None:
    """Register the mark_task_needs_review tool on the given registry."""

    def mark_task_needs_review(
        task_id: str,
        session_id: str,
        review_notes: str | None = None,
    ) -> dict[str, Any]:
        """Mark a task as ready for review.

        Sets status to 'needs_review'. Use this when work is complete
        but needs human verification before closing.

        Args:
            task_id: Task reference (#N, path, or UUID)
            session_id: Session ID marking the task for review
            review_notes: Optional notes for the reviewer

        Returns:
            Empty dict on success, or error dict with details.
        """
        # Resolve task reference (supports #N, path, UUID formats)
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
        except TaskNotFoundError as e:
            return {"error": str(e)}
        except ValueError as e:
            return {"error": str(e)}

        task = ctx.task_manager.get_task(resolved_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        try:
            resolved_session_id = ctx.resolve_session_id(session_id)
        except ValueError as e:
            return {"error": f"Cannot resolve session '{session_id}': {e}"}

        # Build update kwargs
        update_kwargs: dict[str, Any] = {"status": "needs_review"}

        # Append review notes to description if provided
        if review_notes:
            current_desc = task.description or ""
            review_section = f"\n\n[Review Notes]\n{review_notes}"
            update_kwargs["description"] = current_desc + review_section

        # Update task status to needs_review
        updated = ctx.task_manager.update_task(resolved_id, **update_kwargs)
        if not updated:
            return {"error": f"Failed to mark task {task_id} for review"}

        notify_parent_on_status_change(
            ctx.task_manager.db,
            resolved_id,
            "needs_review",
            task_ref=f"#{task.seq_num}" if task.seq_num else None,
        )

        # Link task to session (best-effort, don't fail if this fails)
        try:
            ctx.session_task_manager.link_task(resolved_session_id, resolved_id, "needs_review")
        except Exception:
            pass  # nosec B110 # best-effort linking

        return {}

    registry.register(
        name="mark_task_needs_review",
        description="Mark a task as ready for review. Sets status to 'needs_review'. Use this when work is complete but needs human verification before closing.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
                "session_id": {
                    "type": "string",
                    "description": "Your session ID (accepts #N, N, UUID, or prefix). The session marking the task for review.",
                },
                "review_notes": {
                    "type": "string",
                    "description": "Optional notes for the reviewer explaining what was done and what to verify.",
                    "default": None,
                },
            },
            "required": ["task_id", "session_id"],
        },
        func=mark_task_needs_review,
    )
