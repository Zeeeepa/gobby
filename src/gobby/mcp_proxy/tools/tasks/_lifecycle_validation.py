"""Validation helpers for task lifecycle operations.

Provides validation functions used by close_task to verify tasks
can be closed (commit checks, child completion, LLM validation).
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.tasks._helpers import SKIP_REASONS
from gobby.storage.tasks import Task

if TYPE_CHECKING:
    from gobby.config.tasks import TaskValidationConfig
    from gobby.mcp_proxy.tools.tasks._context import RegistryContext
    from gobby.storage.tasks import LocalTaskManager
    from gobby.tasks.validation import TaskValidator

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validation checks."""

    can_close: bool
    error_type: str | None = None
    message: str | None = None
    extra: dict[str, Any] | None = None


def validate_commit_requirements(
    task: Task,
    reason: str,
    no_commit_needed: bool,
    override_justification: str | None,
    repo_path: str | None = None,
) -> ValidationResult:
    """Check if task meets commit requirements for closing.

    Args:
        task: The task to validate
        reason: Reason for closing
        no_commit_needed: If True, allow closing without commits
        override_justification: Justification for skipping commit check
        repo_path: Path to the repository for git operations

    Returns:
        ValidationResult indicating if task can be closed
    """
    # Skip commit check for certain close reasons that imply no work was done
    requires_commit_check = reason.lower() not in SKIP_REASONS

    if requires_commit_check and not task.commits:
        # No commits linked - require explicit acknowledgment
        if no_commit_needed:
            # Check for uncommitted changes FIRST - hard blocker regardless of justification
            # If there are uncommitted changes, claiming "no commit needed" is a contradiction
            uncommitted_result = _check_uncommitted_changes(repo_path)
            if uncommitted_result:
                return uncommitted_result

            # Only then require justification (when there truly are no uncommitted changes)
            if not override_justification:
                return ValidationResult(
                    can_close=False,
                    error_type="justification_required",
                    message=(
                        "When no_commit_needed=True, you must provide "
                        "override_justification explaining why no commit was needed."
                    ),
                )

            # Allowed to proceed - no uncommitted changes and agent confirmed no commit needed
        else:
            return ValidationResult(
                can_close=False,
                error_type="no_commits_linked",
                message=(
                    "Cannot close task: no commits are linked. Either:\n"
                    "1. Commit your changes and use close_task(task_id, commit_sha='...') to link and close in one call\n"
                    "2. Include [#N] in your commit message for auto-linking, then call close_task\n"
                    "3. Set no_commit_needed=True with override_justification if this task didn't require code changes"
                ),
            )

    return ValidationResult(can_close=True)


def _check_uncommitted_changes(repo_path: str | None) -> ValidationResult | None:
    """Check if there are uncommitted changes to tracked files.

    Args:
        repo_path: Path to the repository

    Returns:
        ValidationResult if uncommitted changes detected, None otherwise
    """
    from gobby.utils.git import run_git_command

    cwd = repo_path or "."

    try:
        # Check for staged changes
        staged = run_git_command(["git", "diff", "--cached", "--name-only"], cwd=cwd)
        # Check for unstaged changes to tracked files
        unstaged = run_git_command(["git", "diff", "--name-only"], cwd=cwd)

        staged_files = [f for f in (staged or "").strip().split("\n") if f]
        unstaged_files = [f for f in (unstaged or "").strip().split("\n") if f]

        if staged_files or unstaged_files:
            all_files = sorted(set(staged_files + unstaged_files))
            file_list = ", ".join(all_files[:5])
            if len(all_files) > 5:
                file_list += f" and {len(all_files) - 5} more"

            return ValidationResult(
                can_close=False,
                error_type="uncommitted_changes",
                message=(
                    f"Cannot use no_commit_needed=True: tracked files have uncommitted changes "
                    f"({file_list}). Commit your changes first: "
                    "git add . && git commit -m '[task-id] ...'"
                ),
                extra={"uncommitted_files": all_files},
            )
    except Exception as e:
        # If git operations fail (not a git repo, etc.), allow proceed
        logger.debug(f"Git check failed (allowing proceed): {e}")

    return None


def validate_parent_task(
    ctx: "RegistryContext",
    task_id: str,
) -> ValidationResult:
    """Check if a parent task's children are all closed.

    Args:
        ctx: Registry context
        task_id: The parent task ID

    Returns:
        ValidationResult indicating if parent can be closed
    """
    children = ctx.task_manager.list_tasks(parent_task_id=task_id, limit=1000)

    if children:
        open_children = [c for c in children if c.status != "closed"]
        if open_children:
            open_titles = [f"- {c.id}: {c.title}" for c in open_children[:5]]
            remaining = len(open_children) - 5 if len(open_children) > 5 else 0
            feedback = f"Cannot close: {len(open_children)} child tasks still open:\n"
            feedback += "\n".join(open_titles)
            if remaining > 0:
                feedback += f"\n... and {remaining} more"
            return ValidationResult(
                can_close=False,
                error_type="validation_failed",
                message=feedback,
                extra={"open_children": [c.id for c in open_children]},
            )

    return ValidationResult(can_close=True)


def gather_validation_context(
    task: Task,
    changes_summary: str | None,
    repo_path: str | None,
    task_manager: "LocalTaskManager",
) -> tuple[str | None, str | None]:
    """Gather context for LLM validation.

    Uses provided changes_summary or auto-fetches via smart context gathering.

    Args:
        task: The task to validate
        changes_summary: Optional user-provided summary
        repo_path: Path to the repository
        task_manager: LocalTaskManager for fetching task diff

    Returns:
        Tuple of (validation_context, raw_diff)
    """
    from gobby.tasks.commits import get_task_diff, summarize_diff_for_validation

    validation_context = changes_summary
    raw_diff = None

    if not validation_context:
        # First try commit-based diff if task has linked commits
        if task.commits:
            try:
                # Don't include uncommitted changes - they're likely unrelated to this task
                # The linked commits ARE the work for this task
                diff_result = get_task_diff(
                    task_id=task.id,
                    task_manager=task_manager,
                    include_uncommitted=False,
                    cwd=repo_path,
                )
                if diff_result.diff:
                    raw_diff = diff_result.diff
                    # Use smart summarization to ensure all files are visible
                    summarized_diff = summarize_diff_for_validation(raw_diff)
                    validation_context = (
                        f"Commit-based diff ({len(diff_result.commits)} commits, "
                        f"{diff_result.file_count} files):\n\n{summarized_diff}"
                    )
                else:
                    logger.warning(
                        f"get_task_diff returned empty for task {task.id} "
                        f"with commits {task.commits}"
                    )
            except Exception as e:
                logger.warning(f"get_task_diff failed for task {task.id}: {e}")

        # Fall back to smart context ONLY if no linked commits
        # (uncommitted changes are unrelated if we have specific commits linked)
        if not validation_context and not task.commits:
            from gobby.tasks.validation import get_validation_context_smart

            # Smart context gathering: uncommitted changes + multi-commit window + file analysis
            smart_context = get_validation_context_smart(
                task_title=task.title,
                validation_criteria=task.validation_criteria,
                task_description=task.description,
                cwd=repo_path,
            )
            if smart_context:
                validation_context = f"Validation context:\n\n{smart_context}"

    return validation_context, raw_diff


async def validate_leaf_task_with_llm(
    task: Task,
    task_validator: "TaskValidator",
    validation_context: str,
    raw_diff: str | None,
    ctx: "RegistryContext",
    resolved_id: str,
    validation_config: "TaskValidationConfig | None",
) -> ValidationResult:
    """Run LLM validation on a leaf task.

    Args:
        task: The task to validate
        task_validator: The validator instance
        validation_context: Context for validation
        raw_diff: Raw diff for doc-only check
        ctx: Registry context
        resolved_id: Resolved task ID
        validation_config: Validation configuration

    Returns:
        ValidationResult indicating if task can be closed
    """
    from gobby.tasks.commits import is_doc_only_diff

    # Auto-skip LLM validation for doc-only changes
    if raw_diff and is_doc_only_diff(raw_diff):
        logger.info(f"Skipping LLM validation for task {task.id}: doc-only changes")
        ctx.task_manager.update_task(
            resolved_id,
            validation_status="valid",
            validation_feedback="Auto-validated: documentation-only changes",
        )
        return ValidationResult(can_close=True)

    # Run LLM validation
    result = await task_validator.validate_task(
        task_id=task.id,
        title=task.title,
        description=task.description,
        changes_summary=validation_context,
        validation_criteria=task.validation_criteria,
        category=task.category,
    )

    # Store validation result regardless of pass/fail
    ctx.task_manager.update_task(
        resolved_id,
        validation_status=result.status,
        validation_feedback=result.feedback,
    )

    if result.status != "valid":
        # Block closing on invalid or pending (error during validation)
        return ValidationResult(
            can_close=False,
            error_type="validation_failed",
            message=result.feedback or "Validation did not pass",
            extra={"validation_status": result.status},
        )

    # Run external validation if enabled (after internal validation passes)
    if validation_config and validation_config.use_external_validator:
        from gobby.tasks.external_validator import run_external_validation

        external_result = await run_external_validation(
            config=validation_config,
            llm_service=task_validator.llm_service,
            task={
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "validation_criteria": task.validation_criteria,
            },
            changes_context=validation_context,
            agent_runner=ctx.agent_runner,
        )

        if external_result.status not in ("valid", "skipped"):
            # Block closing on external validation failure
            return ValidationResult(
                can_close=False,
                error_type="external_validation_failed",
                message=external_result.summary,
                extra={
                    "validation_status": external_result.status,
                    "issues": [issue.to_dict() for issue in external_result.issues],
                },
            )

    return ValidationResult(can_close=True)


def determine_close_outcome(
    task: Task,
    skip_validation: bool,
    no_commit_needed: bool,
    override_justification: str | None,
) -> tuple[bool, bool]:
    """Determine the close outcome for a task.

    Args:
        task: The task being closed
        skip_validation: Whether validation was skipped
        no_commit_needed: Whether commit was not needed
        override_justification: Justification for override

    Returns:
        Tuple of (route_to_review, store_override)
    """
    # Determine if override should be stored
    store_override = skip_validation or no_commit_needed

    # Route to review if task requires user review OR override was used
    # This ensures tasks with HITL flag or skipped validation go through human review
    route_to_review = bool(task.requires_user_review or (override_justification and store_override))

    return route_to_review, store_override
