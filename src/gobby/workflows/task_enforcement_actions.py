"""
Task enforcement actions for workflow engine.

Provides actions that enforce task tracking before allowing certain tools,
and enforce epic completion before allowing agent to stop.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig
    from gobby.storage.tasks import LocalTaskManager
    from gobby.workflows.definitions import WorkflowState

logger = logging.getLogger(__name__)


async def require_epic_complete(
    task_manager: "LocalTaskManager | None",
    session_id: str,
    epic_task_id: str | None,
    event_data: dict[str, Any] | None = None,
    project_id: str | None = None,
    workflow_state: "WorkflowState | None" = None,
) -> dict[str, Any] | None:
    """
    Block agent from stopping until all tasks under an epic are complete.

    This action is designed for on_after_agent triggers to enforce that the
    agent completes all subtasks under a parent epic before stopping.

    Logic:
    1. If epic has incomplete subtasks and agent has no claimed task → suggest next subtask
    2. If epic has incomplete subtasks and agent has claimed task → remind to finish it
    3. If all subtasks done but epic not closed → remind to close the epic
    4. If epic is closed → allow stop

    Args:
        task_manager: LocalTaskManager for querying tasks
        session_id: Current session ID
        epic_task_id: The parent epic task ID to enforce completion on
        event_data: Hook event data (includes stop_hook_active flag)
        project_id: Optional project ID for scoping
        workflow_state: Workflow state with variables (task_claimed, etc.)

    Returns:
        Dict with decision="block" and reason if epic incomplete,
        or None to allow the stop.
    """
    if not epic_task_id:
        logger.debug("require_epic_complete: No epic_task_id specified, allowing")
        return None

    if not task_manager:
        logger.debug("require_epic_complete: No task_manager available, allowing")
        return None

    # Check stop_hook_active to prevent infinite loops
    # If we've already blocked once and agent is continuing, check iteration count
    stop_hook_active = False
    if event_data:
        stop_hook_active = event_data.get("stop_hook_active", False)

    # Track how many times we've blocked in this session
    block_count = 0
    if workflow_state:
        block_count = workflow_state.variables.get("_epic_block_count", 0)

    # Safety valve: after 5 blocks, allow to prevent infinite loop
    if block_count >= 5:
        logger.warning(
            f"require_epic_complete: Reached max block count ({block_count}), allowing stop"
        )
        return None

    try:
        # Get the epic task
        epic = task_manager.get_task(epic_task_id)
        if not epic:
            logger.warning(f"require_epic_complete: Epic '{epic_task_id}' not found, allowing")
            return None

        # If epic is already closed, allow
        if epic.status == "closed":
            logger.debug(f"require_epic_complete: Epic '{epic_task_id}' is closed, allowing")
            return None

        # Get all subtasks under this epic
        subtasks = task_manager.list_tasks(parent_task_id=epic_task_id)

        # Find incomplete subtasks
        incomplete = [t for t in subtasks if t.status != "closed"]
        in_progress = [t for t in subtasks if t.status == "in_progress"]

        # Check if agent has a claimed task this session
        has_claimed_task = False
        claimed_task_id = None
        if workflow_state:
            has_claimed_task = workflow_state.variables.get("task_claimed", False)
            claimed_task_id = workflow_state.variables.get("claimed_task_id")

        # Increment block count
        if workflow_state:
            workflow_state.variables["_epic_block_count"] = block_count + 1

        # Case 1: No incomplete subtasks, but epic not closed
        if not incomplete:
            logger.info(
                f"require_epic_complete: All subtasks done, epic '{epic_task_id}' needs closing"
            )
            return {
                "decision": "block",
                "reason": (
                    f"All subtasks under epic '{epic.title}' are complete. "
                    f"Close the parent epic to finish:\n"
                    f"close_task(task_id=\"{epic_task_id}\")"
                ),
            }

        # Case 2: Has incomplete subtasks, agent has no claimed task
        if not has_claimed_task:
            # Find next ready subtask (open, not blocked)
            ready_subtasks = [t for t in incomplete if t.status == "open"]
            if ready_subtasks:
                next_task = ready_subtasks[0]
                logger.info(
                    f"require_epic_complete: No claimed task, suggesting '{next_task.id}'"
                )
                return {
                    "decision": "block",
                    "reason": (
                        f"Epic '{epic.title}' has {len(incomplete)} incomplete subtask(s). "
                        f"Claim and work on the next one:\n"
                        f"update_task(task_id=\"{next_task.id}\", status=\"in_progress\")\n\n"
                        f"Next subtask: {next_task.title}"
                    ),
                }
            elif in_progress:
                # There are in-progress tasks but not claimed by this session
                next_task = in_progress[0]
                logger.info(
                    f"require_epic_complete: Found in_progress task '{next_task.id}' to claim"
                )
                return {
                    "decision": "block",
                    "reason": (
                        f"Epic '{epic.title}' has {len(incomplete)} incomplete subtask(s). "
                        f"Task '{next_task.id}' is in progress - claim it:\n"
                        f"update_task(task_id=\"{next_task.id}\", status=\"in_progress\")\n\n"
                        f"Task: {next_task.title}"
                    ),
                }

        # Case 3: Has claimed task but subtasks still incomplete
        if has_claimed_task and incomplete:
            # Check if the claimed task is under this epic
            claimed_under_epic = any(t.id == claimed_task_id for t in subtasks)

            if claimed_under_epic:
                logger.info(
                    f"require_epic_complete: Claimed task '{claimed_task_id}' still incomplete"
                )
                return {
                    "decision": "block",
                    "reason": (
                        f"Your current task is not yet complete. "
                        f"Finish and close it before stopping:\n"
                        f"close_task(task_id=\"{claimed_task_id}\")\n\n"
                        f"Epic '{epic.title}' still has {len(incomplete)} incomplete subtask(s)."
                    ),
                }
            else:
                # Claimed task is not under this epic - remind about epic work
                next_task = incomplete[0]
                logger.info(
                    "require_epic_complete: Claimed task not under epic, redirecting"
                )
                return {
                    "decision": "block",
                    "reason": (
                        f"Epic '{epic.title}' has {len(incomplete)} incomplete subtask(s). "
                        f"Work on the next subtask:\n"
                        f"update_task(task_id=\"{next_task.id}\", status=\"in_progress\")\n\n"
                        f"Next: {next_task.title}"
                    ),
                }

        # Fallback: shouldn't reach here, but block with generic message
        logger.info(f"require_epic_complete: Generic block for epic '{epic_task_id}'")
        return {
            "decision": "block",
            "reason": (
                f"Epic '{epic.title}' is not yet complete. "
                f"{len(incomplete)} subtask(s) remaining."
            ),
        }

    except Exception as e:
        logger.error(f"require_epic_complete: Error checking epic: {e}")
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
    has_project_task = False
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
                has_project_task = True
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
