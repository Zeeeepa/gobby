"""
Task enforcement actions for workflow engine.

Provides actions that enforce task tracking before allowing certain tools,
and enforce task completion before allowing agent to stop.
"""

import logging
import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig
    from gobby.storage.tasks import LocalTaskManager
    from gobby.workflows.definitions import WorkflowState

logger = logging.getLogger(__name__)


async def require_commit_before_stop(
    workflow_state: "WorkflowState | None",
    project_path: str | None = None,
    task_manager: "LocalTaskManager | None" = None,
) -> dict[str, Any] | None:
    """
    Block stop if there's an in_progress task with uncommitted changes.

    This action is designed for on_stop triggers to enforce that agents
    commit their work and close tasks before stopping.

    Args:
        workflow_state: Workflow state with variables (claimed_task_id, etc.)
        project_path: Path to the project directory for git status check
        task_manager: LocalTaskManager to verify task status

    Returns:
        Dict with decision="block" and reason if task has uncommitted changes,
        or None to allow the stop.
    """
    if not workflow_state:
        logger.debug("require_commit_before_stop: No workflow_state, allowing")
        return None

    claimed_task_id = workflow_state.variables.get("claimed_task_id")
    if not claimed_task_id:
        logger.debug("require_commit_before_stop: No claimed task, allowing")
        return None

    # Verify the task is actually still in_progress (not just cached in workflow state)
    if task_manager:
        task = task_manager.get_task(claimed_task_id)
        if not task or task.status != "in_progress":
            # Task was changed - clear the stale workflow state
            logger.debug(
                f"require_commit_before_stop: Task '{claimed_task_id}' is no longer "
                f"in_progress (status={task.status if task else 'not found'}), clearing state"
            )
            workflow_state.variables["claimed_task_id"] = None
            workflow_state.variables["task_claimed"] = False
            return None

    # Check for uncommitted changes
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.warning(
                f"require_commit_before_stop: git status failed: {result.stderr}"
            )
            return None

        uncommitted = result.stdout.strip()
        if not uncommitted:
            logger.debug("require_commit_before_stop: No uncommitted changes, allowing")
            return None

    except subprocess.TimeoutExpired:
        logger.warning("require_commit_before_stop: git status timed out")
        return None
    except FileNotFoundError:
        logger.warning("require_commit_before_stop: git not found")
        return None
    except Exception as e:
        logger.error(f"require_commit_before_stop: Error running git status: {e}")
        return None

    # Track how many times we've blocked to prevent infinite loops
    block_count = workflow_state.variables.get("_commit_block_count", 0)
    if block_count >= 3:
        logger.warning(
            f"require_commit_before_stop: Reached max block count ({block_count}), allowing"
        )
        return None

    workflow_state.variables["_commit_block_count"] = block_count + 1

    # Block - agent needs to commit and close
    logger.info(
        f"require_commit_before_stop: Blocking stop - task '{claimed_task_id}' "
        f"has uncommitted changes"
    )

    return {
        "decision": "block",
        "reason": (
            f"Task '{claimed_task_id}' is in_progress with uncommitted changes.\n\n"
            f"Before stopping, commit your changes and close the task:\n"
            f"1. Commit with [{claimed_task_id}] in the message\n"
            f"2. Close the task: close_task(task_id=\"{claimed_task_id}\", commit_sha=\"...\")"
        ),
    }


async def require_task_complete(
    task_manager: "LocalTaskManager | None",
    session_id: str,
    task_ids: list[str] | None,
    event_data: dict[str, Any] | None = None,
    project_id: str | None = None,
    workflow_state: "WorkflowState | None" = None,
) -> dict[str, Any] | None:
    """
    Block agent from stopping until task(s) (and their subtasks) are complete.

    This action is designed for on_stop triggers to enforce that the
    agent completes all subtasks under specified task(s) before stopping.

    Supports:
    - Single task: ["gt-abc123"]
    - Multiple tasks: ["gt-abc123", "gt-def456"]
    - Wildcard mode handled by caller (passes ready tasks as list)

    Logic per task:
    1. If task has incomplete subtasks and agent has no claimed task → suggest next subtask
    2. If task has incomplete subtasks and agent has claimed task → remind to finish it
    3. If all subtasks done but task not closed → remind to close the task
    4. If task is closed → move to next task in list

    Args:
        task_manager: LocalTaskManager for querying tasks
        session_id: Current session ID
        task_ids: List of task IDs to enforce completion on
        event_data: Hook event data
        project_id: Optional project ID for scoping
        workflow_state: Workflow state with variables (task_claimed, etc.)

    Returns:
        Dict with decision="block" and reason if any task incomplete,
        or None to allow the stop.
    """
    if not task_ids:
        logger.debug("require_task_complete: No task_ids specified, allowing")
        return None

    if not task_manager:
        logger.debug("require_task_complete: No task_manager available, allowing")
        return None

    # Track how many times we've blocked in this session
    block_count = 0
    if workflow_state:
        block_count = workflow_state.variables.get("_task_block_count", 0)

    # Safety valve: after 5 blocks, allow to prevent infinite loop
    if block_count >= 5:
        logger.warning(
            f"require_task_complete: Reached max block count ({block_count}), allowing stop"
        )
        return None

    # Check if agent has a claimed task this session
    has_claimed_task = False
    claimed_task_id = None
    if workflow_state:
        has_claimed_task = workflow_state.variables.get("task_claimed", False)
        claimed_task_id = workflow_state.variables.get("claimed_task_id")

    try:
        # Collect incomplete tasks across all specified task IDs
        all_incomplete: list[tuple[Any, list[Any]]] = []  # (parent_task, incomplete_subtasks)

        for task_id in task_ids:
            task = task_manager.get_task(task_id)
            if not task:
                logger.warning(f"require_task_complete: Task '{task_id}' not found, skipping")
                continue

            # If task is already closed, skip it
            if task.status == "closed":
                logger.debug(f"require_task_complete: Task '{task_id}' is closed, skipping")
                continue

            # Get all subtasks under this task
            subtasks = task_manager.list_tasks(parent_task_id=task_id)

            # Find incomplete subtasks
            incomplete = [t for t in subtasks if t.status != "closed"]

            # If task itself is incomplete (no subtasks or has incomplete subtasks)
            if not subtasks or incomplete:
                all_incomplete.append((task, incomplete))

        # If all tasks are complete, allow stop
        if not all_incomplete:
            logger.debug("require_task_complete: All specified tasks are complete, allowing")
            return None

        # Increment block count
        if workflow_state:
            workflow_state.variables["_task_block_count"] = block_count + 1

        # Get the first incomplete task to report on
        parent_task, incomplete = all_incomplete[0]
        task_id = parent_task.id
        remaining_tasks = len(all_incomplete)

        # Build suffix for multiple tasks
        multi_task_suffix = ""
        if remaining_tasks > 1:
            multi_task_suffix = f"\n\n({remaining_tasks} tasks remaining in total)"

        # Case 1: No incomplete subtasks, but task not closed (leaf task or parent with all done)
        if not incomplete:
            logger.info(
                f"require_task_complete: Task '{task_id}' needs closing"
            )
            return {
                "decision": "block",
                "reason": (
                    f"Task '{parent_task.title}' is ready to close.\n"
                    f"close_task(task_id=\"{task_id}\")"
                    f"{multi_task_suffix}"
                ),
            }

        # Case 2: Has incomplete subtasks, agent has no claimed task
        if not has_claimed_task:
            logger.info(
                f"require_task_complete: No claimed task, {len(incomplete)} incomplete subtasks"
            )
            return {
                "decision": "block",
                "reason": (
                    f"'{parent_task.title}' has {len(incomplete)} incomplete subtask(s).\n\n"
                    f"Use suggest_next_task() to find the best task to work on next."
                    f"{multi_task_suffix}"
                ),
            }

        # Case 3: Has claimed task but subtasks still incomplete
        if has_claimed_task and incomplete:
            # Check if the claimed task is under this parent
            claimed_under_parent = any(t.id == claimed_task_id for t in incomplete)

            if claimed_under_parent:
                logger.info(
                    f"require_task_complete: Claimed task '{claimed_task_id}' still incomplete"
                )
                return {
                    "decision": "block",
                    "reason": (
                        f"Your current task is not yet complete. "
                        f"Finish and close it before stopping:\n"
                        f"close_task(task_id=\"{claimed_task_id}\")\n\n"
                        f"'{parent_task.title}' still has {len(incomplete)} incomplete subtask(s)."
                        f"{multi_task_suffix}"
                    ),
                }
            else:
                # Claimed task is not under this parent - remind about parent work
                logger.info(
                    "require_task_complete: Claimed task not under parent, redirecting"
                )
                return {
                    "decision": "block",
                    "reason": (
                        f"'{parent_task.title}' has {len(incomplete)} incomplete subtask(s).\n\n"
                        f"Use suggest_next_task() to find the best task to work on next."
                        f"{multi_task_suffix}"
                    ),
                }

        # Fallback: shouldn't reach here, but block with generic message
        logger.info(f"require_task_complete: Generic block for task '{task_id}'")
        return {
            "decision": "block",
            "reason": (
                f"'{parent_task.title}' is not yet complete. "
                f"{len(incomplete)} subtask(s) remaining."
                f"{multi_task_suffix}"
            ),
        }

    except Exception as e:
        logger.error(f"require_task_complete: Error checking tasks: {e}")
        # On error, allow to avoid blocking legitimate work
        return None


async def require_active_task(
    task_manager: "LocalTaskManager | None",
    session_id: str,
    config: "DaemonConfig | None",
    event_data: dict[str, Any] | None,
    project_id: str | None = None,
    workflow_state: "WorkflowState | None" = None,
) -> dict[str, Any] | None:
    """
    Check if an active task exists before allowing protected tools.

    This action is designed to be used in on_before_tool triggers to enforce
    that agents create or start a gobby-task before modifying files.

    Session-scoped enforcement:
    - First checks if `task_claimed` variable is True in workflow state
    - If True, allows immediately (agent already claimed a task this session)
    - If False, falls back to project-wide DB check for helpful messaging

    Args:
        task_manager: LocalTaskManager for querying tasks
        session_id: Current session ID
        config: DaemonConfig with workflow settings
        event_data: Hook event data containing tool_name
        project_id: Optional project ID to filter tasks by project scope
        workflow_state: Optional workflow state to check task_claimed variable

    Returns:
        Dict with decision="block" if no active task and tool is protected,
        or None to allow the tool.
    """
    # Check if feature is enabled
    if not config:
        logger.debug("require_active_task: No config, allowing")
        return None

    workflow_config = config.workflow
    if not workflow_config.require_task_before_edit:
        logger.debug("require_active_task: Feature disabled, allowing")
        return None

    # Get the tool being called
    if not event_data:
        logger.debug("require_active_task: No event_data, allowing")
        return None

    tool_name = event_data.get("tool_name")
    if not tool_name:
        logger.debug("require_active_task: No tool_name in event_data, allowing")
        return None

    # Check if this tool is protected
    protected_tools = workflow_config.protected_tools
    if tool_name not in protected_tools:
        logger.debug(f"require_active_task: Tool '{tool_name}' not protected, allowing")
        return None

    # Tool is protected - check for active task

    # Session-scoped check: task_claimed variable (set by AFTER_TOOL detection)
    # This is the primary enforcement - each session must explicitly claim a task
    if workflow_state and workflow_state.variables.get("task_claimed"):
        logger.debug(
            f"require_active_task: task_claimed=True in session {session_id}, allowing"
        )
        return None

    # Fallback: Check for any in_progress task in the project
    # This provides helpful messaging about existing tasks but is NOT sufficient
    # for session-scoped enforcement (concurrent sessions shouldn't free-ride)
    project_task_hint = ""

    if task_manager is None:
        logger.debug(
            f"require_active_task: task_manager unavailable, skipping DB fallback check "
            f"(project_id={project_id}, session_id={session_id})"
        )
    else:
        try:
            project_tasks = task_manager.list_tasks(
                project_id=project_id,
                status="in_progress",
                limit=1,
            )

            if project_tasks:
                project_task_hint = (
                    f"\n\nNote: Task '{project_tasks[0].id}' ({project_tasks[0].title}) "
                    f"is in_progress but wasn't claimed by this session. "
                    f"Use `update_task(task_id=\"{project_tasks[0].id}\", status=\"in_progress\")` "
                    f"to claim it for this session."
                )
                logger.debug(
                    f"require_active_task: Found project task '{project_tasks[0].id}' but "
                    f"session hasn't claimed it"
                )

        except Exception as e:
            logger.error(f"require_active_task: Error querying tasks: {e}")
            # On error, allow to avoid blocking legitimate work
            return None

    # No task claimed this session - block the tool
    logger.info(
        f"require_active_task: Blocking '{tool_name}' - no task claimed for session {session_id}"
    )

    # Check if we've already shown the full error this session
    error_already_shown = False
    if workflow_state:
        error_already_shown = workflow_state.variables.get("task_error_shown", False)
        # Mark that we've shown the error (for next time)
        if not error_already_shown:
            workflow_state.variables["task_error_shown"] = True

    # Return short reminder if we've already shown the full error
    if error_already_shown:
        return {
            "decision": "block",
            "reason": "No task claimed. See previous **Task Required** error for instructions.",
            "inject_context": (
                f"**Task Required**: `{tool_name}` blocked. "
                f"Create or claim a task before editing files (see previous error for details)."
                f"{project_task_hint}"
            ),
        }

    # First time - show full instructions
    return {
        "decision": "block",
        "reason": (
            f"No task claimed for this session. Before using {tool_name}, please either:\n"
            f"- Create a task: call_tool(server_name='gobby-tasks', tool_name='create_task', arguments={{...}})\n"
            f"- Claim an existing task: call_tool(server_name='gobby-tasks', tool_name='update_task', "
            f"arguments={{'task_id': '...', 'status': 'in_progress'}})"
            f"{project_task_hint}"
        ),
        "inject_context": (
            f"**Task Required**: The `{tool_name}` tool is blocked until you claim a task for this session.\n\n"
            f"Each session must explicitly create or claim a task before modifying files:\n"
            f"1. **Create a new task**: `create_task(title=\"...\", description=\"...\")`\n"
            f"2. **Claim an existing task**: `update_task(task_id=\"...\", status=\"in_progress\")`\n\n"
            f"Use `list_ready_tasks()` to see available tasks."
            f"{project_task_hint}"
        ),
    }
