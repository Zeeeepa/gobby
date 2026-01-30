"""
Detection helper functions for workflow engine.

Extracted from engine.py to reduce complexity.
These functions detect specific events (task claims, plan mode, MCP calls)
and update workflow state variables accordingly.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.hooks.events import HookEvent
    from gobby.storage.tasks import LocalTaskManager
    from gobby.tasks.session_tasks import SessionTaskManager

    from .definitions import WorkflowState

logger = logging.getLogger(__name__)


def detect_task_claim(
    event: "HookEvent",
    state: "WorkflowState",
    session_task_manager: "SessionTaskManager | None" = None,
    task_manager: "LocalTaskManager | None" = None,
) -> None:
    """Detect gobby-tasks calls that claim or release a task for this session.

    Sets `task_claimed: true` in workflow state variables when the agent
    successfully creates a task or updates a task to in_progress status.

    Clears `task_claimed: false` when the agent closes a task, requiring
    them to claim another task before making further file modifications.

    This enables session-scoped task enforcement where each session must
    explicitly claim a task rather than free-riding on project-wide checks.

    Args:
        event: The AFTER_TOOL hook event
        state: Current workflow state (modified in place)
        session_task_manager: Optional manager for auto-linking tasks to sessions
    """
    if not event.data:
        return

    tool_input = event.data.get("tool_input", {}) or {}
    # Use normalized tool_output (adapters normalize tool_result/tool_response)
    tool_output = event.data.get("tool_output") or {}

    # Use normalized MCP fields from adapter layer
    # Adapters extract these from CLI-specific formats
    server_name = event.data.get("mcp_server", "")
    if server_name != "gobby-tasks":
        return

    inner_tool_name = event.data.get("mcp_tool", "")

    # Handle close_task - clears task_claimed when task is closed
    # Note: Claude Code doesn't include tool_result in post-tool-use hooks, so for CC
    # the workflow state is updated directly in the MCP proxy's close_task function.
    # This detection provides a fallback for CLIs that do report tool results (Gemini/Codex).
    if inner_tool_name == "close_task":
        # tool_output already normalized at top of function

        # If no tool output, skip - can't verify success
        # The MCP proxy's close_task handles state clearing for successful closes
        if not tool_output:
            return

        # Check if close succeeded (not an error)
        if isinstance(tool_output, dict):
            if tool_output.get("error") or tool_output.get("status") == "error":
                return
            result = tool_output.get("result", {})
            if isinstance(result, dict) and result.get("error"):
                return

        # Clear task_claimed on successful close
        state.variables["task_claimed"] = False
        state.variables["claimed_task_id"] = None
        logger.info(f"Session {state.session_id}: task_claimed=False (detected close_task success)")
        return

    if inner_tool_name not in ("create_task", "update_task", "claim_task"):
        return

    # For update_task, only count if status is being set to in_progress
    if inner_tool_name == "update_task":
        arguments = tool_input.get("arguments", {}) or {}
        if arguments.get("status") != "in_progress":
            return
    # claim_task always counts (it sets status to in_progress internally)

    # Check if the call succeeded (not an error) - for non-close_task operations
    # tool_output structure varies, but errors typically have "error" key
    # or the MCP response has "status": "error"
    if isinstance(tool_output, dict):
        if tool_output.get("error") or tool_output.get("status") == "error":
            return
        # Also check nested result for MCP proxy responses
        result = tool_output.get("result", {})
        if isinstance(result, dict) and result.get("error"):
            return

    # Extract task_id based on tool type
    arguments = tool_input.get("arguments", {}) or {}
    if inner_tool_name in ("update_task", "claim_task"):
        task_id = arguments.get("task_id")
        # Resolve to UUID for consistent comparison with close_task
        if task_id and task_manager:
            try:
                task = task_manager.get_task(task_id)
                if task:
                    task_id = task.id  # Use UUID
            except Exception:  # nosec B110 - best effort resolution, keep original if fails
                pass
    elif inner_tool_name == "create_task":
        # For create_task, the id is in the result
        result = tool_output.get("result", {}) if isinstance(tool_output, dict) else {}
        task_id = result.get("id") if isinstance(result, dict) else None
        # Skip if we can't get the task ID (e.g., Claude Code doesn't include tool results)
        # The MCP tool itself handles state updates in this case via _crud.py
        if not task_id:
            return
    else:
        task_id = None

    # All conditions met - set task_claimed and claimed_task_id
    state.variables["task_claimed"] = True
    state.variables["claimed_task_id"] = task_id
    logger.info(
        f"Session {state.session_id}: task_claimed=True, claimed_task_id={task_id} "
        f"(via {inner_tool_name})"
    )

    # Auto-link task to session when claiming a task
    if inner_tool_name in ("update_task", "claim_task"):
        arguments = tool_input.get("arguments", {}) or {}
        task_id = arguments.get("task_id")
        if task_id and session_task_manager:
            try:
                session_task_manager.link_task(state.session_id, task_id, "worked_on")
                logger.info(f"Auto-linked task {task_id} to session {state.session_id}")
            except Exception as e:
                logger.warning(f"Failed to auto-link task {task_id}: {e}")


def detect_plan_mode(event: "HookEvent", state: "WorkflowState") -> None:
    """Detect Claude Code plan mode entry/exit and set workflow variable.

    Sets `plan_mode: true` when EnterPlanMode tool is called, allowing
    file modifications without an active task (planning writes to plan files).

    Clears `plan_mode: false` when ExitPlanMode tool is called, re-enabling
    task enforcement for actual implementation work.

    Args:
        event: The AFTER_TOOL hook event
        state: Current workflow state (modified in place)
    """
    if not event.data:
        return

    tool_name = event.data.get("tool_name", "")

    if tool_name == "EnterPlanMode":
        state.variables["plan_mode"] = True
        logger.info(f"Session {state.session_id}: plan_mode=True (entered plan mode)")
    elif tool_name == "ExitPlanMode":
        state.variables["plan_mode"] = False
        logger.info(f"Session {state.session_id}: plan_mode=False (exited plan mode)")


def detect_plan_mode_from_context(event: "HookEvent", state: "WorkflowState") -> None:
    """Detect plan mode from system reminders injected by Claude Code.

    Claude Code injects system reminders like "Plan mode is active" when the user
    enters plan mode via the UI (not via the EnterPlanMode tool). This function
    detects those reminders and sets the plan_mode variable accordingly.

    IMPORTANT: Only matches indicators within <system-reminder> tags to avoid
    false positives from handoff context or user messages that mention plan mode.

    This complements detect_plan_mode() which only catches programmatic tool calls.

    Args:
        event: The BEFORE_AGENT hook event (contains user prompt with system reminders)
        state: Current workflow state (modified in place)
    """
    if not event.data:
        return

    # Check for plan mode system reminder in the prompt
    prompt = event.data.get("prompt", "") or ""

    # Extract only content within <system-reminder> tags to avoid false positives
    # from handoff context or user messages mentioning plan mode
    import re

    system_reminders = re.findall(r"<system-reminder>(.*?)</system-reminder>", prompt, re.DOTALL)
    reminder_text = " ".join(system_reminders)

    # Claude Code injects these phrases in system reminders when plan mode is active
    plan_mode_indicators = [
        "Plan mode is active",
        "Plan mode still active",
        "You are in plan mode",
    ]

    # Check if plan mode is indicated in system reminders only
    for indicator in plan_mode_indicators:
        if indicator in reminder_text:
            if not state.variables.get("plan_mode"):
                state.variables["plan_mode"] = True
                logger.info(
                    f"Session {state.session_id}: plan_mode=True "
                    f"(detected from system reminder: '{indicator}')"
                )
            return

    # Detect exit from plan mode (also only in system reminders)
    exit_indicators = [
        "Exited Plan Mode",
        "Plan mode exited",
    ]

    for indicator in exit_indicators:
        if indicator in reminder_text:
            if state.variables.get("plan_mode"):
                state.variables["plan_mode"] = False
                logger.info(
                    f"Session {state.session_id}: plan_mode=False "
                    f"(detected from system reminder: '{indicator}')"
                )
            return


def detect_mcp_call(event: "HookEvent", state: "WorkflowState") -> None:
    """Track MCP tool calls by server/tool for workflow conditions.

    Sets state.variables["mcp_calls"] = {
        "gobby-memory": ["recall", "remember"],
        "context7": ["get-library-docs"],
        ...
    }

    This enables workflow conditions like:
        when: "mcp_called('gobby-memory', 'recall')"

    Uses normalized fields from adapters:
    - mcp_server: The MCP server name (normalized from both Claude and Gemini formats)
    - mcp_tool: The tool name on the server (normalized from both formats)
    - tool_output: The tool result (normalized from tool_result/tool_response)

    Args:
        event: The AFTER_TOOL hook event
        state: Current workflow state (modified in place)
    """
    if not event.data:
        return

    # Use normalized fields from adapter layer
    # Adapters extract these from CLI-specific formats:
    # - Claude: tool_input.server_name/tool_name → mcp_server/mcp_tool
    # - Gemini: mcp_context.server_name/tool_name → mcp_server/mcp_tool
    server_name = event.data.get("mcp_server", "")
    inner_tool = event.data.get("mcp_tool", "")

    if not server_name or not inner_tool:
        return

    # Use normalized tool_output (adapters normalize tool_result/tool_response)
    tool_output = event.data.get("tool_output") or {}

    _track_mcp_call(state, server_name, inner_tool, tool_output)


def _track_mcp_call(
    state: "WorkflowState",
    server_name: str,
    inner_tool: str,
    tool_output: dict[str, Any] | Any,
) -> None:
    """Track a successful MCP call in workflow state.

    Args:
        state: Current workflow state (modified in place)
        server_name: MCP server name (e.g., "gobby-sessions")
        inner_tool: Tool name on the server (e.g., "get_current_session")
        tool_output: Tool output to check for errors
    """
    # Check if call succeeded (skip tracking failed calls)
    if isinstance(tool_output, dict):
        if tool_output.get("error") or tool_output.get("status") == "error":
            return
        result = tool_output.get("result", {})
        if isinstance(result, dict) and result.get("error"):
            return

    # Track the call
    mcp_calls = state.variables.setdefault("mcp_calls", {})
    server_calls = mcp_calls.setdefault(server_name, [])
    if inner_tool not in server_calls:
        server_calls.append(inner_tool)
        logger.debug(f"Session {state.session_id}: MCP call tracked {server_name}/{inner_tool}")
