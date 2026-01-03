"""
Task enforcement actions for workflow engine.

Provides actions that enforce task tracking before allowing certain tools.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig
    from gobby.storage.tasks import LocalTaskManager

logger = logging.getLogger(__name__)


async def require_active_task(
    task_manager: "LocalTaskManager | None",
    session_id: str,
    config: "DaemonConfig | None",
    event_data: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    Check if an active task exists before allowing protected tools.

    This action is designed to be used in on_before_tool triggers to enforce
    that agents create or start a gobby-task before modifying files.

    Args:
        task_manager: LocalTaskManager for querying tasks
        session_id: Current session ID
        config: DaemonConfig with workflow settings
        event_data: Hook event data containing tool_name

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
    if not task_manager:
        logger.warning("require_active_task: No task_manager, cannot check tasks - allowing")
        return None

    # Query for any in_progress task in the project
    # A task being worked on anywhere in the project is sufficient to unlock editing
    try:
        project_tasks = task_manager.list_tasks(
            status="in_progress",
            limit=1,
        )

        if project_tasks:
            logger.debug(
                f"require_active_task: Found active project task '{project_tasks[0].id}', allowing"
            )
            return None

    except Exception as e:
        logger.error(f"require_active_task: Error querying tasks: {e}")
        # On error, allow to avoid blocking legitimate work
        return None

    # No active task found - block the tool
    logger.info(
        f"require_active_task: Blocking '{tool_name}' - no active task for session {session_id}"
    )

    return {
        "decision": "block",
        "reason": f"No active task found. Before using {tool_name}, please either:\n"
        f"- Create a task: call_tool(server_name='gobby-tasks', tool_name='create_task', arguments={{...}})\n"
        f"- Start an existing task: call_tool(server_name='gobby-tasks', tool_name='update_task', "
        f"arguments={{'task_id': '...', 'status': 'in_progress'}})",
        "inject_context": (
            f"**Task Required**: The `{tool_name}` tool is blocked until you have an active task.\n\n"
            f"Before modifying files, please either:\n"
            f"1. **Create a new task**: `create_task(title=\"...\", description=\"...\")`\n"
            f"2. **Start an existing task**: `update_task(task_id=\"...\", status=\"in_progress\")`\n\n"
            f"Use `list_ready_tasks()` to see available tasks, or `create_task()` to track new work."
        ),
    }
