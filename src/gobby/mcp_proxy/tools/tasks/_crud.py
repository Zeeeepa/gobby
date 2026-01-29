"""CRUD operations for task management.

Provides core task operations: create, get, update, list, and tree building.
"""

import logging
from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.tasks._context import RegistryContext
from gobby.mcp_proxy.tools.tasks._helpers import _infer_category
from gobby.mcp_proxy.tools.tasks._resolution import resolve_task_id_for_mcp
from gobby.storage.task_dependencies import DependencyCycleError
from gobby.storage.tasks import TaskNotFoundError
from gobby.utils.project_context import get_project_context
from gobby.utils.project_init import initialize_project

logger = logging.getLogger(__name__)


def create_crud_registry(ctx: RegistryContext) -> InternalToolRegistry:
    """Create a registry with task CRUD tools.

    Args:
        ctx: Shared registry context

    Returns:
        InternalToolRegistry with CRUD tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-tasks-crud",
        description="Task CRUD operations",
    )

    async def create_task(
        title: str,
        session_id: str,
        description: str | None = None,
        priority: int = 2,
        task_type: str = "task",
        parent_task_id: str | None = None,
        blocks: list[str] | None = None,
        depends_on: list[str] | None = None,
        labels: list[str] | None = None,
        category: str | None = None,
        validation_criteria: str | None = None,
        claim: bool = False,
    ) -> dict[str, Any]:
        """Create a single task in the current project.

        This tool creates exactly ONE task. Auto-decomposition of multi-step
        descriptions is disabled. Use expand_task for complex decompositions.

        Args:
            title: Task title
            session_id: Your session ID for tracking (REQUIRED).
            description: Detailed description
            priority: Priority level (1=High, 2=Medium, 3=Low)
            task_type: Task type (task, bug, feature, epic)
            parent_task_id: Optional parent task ID
            blocks: List of task IDs that this new task blocks
            depends_on: List of task IDs that this new task depends on (must complete first)
            labels: List of labels
            category: Task domain category (test, code, document, research, config, manual)
            validation_criteria: Acceptance criteria for validating completion.
            claim: If True, auto-claim the task (set assignee and status to in_progress).

        Returns:
            Created task dict with id (minimal) or full task details based on config.
        """
        # Get current project context which is required for task creation
        project_ctx = get_project_context()
        if project_ctx and project_ctx.get("id"):
            project_id = project_ctx["id"]
        else:
            init_result = initialize_project()
            project_id = init_result.project_id

        # Resolve parent_task_id if it's a reference format
        if parent_task_id:
            try:
                parent_task_id = resolve_task_id_for_mcp(
                    ctx.task_manager, parent_task_id, project_id
                )
            except (TaskNotFoundError, ValueError) as e:
                return {"error": f"Invalid parent_task_id: {e}"}

        # Auto-infer category if not provided
        effective_category = category
        if effective_category is None:
            effective_category = _infer_category(title, description)

        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        resolved_session_id = session_id
        try:
            resolved_session_id = ctx.resolve_session_id(session_id)
        except ValueError:
            pass  # Fall back to raw value if resolution fails

        # Create task
        create_result = ctx.task_manager.create_task_with_decomposition(
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
            task_type=task_type,
            parent_task_id=parent_task_id,
            labels=labels,
            category=effective_category,
            validation_criteria=validation_criteria,
            created_in_session_id=resolved_session_id,
        )

        task = ctx.task_manager.get_task(create_result["task"]["id"])

        # Link task to session (best-effort) - tracks which session created the task
        try:
            ctx.session_task_manager.link_task(resolved_session_id, task.id, "created")
        except Exception:
            pass  # nosec B110 - best-effort linking

        # Auto-claim if requested: set assignee and status to in_progress
        if claim:
            updated_task = ctx.task_manager.update_task(
                task.id,
                assignee=resolved_session_id,
                status="in_progress",
            )
            if updated_task is None:
                logger.warning(f"Failed to auto-claim task {task.id}: update_task returned None")
            else:
                task = updated_task
                # Link task to session with "claimed" action (best-effort)
                try:
                    ctx.session_task_manager.link_task(resolved_session_id, task.id, "claimed")
                except Exception:
                    pass  # nosec B110 - best-effort linking

            # Set workflow state for Claude Code (CC doesn't include tool results in PostToolUse)
            # This mirrors close_task behavior in _lifecycle.py:196-207
            try:
                state = ctx.workflow_state_manager.get_state(resolved_session_id)
                if state:
                    state.variables["task_claimed"] = True
                    state.variables["claimed_task_id"] = task.id  # Always use UUID
                    ctx.workflow_state_manager.save_state(state)
            except Exception:
                pass  # nosec B110 - best-effort state update

        # Handle 'blocks' argument if provided (syntactic sugar)
        # Collect errors consistently with depends_on handling below
        dependency_errors: list[str] = []
        if blocks:
            for blocked_id in blocks:
                try:
                    resolved_blocked = resolve_task_id_for_mcp(
                        ctx.task_manager, blocked_id, project_id
                    )
                    ctx.dep_manager.add_dependency(task.id, resolved_blocked, "blocks")
                except TaskNotFoundError:
                    dependency_errors.append(f"Task '{blocked_id}' not found (blocks)")
                except ValueError as e:
                    dependency_errors.append(f"Invalid ref '{blocked_id}' (blocks): {e}")
                except DependencyCycleError:
                    dependency_errors.append(f"Cycle detected for '{blocked_id}' (blocks)")

        # Handle 'depends_on' argument if provided
        # The new task depends on resolved_blocker, meaning resolved_blocker blocks the new task
        if depends_on:
            for blocker_ref in depends_on:
                try:
                    resolved_blocker = resolve_task_id_for_mcp(
                        ctx.task_manager, blocker_ref, project_id
                    )
                    ctx.dep_manager.add_dependency(resolved_blocker, task.id, "blocks")
                except TaskNotFoundError:
                    dependency_errors.append(f"Task '{blocker_ref}' not found")
                except ValueError as e:
                    dependency_errors.append(f"Invalid ref '{blocker_ref}': {e}")
                except DependencyCycleError:
                    dependency_errors.append(f"Cycle detected for '{blocker_ref}'")

        # Return minimal or full result based on config
        if ctx.show_result_on_create:
            result = task.to_dict()
        else:
            result = {
                "id": task.id,
                "seq_num": task.seq_num,
                "ref": f"#{task.seq_num}",
            }

        # Include dependency errors if any
        if dependency_errors:
            result["dependency_errors"] = dependency_errors
            result["warning"] = f"Task created but {len(dependency_errors)} dependency(s) failed"

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
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tasks this new task depends on (must complete first): #N, N, path, or UUID",
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
                    "description": "Task domain: 'code' (implementation), 'config' (configuration files), 'docs' (documentation), 'test' (test-writing), 'research' (investigation), 'planning' (design/architecture), or 'manual' (manual verification).",
                    "enum": ["code", "config", "docs", "test", "research", "planning", "manual"],
                    "default": None,
                },
                "validation_criteria": {
                    "type": "string",
                    "description": "Acceptance criteria for validating task completion (optional). If not provided and generate_validation is True, criteria will be auto-generated.",
                    "default": None,
                },
                "session_id": {
                    "type": "string",
                    "description": "Your session ID (accepts #N, N, UUID, or prefix). Required to track which session created the task.",
                },
                "claim": {
                    "type": "boolean",
                    "description": "If true, auto-claim the task (set assignee to session_id and status to in_progress). Default: false - task is created with status 'open' and no assignee.",
                    "default": False,
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
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
        except TaskNotFoundError as e:
            return {"error": str(e), "found": False}
        except ValueError as e:
            return {"error": str(e), "found": False}

        task = ctx.task_manager.get_task(resolved_id)
        if not task:
            return {"error": f"Task {task_id} not found", "found": False}

        result: dict[str, Any] = task.to_dict()

        # Enrich with dependency info
        blockers = ctx.dep_manager.get_blockers(resolved_id)
        blocking = ctx.dep_manager.get_blocking(resolved_id)

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
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
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
                    resolved_parent = resolve_task_id_for_mcp(ctx.task_manager, parent_task_id)
                    kwargs["parent_task_id"] = resolved_parent
                except (TaskNotFoundError, ValueError) as e:
                    logger.warning(f"Invalid parent_task_id '{parent_task_id}': {e}")
                    return {"error": f"Invalid parent_task_id '{parent_task_id}': {e}"}
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

        task = ctx.task_manager.update_task(resolved_id, **kwargs)
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
                    "description": "New status (open, in_progress, review, closed)",
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
                    "description": "Task domain: 'code' (implementation), 'config' (configuration files), 'docs' (documentation), 'test' (test-writing), 'research' (investigation), 'planning' (design/architecture), or 'manual' (manual verification).",
                    "enum": ["code", "config", "docs", "test", "research", "planning", "manual"],
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
        project_id = None if all_projects else ctx.get_current_project_id()

        # Resolve parent_task_id if it's a reference format
        if parent_task_id:
            try:
                parent_task_id = resolve_task_id_for_mcp(
                    ctx.task_manager, parent_task_id, project_id
                )
            except (TaskNotFoundError, ValueError) as e:
                return {"error": f"Invalid parent_task_id: {e}", "tasks": [], "count": 0}

        # Handle comma-separated status string
        status_filter: str | list[str] | None = status
        if isinstance(status, str) and "," in status:
            status_filter = [s.strip() for s in status.split(",")]

        tasks = ctx.task_manager.list_tasks(
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

    return registry


def build_task_tree(
    ctx: RegistryContext,
    tree: dict[str, Any],
    session_id: str,
) -> dict[str, Any]:
    """Create an entire task tree in one call.

    Creates tasks with parent-child relationships and wires dependencies
    based on `depends_on` title references within siblings.

    This is an internal helper function, NOT registered as an MCP tool.
    Agents should use expand_task with iterative mode for tree expansion.

    Args:
        ctx: Registry context
        tree: JSON tree structure with title, task_type, children, depends_on
        session_id: Your session ID for tracking (REQUIRED)

    Returns:
        Dict with success status, tasks_created count, epic_ref, task_refs

    Example tree:
        {
            "title": "Epic Title",
            "task_type": "epic",
            "children": [
                {
                    "title": "Phase 1",
                    "children": [
                        {"title": "Task A", "category": "code"},
                        {"title": "Task B", "category": "code", "depends_on": ["Task A"]}
                    ]
                }
            ]
        }
    """
    from gobby.tasks.tree_builder import TaskTreeBuilder

    # Get current project context
    project_ctx = get_project_context()
    if project_ctx and project_ctx.get("id"):
        project_id = project_ctx["id"]
    else:
        init_result = initialize_project()
        project_id = init_result.project_id

    # Build the tree
    builder = TaskTreeBuilder(
        task_manager=ctx.task_manager,
        project_id=project_id,
        session_id=session_id,
    )
    result = builder.build(tree)

    response: dict[str, Any] = {
        "success": len(result.errors) == 0,
        "tasks_created": result.tasks_created,
        "epic_ref": result.epic_ref,
        "task_refs": result.task_refs,
    }
    if result.errors:
        response["errors"] = result.errors

    return response
