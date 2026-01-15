"""
Internal MCP tools for Gobby Task System (facade module).

This module provides the main create_task_registry() factory function that
creates a unified tool registry by merging all task-related tool registries.

Tool categories (extracted to separate modules via Strangler Fig pattern):
- Core CRUD: create, get, update, close, delete, list (this module)
- Dependencies: add_dependency, remove_dependency, get_dependency_tree (task_dependencies.py)
- Readiness: list_ready_tasks, list_blocked_tasks, suggest_next_task (task_readiness.py)
- Sync/Git: sync_tasks, link_commit, auto_link_commits, get_task_diff (task_sync.py)
- Expansion: expand_task, expand_from_spec, analyze_complexity (task_expansion.py)
- Validation: validate_task, generate_validation_criteria (task_validation.py)

For direct access to specific registries, import from:
- gobby.mcp_proxy.tools.task_dependencies
- gobby.mcp_proxy.tools.task_readiness
- gobby.mcp_proxy.tools.task_sync
- gobby.mcp_proxy.tools.task_expansion
- gobby.mcp_proxy.tools.task_validation

Or import via the package __init__.py for convenience.
"""

from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry

# Import extracted registries for internal merging
from gobby.mcp_proxy.tools.task_dependencies import create_dependency_registry
from gobby.mcp_proxy.tools.task_expansion import create_expansion_registry
from gobby.mcp_proxy.tools.task_github import create_github_sync_registry
from gobby.mcp_proxy.tools.task_orchestration import create_orchestration_registry
from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry
from gobby.mcp_proxy.tools.task_sync import create_sync_registry
from gobby.mcp_proxy.tools.task_validation import create_validation_registry
from gobby.storage.projects import LocalProjectManager
from gobby.storage.session_tasks import SessionTaskManager
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import (
    LocalTaskManager,
    TaskNotFoundError,
)
from gobby.storage.worktrees import LocalWorktreeManager
from gobby.sync.tasks import TaskSyncManager
from gobby.tasks.commits import auto_link_commits as auto_link_commits_fn
from gobby.tasks.commits import get_task_diff, is_doc_only_diff, summarize_diff_for_validation
from gobby.tasks.expansion import TaskExpander
from gobby.tasks.validation import TaskValidator
from gobby.utils.project_context import get_project_context
from gobby.utils.project_init import initialize_project
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.state_manager import WorkflowStateManager

__all__ = ["create_task_registry", "resolve_task_id_for_mcp"]

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.config.app import DaemonConfig
    from gobby.mcp_proxy.manager import MCPClientManager
    from gobby.worktrees.git import WorktreeGitManager

# Reasons for which commit linking and validation are skipped when closing tasks
SKIP_REASONS: frozenset[str] = frozenset(
    {"duplicate", "already_implemented", "wont_fix", "obsolete"}
)

# Patterns that suggest a task is about manual testing/verification
_MANUAL_TEST_PATTERNS: tuple[str, ...] = (
    "verify that",
    "verify the",
    "check that",
    "check the",
    "functional test",
    "functional testing",
    "smoke test",
    "sanity test",
    "sanity check",
    "manual test",
    "manually verify",
    "manually test",
    "manually check",
    "run and check",
    "run and verify",
    "test that the",
    "confirm that",
    "ensure that",
    "validate that",
    "run each command",
    "run the command",
    "verify output",
    "check output",
    "verify functionality",
    "test functionality",
)


def _infer_category(title: str, description: str | None) -> str | None:
    """
    Infer category from task title/description patterns.

    Returns 'manual' if the task appears to be about manual verification/testing,
    None otherwise (let the user/LLM decide).
    """
    text = f"{title} {description or ''}".lower()
    for pattern in _MANUAL_TEST_PATTERNS:
        if pattern in text:
            return "manual"
    return None


def _is_path_format(ref: str) -> bool:
    """Check if a reference is in path format (e.g., 1.2.3)."""
    if "." not in ref:
        return False
    parts = ref.split(".")
    return all(part.isdigit() for part in parts)


def resolve_task_id_for_mcp(
    task_manager: LocalTaskManager,
    task_id: str,
    project_id: str | None = None,
) -> str:
    """Resolve a task reference to its UUID for MCP tools.

    Supports multiple reference formats:
      - #N: Project-scoped seq_num (e.g., #1, #47) - requires project_id
      - N: Bare numeric seq_num (e.g., 1, 47) - requires project_id
      - 1.2.3: Path cache format - requires project_id
      - UUID: Direct UUID lookup (validated to exist)

    Args:
        task_manager: The task manager
        task_id: Task reference in any supported format
        project_id: Project ID for scoped lookups (#N and path formats).
                   If not provided, will try to get from project context.

    Returns:
        The resolved task UUID

    Raises:
        TaskNotFoundError: If the reference cannot be resolved
        ValueError: If the format is invalid
    """
    # Get project_id from context if not provided
    if project_id is None:
        ctx = get_project_context()
        project_id = ctx.get("id") if ctx else None

    # Check for #N format or path format (requires project_id)
    if project_id and (task_id.startswith("#") or _is_path_format(task_id)):
        return task_manager.resolve_task_reference(task_id, project_id)

    # Check for bare numeric string (seq_num without #)
    if project_id and task_id.isdigit():
        return task_manager.resolve_task_reference(f"#{task_id}", project_id)

    # UUID format: validate it exists by trying to get it
    task = task_manager.get_task(task_id)
    if task is None:
        raise TaskNotFoundError(f"Task with UUID '{task_id}' not found")
    return task_id


def create_task_registry(
    task_manager: LocalTaskManager,
    sync_manager: TaskSyncManager,
    task_expander: TaskExpander | None = None,
    task_validator: TaskValidator | None = None,
    config: "DaemonConfig | None" = None,
    agent_runner: "AgentRunner | None" = None,
    worktree_storage: "LocalWorktreeManager | None" = None,
    git_manager: "WorktreeGitManager | None" = None,
    project_id: str | None = None,
    mcp_manager: "MCPClientManager | None" = None,
) -> InternalToolRegistry:
    """
    Create a task tool registry with all task-related tools.

    Args:
        task_manager: LocalTaskManager instance
        sync_manager: TaskSyncManager instance
        task_expander: TaskExpander instance (optional)
        task_validator: TaskValidator instance (optional)
        config: DaemonConfig instance (optional)
        agent_runner: AgentRunner instance for external validator agent mode (optional)
        worktree_storage: LocalWorktreeManager for orchestration (optional)
        git_manager: WorktreeGitManager for orchestration (optional)
        project_id: Default project ID for orchestration (optional)
        mcp_manager: MCPClientManager for GitHub integration (optional)

    Returns:
        InternalToolRegistry with all task tools registered
    """
    # Get config settings
    from gobby.config.tasks import TaskValidationConfig

    show_result_on_create = False
    auto_generate_on_expand = True
    validation_config: TaskValidationConfig | None = None
    if config is not None:
        show_result_on_create = config.get_gobby_tasks_config().show_result_on_create
        validation_config = config.get_gobby_tasks_config().validation
        auto_generate_on_expand = validation_config.auto_generate_on_expand
    registry = InternalToolRegistry(
        name="gobby-tasks",
        description="Task management - CRUD, dependencies, sync",
    )

    # Create project manager for looking up project repo_path
    project_manager = LocalProjectManager(task_manager.db)

    def get_project_repo_path(project_id: str | None) -> str | None:
        """Get the repo_path for a project by ID."""
        if not project_id:
            return None
        project = project_manager.get(project_id)
        return project.repo_path if project else None

    def get_current_project_id() -> str | None:
        """Get the current project ID from context, or None if not in a project."""
        ctx = get_project_context()
        if ctx and ctx.get("id"):
            project_id: str = ctx["id"]
            return project_id
        return None

    # Helper managers
    dep_manager = TaskDependencyManager(task_manager.db)
    session_task_manager = SessionTaskManager(task_manager.db)
    workflow_state_manager = WorkflowStateManager(task_manager.db)

    # Get TDD mode config setting (fallback when no workflow state)
    tdd_mode_config = False
    if config is not None:
        tdd_mode_config = config.get_gobby_tasks_config().expansion.tdd_mode

    def get_workflow_state(session_id: str | None) -> WorkflowState | None:
        """Get workflow state for a session, if available."""
        if not session_id:
            return None
        return workflow_state_manager.get_state(session_id)

    def resolve_tdd_mode(session_id: str | None) -> bool:
        """
        Resolve tdd_mode from workflow state > config hierarchy.

        Returns:
            True if TDD mode is enabled, False otherwise.
        """
        # Check workflow state first (takes precedence)
        state = get_workflow_state(session_id)
        if state and "tdd_mode" in state.variables:
            return bool(state.variables["tdd_mode"])

        # Fall back to config
        return tdd_mode_config

    # --- Task CRUD ---

    async def create_task(
        title: str,
        session_id: str,
        description: str | None = None,
        priority: int = 2,
        task_type: str = "task",
        parent_task_id: str | None = None,
        blocks: list[str] | None = None,
        labels: list[str] | None = None,
        category: str | None = None,
        validation_criteria: str | None = None,
    ) -> dict[str, Any]:
        """Create a single task in the current project.

        This tool creates exactly ONE task. Auto-decomposition of multi-step
        descriptions is disabled. Use expand_task for complex decompositions.

        Args:
            title: Task title
            session_id: Your session ID for tracking (REQUIRED)
            description: Detailed description
            priority: Priority level (1=High, 2=Medium, 3=Low)
            task_type: Task type (task, bug, feature, epic)
            parent_task_id: Optional parent task ID
            blocks: List of task IDs that this new task blocks
            labels: List of labels
            category: Testing strategy for this task
            validation_criteria: Acceptance criteria for validating completion.

        Returns:
            Created task dict with id (minimal) or full task details based on config.
        """
        # Get current project context which is required for task creation
        ctx = get_project_context()
        if ctx and ctx.get("id"):
            project_id = ctx["id"]
        else:
            init_result = initialize_project()
            project_id = init_result.project_id

        # Resolve parent_task_id if it's a reference format
        if parent_task_id:
            try:
                parent_task_id = resolve_task_id_for_mcp(task_manager, parent_task_id, project_id)
            except (TaskNotFoundError, ValueError) as e:
                return {"error": f"Invalid parent_task_id: {e}"}

        # Auto-infer category if not provided
        effective_category = category
        if effective_category is None:
            effective_category = _infer_category(title, description)

        # Create task
        create_result = task_manager.create_task_with_decomposition(
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
            task_type=task_type,
            parent_task_id=parent_task_id,
            labels=labels,
            category=effective_category,
            validation_criteria=validation_criteria,
            created_in_session_id=session_id,
        )

        task = task_manager.get_task(create_result["task"]["id"])

        # Handle 'blocks' argument if provided (syntactic sugar)
        if blocks:
            for blocked_id in blocks:
                dep_manager.add_dependency(task.id, blocked_id, "blocks")

        # Return minimal or full result based on config
        if show_result_on_create:
            result = task.to_dict()
        else:
            result = {
                "id": task.id,
                "seq_num": task.seq_num,
                "ref": f"#{task.seq_num}",
            }

        return result

    registry.register(
        name="create_task",
        description="Create a new task in the current project.",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "description": {
                    "type": "string",
                    "description": "Detailed description",
                    "default": None,
                },
                "priority": {
                    "type": "integer",
                    "description": "Priority level (1=High, 2=Medium, 3=Low)",
                    "default": 2,
                },
                "task_type": {
                    "type": "string",
                    "description": "Task type (task, bug, feature, epic)",
                    "default": "task",
                },
                "parent_task_id": {
                    "type": "string",
                    "description": "Parent task reference: #N, N (seq_num), path (1.2.3), or UUID",
                    "default": None,
                },
                "blocks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task IDs that this new task blocks (optional)",
                    "default": None,
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of labels (optional)",
                    "default": None,
                },
                "category": {
                    "type": "string",
                    "description": "Testing strategy: 'manual' (verify by running/inspecting, no automated tests required), 'automated' (requires unit/integration tests), or 'none' (no testing needed). Auto-inferred as 'manual' for verification/functional testing tasks if not specified.",
                    "enum": ["manual", "automated", "none"],
                    "default": None,
                },
                "validation_criteria": {
                    "type": "string",
                    "description": "Acceptance criteria for validating task completion (optional). If not provided and generate_validation is True, criteria will be auto-generated.",
                    "default": None,
                },
                "session_id": {
                    "type": "string",
                    "description": "Your session ID (from system context). Required to track which session created the task.",
                },
            },
            "required": ["title", "session_id"],
        },
        func=create_task,
    )

    def get_task(task_id: str) -> dict[str, Any]:
        """Get task details including dependencies."""
        # Resolve task reference (supports #N, path, UUID formats)
        try:
            resolved_id = resolve_task_id_for_mcp(task_manager, task_id)
        except TaskNotFoundError as e:
            return {"error": str(e), "found": False}
        except ValueError as e:
            return {"error": str(e), "found": False}

        task = task_manager.get_task(resolved_id)
        if not task:
            return {"error": f"Task {task_id} not found", "found": False}

        result: dict[str, Any] = task.to_dict()

        # Enrich with dependency info
        blockers = dep_manager.get_blockers(resolved_id)
        blocking = dep_manager.get_blocking(resolved_id)

        result["dependencies"] = {
            "blocked_by": [b.to_dict() for b in blockers],
            "blocking": [b.to_dict() for b in blocking],
        }

        return result

    registry.register(
        name="get_task",
        description="Get task details including dependencies. Task ID can be #N (e.g., #1), path (e.g., 1.2.3), or UUID.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
            },
            "required": ["task_id"],
        },
        func=get_task,
    )

    def update_task(
        task_id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        assignee: str | None = None,
        labels: list[str] | None = None,
        validation_criteria: str | None = None,
        parent_task_id: str | None = None,
        category: str | None = None,
        workflow_name: str | None = None,
        verification: str | None = None,
        sequence_order: int | None = None,
    ) -> dict[str, Any]:
        """Update task fields."""
        # Resolve task reference (supports #N, path, UUID formats)
        try:
            resolved_id = resolve_task_id_for_mcp(task_manager, task_id)
        except TaskNotFoundError as e:
            return {"error": str(e)}
        except ValueError as e:
            return {"error": str(e)}

        # Build kwargs only for non-None values to avoid overwriting with NULL
        kwargs: dict[str, Any] = {}
        if title is not None:
            kwargs["title"] = title
        if description is not None:
            kwargs["description"] = description
        if status is not None:
            kwargs["status"] = status
        if priority is not None:
            kwargs["priority"] = priority
        if assignee is not None:
            kwargs["assignee"] = assignee
        if labels is not None:
            kwargs["labels"] = labels
        if validation_criteria is not None:
            kwargs["validation_criteria"] = validation_criteria
        if parent_task_id is not None:
            # Empty string means "clear parent" - convert to None for storage layer
            # Also resolve parent_task_id if it's a reference format
            if parent_task_id:
                try:
                    resolved_parent = resolve_task_id_for_mcp(task_manager, parent_task_id)
                    kwargs["parent_task_id"] = resolved_parent
                except (TaskNotFoundError, ValueError):
                    kwargs["parent_task_id"] = parent_task_id  # Fall back to original
            else:
                kwargs["parent_task_id"] = None
        if category is not None:
            kwargs["category"] = category
        if workflow_name is not None:
            kwargs["workflow_name"] = workflow_name
        if verification is not None:
            kwargs["verification"] = verification
        if sequence_order is not None:
            kwargs["sequence_order"] = sequence_order

        task = task_manager.update_task(resolved_id, **kwargs)
        if not task:
            return {"error": f"Task {task_id} not found"}
        return {}

    registry.register(
        name="update_task",
        description="Update task fields.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
                "title": {"type": "string", "description": "New title", "default": None},
                "description": {
                    "type": "string",
                    "description": "New description",
                    "default": None,
                },
                "status": {
                    "type": "string",
                    "description": "New status (open, in_progress, closed)",
                    "default": None,
                },
                "priority": {"type": "integer", "description": "New priority", "default": None},
                "assignee": {"type": "string", "description": "New assignee", "default": None},
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New labels list",
                    "default": None,
                },
                "validation_criteria": {
                    "type": "string",
                    "description": "Acceptance criteria for validating task completion",
                    "default": None,
                },
                "parent_task_id": {
                    "type": "string",
                    "description": "Parent task reference: #N, N (seq_num), path (1.2.3), or UUID. Empty string clears parent.",
                    "default": None,
                },
                "category": {
                    "type": "string",
                    "description": "Testing strategy: 'manual' (verify by running/inspecting, no automated tests required), 'automated' (requires unit/integration tests), or 'none' (no testing needed).",
                    "enum": ["manual", "automated", "none"],
                    "default": None,
                },
                "workflow_name": {
                    "type": "string",
                    "description": "Workflow name for execution context",
                    "default": None,
                },
                "verification": {
                    "type": "string",
                    "description": "Verification steps or notes",
                    "default": None,
                },
                "sequence_order": {
                    "type": "integer",
                    "description": "Order in a sequence of tasks",
                    "default": None,
                },
            },
            "required": ["task_id"],
        },
        func=update_task,
    )

    def add_label(task_id: str, label: str) -> dict[str, Any]:
        """Add a label to a task."""
        try:
            resolved_id = resolve_task_id_for_mcp(task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}
        task = task_manager.add_label(resolved_id, label)
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
            resolved_id = resolve_task_id_for_mcp(task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}
        task = task_manager.remove_label(resolved_id, label)
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
            resolved_id = resolve_task_id_for_mcp(task_manager, task_id)
        except TaskNotFoundError as e:
            return {"error": str(e)}
        except ValueError as e:
            return {"error": str(e)}

        task = task_manager.get_task(resolved_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        # Link commit if provided (convenience for link + close in one call)
        if commit_sha:
            task = task_manager.link_commit(resolved_id, commit_sha)

        # Get project repo_path for git commands
        repo_path = get_project_repo_path(task.project_id)
        cwd = repo_path or "."

        # Check for linked commits (unless task type doesn't require commits)
        # Skip commit check for certain close reasons that imply no work was done
        requires_commit_check = reason.lower() not in SKIP_REASONS

        if requires_commit_check and not task.commits:
            # No commits linked - require explicit acknowledgment
            if no_commit_needed:
                if not override_justification:
                    return {
                        "error": "justification_required",
                        "message": "When no_commit_needed=True, you must provide override_justification explaining why no commit was needed.",
                    }
                # Allowed to proceed - agent confirmed no commit needed
            else:
                return {
                    "error": "no_commits_linked",
                    "message": (
                        "Cannot close task: no commits are linked. Either:\n"
                        "1. Commit your changes and use link_commit() or include [task_id] in commit message\n"
                        "2. Set no_commit_needed=True with override_justification if this task didn't require code changes"
                    ),
                }

        # Auto-skip validation for certain close reasons
        should_skip = skip_validation or reason.lower() in SKIP_REASONS

        if not should_skip:
            # Check if task has children (is a parent task)
            children = task_manager.list_tasks(parent_task_id=resolved_id, limit=1000)

            if children:
                # Parent task: must have all children closed
                open_children = [c for c in children if c.status != "closed"]
                if open_children:
                    open_titles = [f"- {c.id}: {c.title}" for c in open_children[:5]]
                    remaining = len(open_children) - 5 if len(open_children) > 5 else 0
                    feedback = f"Cannot close: {len(open_children)} child tasks still open:\n"
                    feedback += "\n".join(open_titles)
                    if remaining > 0:
                        feedback += f"\n... and {remaining} more"
                    return {
                        "error": "validation_failed",
                        "message": feedback,
                        "open_children": [c.id for c in open_children],
                    }
            elif task_validator and task.validation_criteria:
                # Leaf task with validation criteria: run LLM validation
                # Use provided changes_summary or auto-fetch via smart context gathering
                validation_context = changes_summary
                raw_diff = None  # Track the raw diff for doc-only check

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
                                import logging

                                logging.getLogger(__name__).warning(
                                    f"get_task_diff returned empty for task {task.id} "
                                    f"with commits {task.commits}"
                                )
                        except Exception as e:
                            import logging

                            logging.getLogger(__name__).warning(
                                f"get_task_diff failed for task {task.id}: {e}"
                            )

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

                # Auto-skip LLM validation for doc-only changes
                if raw_diff and is_doc_only_diff(raw_diff):
                    import logging

                    logging.getLogger(__name__).info(
                        f"Skipping LLM validation for task {task.id}: doc-only changes"
                    )
                    task_manager.update_task(
                        resolved_id,
                        validation_status="valid",
                        validation_feedback="Auto-validated: documentation-only changes",
                    )
                elif validation_context:
                    result = await task_validator.validate_task(
                        task_id=task.id,
                        title=task.title,
                        description=task.description,
                        changes_summary=validation_context,
                        validation_criteria=task.validation_criteria,
                        category=task.category,
                    )
                    # Store validation result regardless of pass/fail
                    task_manager.update_task(
                        resolved_id,
                        validation_status=result.status,
                        validation_feedback=result.feedback,
                    )
                    if result.status != "valid":
                        # Block closing on invalid or pending (error during validation)
                        return {
                            "error": "validation_failed",
                            "message": result.feedback or "Validation did not pass",
                            "validation_status": result.status,
                        }

                    # Run external validation if enabled (after internal validation passes)
                    if (
                        validation_config
                        and validation_config.use_external_validator
                        and validation_context
                    ):
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
                            agent_runner=agent_runner,
                        )

                        if external_result.status not in ("valid", "skipped"):
                            # Block closing on external validation failure
                            return {
                                "error": "external_validation_failed",
                                "message": external_result.summary,
                                "validation_status": external_result.status,
                                "issues": [issue.to_dict() for issue in external_result.issues],
                            }

        # Get git commit SHA (best-effort)
        from gobby.utils.git import run_git_command

        commit_sha = run_git_command(["git", "rev-parse", "HEAD"], cwd=cwd)

        # Determine target status: route to review if task requires user review OR override was used
        # This ensures tasks with HITL flag or skipped validation go through human review
        store_override = should_skip or no_commit_needed
        route_to_review = task.requires_user_review or (
            override_justification and store_override
        )

        if route_to_review:
            # Route to review status instead of closing
            # Task stays in review until user explicitly closes
            task_manager.update_task(
                resolved_id,
                status="review",
                validation_override_reason=override_justification if store_override else None,
            )

            # Auto-link session if provided
            if session_id:
                try:
                    session_task_manager.link_task(session_id, resolved_id, "review")
                except Exception:
                    pass  # nosec B110 - Best-effort linking

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
        task_manager.close_task(
            resolved_id,
            reason=reason,
            closed_in_session_id=session_id,
            closed_commit_sha=commit_sha,
            validation_override_reason=override_justification if store_override else None,
        )

        # Auto-link session if provided
        if session_id:
            try:
                session_task_manager.link_task(session_id, resolved_id, "closed")
            except Exception:
                pass  # nosec B110 - Best-effort linking, don't fail the close

        # Update worktree status based on closure reason (case-insensitive)
        try:
            reason_normalized = reason.lower()
            worktree_manager = LocalWorktreeManager(task_manager.db)
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
            pass  # nosec B110 - Best-effort worktree update, don't fail the close

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
        """Reopen a closed task.

        Args:
            task_id: Task reference (#N, path, or UUID)
            reason: Optional reason for reopening

        Returns:
            Reopened task or error
        """
        try:
            resolved_id = resolve_task_id_for_mcp(task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}

        try:
            task_manager.reopen_task(resolved_id, reason=reason)

            # Reactivate any associated worktrees that were marked merged/abandoned
            try:
                from gobby.storage.worktrees import WorktreeStatus

                worktree_manager = LocalWorktreeManager(task_manager.db)
                wt = worktree_manager.get_by_task(resolved_id)
                if wt and wt.status in (
                    WorktreeStatus.MERGED.value,
                    WorktreeStatus.ABANDONED.value,
                ):
                    worktree_manager.update(wt.id, status=WorktreeStatus.ACTIVE.value)
            except Exception:
                pass  # nosec B110 - Best-effort worktree update

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

    def delete_task(task_id: str, cascade: bool = True) -> dict[str, Any]:
        """Delete a task and its children by default."""
        try:
            resolved_id = resolve_task_id_for_mcp(task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}

        # Get task before deleting to capture seq_num for ref
        task = task_manager.get_task(resolved_id)
        if not task:
            return {"error": f"Task {task_id} not found"}
        ref = f"#{task.seq_num}" if task.seq_num else resolved_id[:8]

        deleted = task_manager.delete_task(resolved_id, cascade=cascade)
        if not deleted:
            return {"error": f"Task {task_id} not found"}

        return {
            "ref": ref,
            "deleted_task_id": resolved_id,  # UUID at end
        }

    registry.register(
        name="delete_task",
        description="Delete a task and its subtasks.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
                "cascade": {
                    "type": "boolean",
                    "description": "If True, delete all child tasks as well. Defaults to True.",
                    "default": True,
                },
            },
            "required": ["task_id"],
        },
        func=delete_task,
    )

    def list_tasks(
        status: str | list[str] | None = None,
        priority: int | None = None,
        task_type: str | None = None,
        assignee: str | None = None,
        label: str | None = None,
        parent_task_id: str | None = None,
        title_like: str | None = None,
        limit: int = 50,
        all_projects: bool = False,
    ) -> dict[str, Any]:
        """List tasks with optional filters."""
        # Filter by current project unless all_projects is True
        project_id = None if all_projects else get_current_project_id()

        # Resolve parent_task_id if it's a reference format
        if parent_task_id:
            try:
                parent_task_id = resolve_task_id_for_mcp(task_manager, parent_task_id, project_id)
            except (TaskNotFoundError, ValueError) as e:
                return {"error": f"Invalid parent_task_id: {e}", "tasks": [], "count": 0}

        # Handle comma-separated status string
        status_filter: str | list[str] | None = status
        if isinstance(status, str) and "," in status:
            status_filter = [s.strip() for s in status.split(",")]

        tasks = task_manager.list_tasks(
            status=status_filter,
            priority=priority,
            task_type=task_type,
            assignee=assignee,
            label=label,
            parent_task_id=parent_task_id,
            title_like=title_like,
            limit=limit,
            project_id=project_id,
        )
        return {"tasks": [t.to_brief() for t in tasks], "count": len(tasks)}

    registry.register(
        name="list_tasks",
        description="List tasks with optional filters.",
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
                    "description": "Filter by status. Can be a single status, array of statuses, or comma-separated string (e.g., 'open,in_progress')",
                    "default": None,
                },
                "priority": {
                    "type": "integer",
                    "description": "Filter by priority",
                    "default": None,
                },
                "task_type": {
                    "type": "string",
                    "description": "Filter by task type",
                    "default": None,
                },
                "assignee": {
                    "type": "string",
                    "description": "Filter by assignee",
                    "default": None,
                },
                "label": {
                    "type": "string",
                    "description": "Filter by label presence",
                    "default": None,
                },
                "parent_task_id": {
                    "type": "string",
                    "description": "Filter by parent task: #N, N (seq_num), path (1.2.3), or UUID",
                    "default": None,
                },
                "title_like": {
                    "type": "string",
                    "description": "Filter by title (fuzzy match)",
                    "default": None,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of tasks to return",
                    "default": 50,
                },
                "all_projects": {
                    "type": "boolean",
                    "description": "If true, list tasks from all projects instead of just the current project",
                    "default": False,
                },
            },
        },
        func=list_tasks,
    )

    # --- Session Integration ---

    def link_task_to_session(
        task_id: str,
        session_id: str | None = None,
        action: str = "worked_on",
    ) -> dict[str, Any]:
        """Link a task to a session."""
        if not session_id:
            return {"error": "session_id is required"}

        try:
            resolved_id = resolve_task_id_for_mcp(task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}

        try:
            session_task_manager.link_task(session_id, resolved_id, action)
            return {}
        except ValueError as e:
            return {"error": str(e)}

    registry.register(
        name="link_task_to_session",
        description="Link a task to a session.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID (optional, defaults to linking context if available)",
                    "default": None,
                },
                "action": {
                    "type": "string",
                    "description": "Relationship type (worked_on, discovered, mentioned, closed)",
                    "default": "worked_on",
                },
            },
            "required": ["task_id"],
        },
        func=link_task_to_session,
    )

    def get_session_tasks(session_id: str) -> dict[str, Any]:
        """Get all tasks associated with a session."""
        tasks = session_task_manager.get_session_tasks(session_id)
        return {"session_id": session_id, "tasks": tasks}

    registry.register(
        name="get_session_tasks",
        description="Get all tasks associated with a session.",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
            },
            "required": ["session_id"],
        },
        func=get_session_tasks,
    )

    def get_task_sessions(task_id: str) -> dict[str, Any]:
        """Get all sessions that touched a task."""
        try:
            resolved_id = resolve_task_id_for_mcp(task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}
        task = task_manager.get_task(resolved_id)
        sessions = session_task_manager.get_task_sessions(resolved_id)
        return {
            "ref": f"#{task.seq_num}" if task.seq_num else resolved_id[:8],
            "task_id": resolved_id,
            "sessions": sessions,
        }

    registry.register(
        name="get_task_sessions",
        description="Get all sessions that touched a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
            },
            "required": ["task_id"],
        },
        func=get_task_sessions,
    )

    # Merge validation tools from extracted module (Strangler Fig pattern)
    # This ensures backwards compatibility - all validation tools remain
    # accessible via the main task registry while implementation lives
    # in the task_validation module
    validation_registry = create_validation_registry(
        task_manager=task_manager,
        task_validator=task_validator,
        project_manager=project_manager,
        get_project_repo_path=get_project_repo_path,
    )
    for tool_name, tool in validation_registry._tools.items():
        registry._tools[tool_name] = tool

    # Merge expansion tools from extracted module (Strangler Fig pattern)
    expansion_registry = create_expansion_registry(
        task_manager=task_manager,
        task_expander=task_expander,
        task_validator=task_validator,
        auto_generate_on_expand=auto_generate_on_expand,
        resolve_tdd_mode=resolve_tdd_mode,
    )
    for tool_name, tool in expansion_registry._tools.items():
        registry._tools[tool_name] = tool

    # Merge dependency tools from extracted module (Strangler Fig pattern)
    dependency_registry = create_dependency_registry(
        task_manager=task_manager,
        dep_manager=dep_manager,
    )
    for tool_name, tool in dependency_registry._tools.items():
        registry._tools[tool_name] = tool

    # Merge readiness tools from extracted module (Strangler Fig pattern)
    readiness_registry = create_readiness_registry(
        task_manager=task_manager,
    )
    for tool_name, tool in readiness_registry._tools.items():
        registry._tools[tool_name] = tool

    # Merge sync tools from extracted module (Strangler Fig pattern)
    sync_registry = create_sync_registry(
        sync_manager=sync_manager,
        task_manager=task_manager,
        project_manager=project_manager,
        auto_link_commits_fn=auto_link_commits_fn,
        get_task_diff_fn=get_task_diff,
    )
    for tool_name, tool in sync_registry._tools.items():
        registry._tools[tool_name] = tool

    # Merge orchestration tools from extracted module (Strangler Fig pattern)
    # Only if worktree_storage is available (required for orchestration)
    if worktree_storage is not None:
        orchestration_registry = create_orchestration_registry(
            task_manager=task_manager,
            worktree_storage=worktree_storage,
            git_manager=git_manager,
            agent_runner=agent_runner,
            project_id=project_id,
        )
        for tool_name, tool in orchestration_registry._tools.items():
            registry._tools[tool_name] = tool

    # Merge GitHub sync tools from extracted module (Strangler Fig pattern)
    # Only if mcp_manager is available (required for GitHub MCP access)
    if mcp_manager is not None:
        github_registry = create_github_sync_registry(
            task_manager=task_manager,
            mcp_manager=mcp_manager,
            project_manager=project_manager,
            project_id=project_id,
        )
        for tool_name, tool in github_registry._tools.items():
            registry._tools[tool_name] = tool

    return registry
