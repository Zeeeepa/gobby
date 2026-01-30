"""Tool blocking enforcement for workflow engine.

Provides configurable tool blocking based on workflow state and conditions.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.workflows.git_utils import get_dirty_files
from gobby.workflows.safe_evaluator import LazyBool, SafeExpressionEvaluator
from gobby.workflows.templates import TemplateEngine

if TYPE_CHECKING:
    from gobby.storage.tasks import LocalTaskManager
    from gobby.workflows.definitions import WorkflowState

logger = logging.getLogger(__name__)

# MCP discovery tools that don't require prior schema lookup
DISCOVERY_TOOLS = {
    "list_mcp_servers",
    "list_tools",
    "get_tool_schema",
    "search_tools",
    "recommend_tools",
    "list_skills",
    "get_skill",
    "search_skills",
}


def is_discovery_tool(tool_name: str | None) -> bool:
    """Check if the tool is a discovery/introspection tool.

    These tools are allowed without prior schema lookup since they ARE
    the discovery mechanism.

    Args:
        tool_name: The MCP tool name (from tool_input.tool_name)

    Returns:
        True if this is a discovery tool that doesn't need schema unlock
    """
    return tool_name in DISCOVERY_TOOLS if tool_name else False


def is_tool_unlocked(
    tool_input: dict[str, Any],
    variables: dict[str, Any],
) -> bool:
    """Check if a tool has been unlocked via prior get_tool_schema call.

    Args:
        tool_input: The tool input containing server_name and tool_name
        variables: Workflow state variables containing unlocked_tools list

    Returns:
        True if the server:tool combo was previously unlocked via get_tool_schema
    """
    server = tool_input.get("server_name", "")
    tool = tool_input.get("tool_name", "")
    if not server or not tool:
        return False
    key = f"{server}:{tool}"
    unlocked = variables.get("unlocked_tools", [])
    return key in unlocked


def track_schema_lookup(
    tool_input: dict[str, Any],
    workflow_state: WorkflowState | None,
) -> dict[str, Any] | None:
    """Track a successful get_tool_schema call by adding to unlocked_tools.

    Called from on_after_tool when tool_name is get_tool_schema and succeeded.

    Args:
        tool_input: The tool input containing server_name and tool_name
        workflow_state: Workflow state to update

    Returns:
        Dict with tracking result or None
    """
    if not workflow_state:
        return None

    server = tool_input.get("server_name", "")
    tool = tool_input.get("tool_name", "")
    if not server or not tool:
        return None

    key = f"{server}:{tool}"
    unlocked = workflow_state.variables.setdefault("unlocked_tools", [])

    if key not in unlocked:
        unlocked.append(key)
        logger.debug(f"Unlocked tool schema: {key}")
        return {"unlocked": key, "total_unlocked": len(unlocked)}

    return {"already_unlocked": key}


def _is_plan_file(file_path: str, source: str | None = None) -> bool:
    """Check if file path is a Claude Code plan file (platform-agnostic).

    Only exempts plan files for Claude Code sessions to avoid accidental
    exemptions for Gemini/Codex users.

    The pattern `/.claude/plans/` matches paths like:
    - Unix: /Users/xxx/.claude/plans/file.md  (the / comes from xxx/)
    - Windows: C:/Users/xxx/.claude/plans/file.md  (after normalization)

    Args:
        file_path: The file path being edited
        source: CLI source (e.g., "claude", "gemini", "codex")

    Returns:
        True if this is a CC plan file that should be exempt from task requirement
    """
    if not file_path:
        return False
    # Only exempt for Claude Code sessions
    if source != "claude":
        return False
    # Normalize path separators (Windows backslash to forward slash)
    normalized = file_path.replace("\\", "/")
    return "/.claude/plans/" in normalized


def _evaluate_block_condition(
    condition: str | None,
    workflow_state: WorkflowState | None,
    event_data: dict[str, Any] | None = None,
    tool_input: dict[str, Any] | None = None,
    session_has_dirty_files: LazyBool | bool = False,
    task_has_commits: LazyBool | bool = False,
    source: str | None = None,
) -> bool:
    """
    Evaluate a blocking rule condition against workflow state.

    Supports simple Python expressions with access to:
    - variables: workflow state variables dict
    - task_claimed: shorthand for variables.get('task_claimed')
    - plan_mode: shorthand for variables.get('plan_mode')
    - tool_input: the tool's input arguments (for MCP tool checks)
    - session_has_dirty_files: whether session has NEW dirty files (beyond baseline)
    - task_has_commits: whether the current task has linked commits
    - source: CLI source (e.g., "claude", "gemini", "codex")

    Args:
        condition: Python expression to evaluate
        workflow_state: Current workflow state
        event_data: Optional hook event data
        tool_input: Tool input arguments (for MCP tools, this is the 'arguments' field)
        session_has_dirty_files: Whether session has dirty files beyond baseline (lazy or bool)
        task_has_commits: Whether claimed task has linked commits (lazy or bool)
        source: CLI source identifier

    Returns:
        True if condition matches (tool should be blocked), False otherwise.
    """
    if not condition:
        return True  # No condition means always match

    # Build evaluation context
    variables = workflow_state.variables if workflow_state else {}
    context = {
        "variables": variables,
        "task_claimed": variables.get("task_claimed", False),
        "plan_mode": variables.get("plan_mode", False),
        "event": event_data or {},
        "tool_input": tool_input or {},
        "session_has_dirty_files": session_has_dirty_files,
        "task_has_commits": task_has_commits,
        "source": source or "",
    }

    # Allowed functions for safe evaluation
    allowed_funcs: dict[str, Callable[..., Any]] = {
        "is_plan_file": _is_plan_file,
        "is_discovery_tool": is_discovery_tool,
        "is_tool_unlocked": lambda ti: is_tool_unlocked(ti, variables),
        "bool": bool,
        "str": str,
        "int": int,
    }

    try:
        evaluator = SafeExpressionEvaluator(context, allowed_funcs)
        return evaluator.evaluate(condition)
    except Exception as e:
        # Fail-closed: block the tool if condition evaluation fails to prevent bypass
        logger.error(
            f"block_tools condition evaluation failed (blocking tool): condition='{condition}', "
            f"variables={variables}, error={e}",
            exc_info=True,
        )
        return True


async def block_tools(
    rules: list[dict[str, Any]] | None = None,
    event_data: dict[str, Any] | None = None,
    workflow_state: WorkflowState | None = None,
    project_path: str | None = None,
    task_manager: LocalTaskManager | None = None,
    source: str | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """
    Unified tool blocking with multiple configurable rules.

    Each rule can specify:
      - tools: List of tool names to block (for native CC tools)
      - mcp_tools: List of "server:tool" patterns to block (for MCP tools)
      - when: Optional condition (evaluated against workflow state)
      - reason: Block message to display

    For MCP tools, the tool_name in event_data is "call_tool" or "mcp__gobby__call_tool",
    and we look inside tool_input for server_name and tool_name.

    Condition evaluation has access to:
      - variables: workflow state variables
      - task_claimed, plan_mode: shortcuts
      - tool_input: the MCP tool's arguments (for checking commit_sha etc.)
      - session_has_dirty_files: whether session has NEW dirty files beyond baseline
      - task_has_commits: whether the claimed task has linked commits
      - source: CLI source (e.g., "claude", "gemini", "codex")

    Args:
        rules: List of blocking rules
        event_data: Hook event data with tool_name, tool_input
        workflow_state: For evaluating conditions
        project_path: Path to project for git status checks
        task_manager: For checking task commit status
        source: CLI source identifier (for is_plan_file checks)

    Returns:
        Dict with decision="block" and reason if blocked, None to allow.

    Example rule (native tools):
        {
            "tools": ["TaskCreate", "TaskUpdate"],
            "reason": "CC native task tools are disabled. Use gobby-tasks MCP tools."
        }

    Example rule with condition:
        {
            "tools": ["Edit", "Write", "NotebookEdit"],
            "when": "not task_claimed and not plan_mode",
            "reason": "Claim a task before using Edit, Write, or NotebookEdit tools."
        }

    Example rule (MCP tools):
        {
            "mcp_tools": ["gobby-tasks:close_task"],
            "when": "not task_has_commits and not tool_input.get('commit_sha')",
            "reason": "A commit is required before closing this task."
        }
    """
    if not event_data or not rules:
        return None

    tool_name = event_data.get("tool_name")
    if not tool_name:
        return None

    tool_input = event_data.get("tool_input", {}) or {}

    # Create lazy thunks for expensive context values (git status, DB queries).
    # These are only evaluated when actually referenced in a rule condition.

    def _compute_session_has_dirty_files() -> bool:
        """Lazy thunk: check for new dirty files beyond baseline."""
        if not workflow_state:
            return False
        if project_path is None:
            # Can't compute without project_path - avoid running git in wrong directory
            logger.debug("_compute_session_has_dirty_files: project_path is None, returning False")
            return False
        baseline_dirty = set(workflow_state.variables.get("baseline_dirty_files", []))
        current_dirty = get_dirty_files(project_path)
        new_dirty = current_dirty - baseline_dirty
        return len(new_dirty) > 0

    def _compute_task_has_commits() -> bool:
        """Lazy thunk: check if claimed task has linked commits."""
        if not workflow_state or not task_manager:
            return False
        claimed_task_id = workflow_state.variables.get("claimed_task_id")
        if not claimed_task_id:
            return False
        try:
            task = task_manager.get_task(claimed_task_id)
            return bool(task and task.commits)
        except Exception:
            return False  # nosec B110 - best-effort check

    # Wrap in LazyBool so they're only computed when used in boolean context
    session_has_dirty_files: LazyBool | bool = LazyBool(_compute_session_has_dirty_files)
    task_has_commits: LazyBool | bool = LazyBool(_compute_task_has_commits)

    for rule in rules:
        # Determine if this rule matches the current tool
        rule_matches = False
        mcp_tool_args: dict[str, Any] = {}

        # Check native CC tools (Edit, Write, etc.)
        if "tools" in rule:
            tools = rule.get("tools", [])
            if tool_name in tools:
                rule_matches = True

        # Check MCP tools (server:tool format)
        elif "mcp_tools" in rule:
            # MCP calls come in as "call_tool" or "mcp__gobby__call_tool"
            if tool_name in ("call_tool", "mcp__gobby__call_tool"):
                mcp_server = tool_input.get("server_name", "")
                mcp_tool = tool_input.get("tool_name", "")
                mcp_key = f"{mcp_server}:{mcp_tool}"

                mcp_tools = rule.get("mcp_tools", [])
                if mcp_key in mcp_tools:
                    rule_matches = True
                    # For MCP tools, the actual arguments are in tool_input.arguments
                    # Arguments may be a JSON string (Claude Code serialization) or dict
                    raw_args = tool_input.get("arguments")
                    if isinstance(raw_args, str):
                        try:
                            parsed = json.loads(raw_args)
                            mcp_tool_args = parsed if isinstance(parsed, dict) else {}
                        except (json.JSONDecodeError, TypeError):
                            mcp_tool_args = {}
                    elif isinstance(raw_args, dict):
                        mcp_tool_args = raw_args
                    else:
                        mcp_tool_args = {}

        if not rule_matches:
            continue

        # Check optional condition
        condition = rule.get("when")
        if condition:
            # For MCP tools, use the nested arguments for condition evaluation
            eval_tool_input = mcp_tool_args if mcp_tool_args else tool_input
            if not _evaluate_block_condition(
                condition,
                workflow_state,
                event_data,
                tool_input=eval_tool_input,
                session_has_dirty_files=session_has_dirty_files,
                task_has_commits=task_has_commits,
                source=source,
            ):
                continue

        reason = rule.get("reason", f"Tool '{tool_name}' is blocked.")

        # Render Jinja2 template variables in reason message
        if "{{" in reason:
            try:
                engine = TemplateEngine()
                reason = engine.render(reason, {"tool_input": tool_input})
            except Exception as e:
                logger.warning(f"Failed to render reason template: {e}")
                # Keep original reason on failure

        logger.info(f"block_tools: Blocking '{tool_name}' - {reason[:100]}")
        return {"decision": "block", "reason": reason}

    return None
