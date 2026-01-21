"""Lifecycle operations for task management.

Provides task lifecycle tools: close, reopen, delete, and label management.
"""

from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.tasks._context import RegistryContext
from gobby.mcp_proxy.tools.tasks._helpers import SKIP_REASONS
from gobby.mcp_proxy.tools.tasks._lifecycle_validation import (
    determine_close_outcome,
    gather_validation_context,
    validate_commit_requirements,
    validate_leaf_task_with_llm,
    validate_parent_task,
)
from gobby.mcp_proxy.tools.tasks._resolution import resolve_task_id_for_mcp
from gobby.storage.tasks import TaskNotFoundError
from gobby.storage.worktrees import LocalWorktreeManager


def create_lifecycle_registry(ctx: RegistryContext) -> InternalToolRegistry:
    """Create a registry with task lifecycle tools.

    Args:
        ctx: Shared registry context

    Returns:
        InternalToolRegistry with lifecycle tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-tasks-lifecycle",
        description="Task lifecycle operations",
    )

    async def close_task(
        task_id: str,
        reason: str = "completed",
        changes_summary: str | None = None,
        skip_validation: bool = False,
        session_id: str | None = None,
        override_justification: str | None = None,
        no_commit_needed: bool = False,
        commit_sha: str | None = None,
    ) -> dict[str, Any]:
        """Close a task with validation.

        For parent tasks: automatically checks all children are closed.
        For leaf tasks: optionally validates with LLM if changes_summary provided.

        Args:
            task_id: Task reference (#N, path, or UUID)
            reason: Reason for closing
            changes_summary: Summary of changes (enables LLM validation for leaf tasks)
            skip_validation: Skip all validation checks
            session_id: Session ID where task is being closed (auto-links to session)
            override_justification: Why agent bypassed validation (stored for audit).
                Also used to explain why no commit was needed when no_commit_needed=True.
            no_commit_needed: Set to True for tasks that don't produce code changes
                (research, planning, documentation review). Requires override_justification.
            commit_sha: Git commit SHA to link before closing. Convenience for link + close in one call.

        Returns:
            Closed task or error with validation feedback
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

        # Link commit if provided (convenience for link + close in one call)
        if commit_sha:
            task = ctx.task_manager.link_commit(resolved_id, commit_sha)

        # Get project repo_path for git commands
        repo_path = ctx.get_project_repo_path(task.project_id)
        cwd = repo_path or "."

        # Check for linked commits (unless task type doesn't require commits)
        commit_result = validate_commit_requirements(
            task, reason, no_commit_needed, override_justification
        )
        if not commit_result.can_close:
            return {
                "error": commit_result.error_type,
                "message": commit_result.message,
            }

        # Auto-skip validation for certain close reasons
        should_skip = skip_validation or reason.lower() in SKIP_REASONS

        if not should_skip:
            # Check if task has children (is a parent task)
            parent_result = validate_parent_task(ctx, resolved_id)
            if not parent_result.can_close:
                response = {
                    "error": parent_result.error_type,
                    "message": parent_result.message,
                }
                if parent_result.extra:
                    response.update(parent_result.extra)
                return response

            # Check for leaf task with validation criteria
            children = ctx.task_manager.list_tasks(parent_task_id=resolved_id, limit=1)
            is_leaf = len(children) == 0

            if is_leaf and ctx.task_validator and task.validation_criteria:
                # Gather validation context
                validation_context, raw_diff = gather_validation_context(
                    task, changes_summary, repo_path, ctx.task_manager
                )

                if validation_context:
                    # Run LLM validation
                    llm_result = await validate_leaf_task_with_llm(
                        task=task,
                        task_validator=ctx.task_validator,
                        validation_context=validation_context,
                        raw_diff=raw_diff,
                        ctx=ctx,
                        resolved_id=resolved_id,
                        validation_config=ctx.validation_config,
                    )
                    if not llm_result.can_close:
                        response = {
                            "error": llm_result.error_type,
                            "message": llm_result.message,
                        }
                        if llm_result.extra:
                            response.update(llm_result.extra)
                        return response

        # Determine close outcome
        route_to_review, store_override = determine_close_outcome(
            task, skip_validation, no_commit_needed, override_justification
        )

        # Get git commit SHA (best-effort, dynamic short format for consistency)
        from gobby.utils.git import run_git_command

        current_commit_sha = run_git_command(["git", "rev-parse", "--short", "HEAD"], cwd=cwd)

        if route_to_review:
            # Route to review status instead of closing
            # Task stays in review until user explicitly closes
            ctx.task_manager.update_task(
                resolved_id,
                status="review",
                validation_override_reason=override_justification if store_override else None,
            )

            # Auto-link session if provided
            if session_id:
                try:
                    ctx.session_task_manager.link_task(session_id, resolved_id, "review")
                except Exception:
                    pass  # nosec B110 - best-effort linking

            return {
                "routed_to_review": True,
                "message": (
                    "Task routed to review status. "
                    + (
                        "Reason: requires user review before closing."
                        if task.requires_user_review
                        else "Reason: validation was overridden, human review recommended."
                    )
                ),
                "task_id": resolved_id,
            }

        # All checks passed - close the task with session and commit tracking
        ctx.task_manager.close_task(
            resolved_id,
            reason=reason,
            closed_in_session_id=session_id,
            closed_commit_sha=current_commit_sha,
            validation_override_reason=override_justification if store_override else None,
        )

        # Auto-link session if provided
        if session_id:
            try:
                ctx.session_task_manager.link_task(session_id, resolved_id, "closed")
            except Exception:
                pass  # nosec B110 - best-effort linking, don't fail the close

        # Update worktree status based on closure reason (case-insensitive)
        try:
            reason_normalized = reason.lower()
            worktree_manager = LocalWorktreeManager(ctx.task_manager.db)
            wt = worktree_manager.get_by_task(resolved_id)
            if wt:
                if reason_normalized in (
                    "wont_fix",
                    "obsolete",
                    "duplicate",
                    "already_implemented",
                ):
                    worktree_manager.mark_abandoned(wt.id)
                elif reason_normalized == "completed":
                    worktree_manager.mark_merged(wt.id)
        except Exception:
            pass  # nosec B110 - best-effort worktree update, don't fail the close

        return {}

    registry.register(
        name="close_task",
        description="Close a task. Commits should use [#N] format (e.g., git commit -m '[#42] feat: add feature'). Requires commits to be linked (auto-detected from commit message or use link_commit). Parent tasks require all children closed. Leaf tasks validate with LLM. Validation auto-skipped for: duplicate, already_implemented, wont_fix, obsolete.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
                "reason": {
                    "type": "string",
                    "description": 'Reason for closing. Use "duplicate", "already_implemented", "wont_fix", or "obsolete" to auto-skip validation and commit check.',
                    "default": "completed",
                },
                "changes_summary": {
                    "type": "string",
                    "description": "Summary of changes made. If provided for leaf tasks, triggers LLM validation before close.",
                    "default": None,
                },
                "skip_validation": {
                    "type": "boolean",
                    "description": (
                        "Skip LLM validation even when task has validation_criteria. "
                        "USE THIS when: validation fails due to truncated diff, validator misses context, "
                        "or you've manually verified completion. Provide override_justification explaining why."
                    ),
                    "default": False,
                },
                "session_id": {
                    "type": "string",
                    "description": "Your session ID (from system context). Pass this to track which session closed the task.",
                    "default": None,
                },
                "override_justification": {
                    "type": "string",
                    "description": (
                        "Justification for bypassing validation or commit check. "
                        "Required when skip_validation=True or no_commit_needed=True. "
                        "Example: 'Validation saw truncated diff - verified via git show that commit includes all changes'"
                    ),
                    "default": None,
                },
                "no_commit_needed": {
                    "type": "boolean",
                    "description": (
                        "ONLY for tasks with NO code changes (pure research, planning, documentation review). "
                        "Do NOT use this to bypass validation when a commit exists - use skip_validation instead. "
                        "Requires override_justification."
                    ),
                    "default": False,
                },
                "commit_sha": {
                    "type": "string",
                    "description": "Git commit SHA to link before closing. Convenience for commit + close in one call.",
                    "default": None,
                },
            },
            "required": ["task_id"],
        },
        func=close_task,
    )

    def reopen_task(task_id: str, reason: str | None = None) -> dict[str, Any]:
        """Reopen a closed or review task.

        Args:
            task_id: Task reference (#N, path, or UUID)
            reason: Optional reason for reopening

        Returns:
            Reopened task or error. Resets accepted_by_user to false.
        """
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}

        try:
            ctx.task_manager.reopen_task(resolved_id, reason=reason)

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
            except Exception:
                pass  # nosec B110 - best-effort worktree update

            return {}
        except ValueError as e:
            return {"error": str(e)}

    registry.register(
        name="reopen_task",
        description="Reopen a closed task. Clears closed_at, closed_reason, and closed_in_session_id. Optionally appends a reopen reason to the description.",
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

    def delete_task(
        task_id: str, cascade: bool = True, unlink: bool = False
    ) -> dict[str, Any]:
        """Delete a task.

        By default (cascade=True), deletes subtasks and dependent tasks.
        Use unlink=True to remove dependency links but preserve dependent tasks.
        """
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}

        # Get task before deleting to capture seq_num for ref
        task = ctx.task_manager.get_task(resolved_id)
        if not task:
            return {"error": f"Task {task_id} not found"}
        ref = f"#{task.seq_num}" if task.seq_num else resolved_id[:8]

        try:
            deleted = ctx.task_manager.delete_task(
                resolved_id, cascade=cascade, unlink=unlink
            )
            if not deleted:
                return {"error": f"Task {task_id} not found"}
        except ValueError as e:
            error_msg = str(e)
            if "dependent task(s)" in error_msg:
                return {
                    "error": "has_dependents",
                    "message": error_msg,
                    "suggestion": f"Use cascade=True to delete task {ref} and its dependents, "
                    f"or unlink=True to preserve dependent tasks.",
                }
            elif "has children" in error_msg:
                return {
                    "error": "has_children",
                    "message": error_msg,
                    "suggestion": f"Use cascade=True to delete task {ref} and all its subtasks.",
                }
            return {"error": error_msg}

        return {
            "ref": ref,
            "deleted_task_id": resolved_id,  # UUID at end
        }

    registry.register(
        name="delete_task",
        description="Delete a task. By default (cascade=True), deletes subtasks and dependent tasks. "
        "Set cascade=False to fail if task has children or dependents. "
        "Use unlink=True to remove dependency links but preserve dependent tasks.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
                "cascade": {
                    "type": "boolean",
                    "description": "If True, delete subtasks and dependent tasks. Defaults to True.",
                    "default": True,
                },
                "unlink": {
                    "type": "boolean",
                    "description": "If True, remove dependency links but preserve dependent tasks. "
                    "Ignored if cascade=True.",
                    "default": False,
                },
            },
            "required": ["task_id"],
        },
        func=delete_task,
    )

    def add_label(task_id: str, label: str) -> dict[str, Any]:
        """Add a label to a task."""
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}
        task = ctx.task_manager.add_label(resolved_id, label)
        if not task:
            return {"error": f"Task {task_id} not found"}
        return {}

    registry.register(
        name="add_label",
        description="Add a label to a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
                "label": {"type": "string", "description": "Label to add"},
            },
            "required": ["task_id", "label"],
        },
        func=add_label,
    )

    def remove_label(task_id: str, label: str) -> dict[str, Any]:
        """Remove a label from a task."""
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}
        task = ctx.task_manager.remove_label(resolved_id, label)
        if not task:
            return {"error": f"Task {task_id} not found"}
        return {}

    registry.register(
        name="remove_label",
        description="Remove a label from a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
                "label": {"type": "string", "description": "Label to remove"},
            },
            "required": ["task_id", "label"],
        },
        func=remove_label,
    )

    def claim_task(
        task_id: str,
        session_id: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """Claim a task for the current session.

        Combines setting the assignee and marking as in_progress in a single
        atomic operation. Detects conflicts when another session has already
        claimed the task.

        Args:
            task_id: Task reference (#N, path, or UUID)
            session_id: Session ID claiming the task
            force: Override existing claim by another session (default: False)

        Returns:
            Empty dict on success, or error dict with conflict information.
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

        # Check if already claimed by another session
        if task.assignee and task.assignee != session_id and not force:
            return {
                "error": "Task already claimed by another session",
                "claimed_by": task.assignee,
                "message": f"Task is already claimed by session '{task.assignee}'. Use force=True to override.",
            }

        # Update task with assignee and status in single atomic call
        updated = ctx.task_manager.update_task(
            resolved_id,
            assignee=session_id,
            status="in_progress",
        )
        if not updated:
            return {"error": f"Failed to claim task {task_id}"}

        # Link task to session (best-effort, don't fail the claim if this fails)
        try:
            ctx.session_task_manager.link_task(session_id, resolved_id, "claimed")
        except Exception:
            pass  # nosec B110 - best-effort linking

        return {}

    registry.register(
        name="claim_task",
        description="Claim a task for your session. Sets assignee to session_id and status to in_progress. Detects conflicts if already claimed by another session.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
                "session_id": {
                    "type": "string",
                    "description": "Your session ID (from system context). The session claiming the task.",
                },
                "force": {
                    "type": "boolean",
                    "description": "Override existing claim by another session (default: False)",
                    "default": False,
                },
            },
            "required": ["task_id", "session_id"],
        },
        func=claim_task,
    )

    return registry
