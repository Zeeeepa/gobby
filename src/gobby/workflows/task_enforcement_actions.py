"""
Task enforcement actions for workflow engine.

Provides actions that enforce task tracking before allowing certain tools,
and enforce task completion before allowing agent to stop.
"""

import ast
import logging
import operator
import subprocess  # nosec B404 - subprocess needed for git commands
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.task_readiness import is_descendant_of

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig
    from gobby.storage.session_tasks import SessionTaskManager
    from gobby.storage.sessions import LocalSessionManager
    from gobby.storage.tasks import LocalTaskManager
    from gobby.workflows.definitions import WorkflowState

logger = logging.getLogger(__name__)


# =============================================================================
# Lazy Evaluation Helpers
# =============================================================================


class _LazyBool:
    """Lazy boolean that defers computation until first access.

    Used to avoid expensive operations (git status, DB queries) when
    evaluating block_tools conditions that don't reference certain values.

    The computation is triggered when the value is used in a boolean context
    (e.g., `if lazy_val:` or `not lazy_val`), which happens during eval().
    """

    __slots__ = ("_thunk", "_computed", "_value")

    def __init__(self, thunk: "Callable[[], bool]") -> None:
        self._thunk = thunk
        self._computed = False
        self._value = False

    def __bool__(self) -> bool:
        if not self._computed:
            self._value = self._thunk()
            self._computed = True
        return self._value

    def __repr__(self) -> str:
        if self._computed:
            return f"_LazyBool({self._value})"
        return "_LazyBool(<not computed>)"


# =============================================================================
# Helper Functions
# =============================================================================


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


# =============================================================================
# Safe Expression Evaluator (AST-based)
# =============================================================================


class SafeExpressionEvaluator(ast.NodeVisitor):
    """Safe expression evaluator using AST.

    Evaluates simple Python expressions without using eval().
    Supports boolean operations, comparisons, attribute access, subscripts,
    and a limited set of allowed function calls.
    """

    # Comparison operators mapping
    CMP_OPS: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
    }

    def __init__(
        self, context: dict[str, Any], allowed_funcs: dict[str, Callable[..., Any]]
    ) -> None:
        self.context = context
        self.allowed_funcs = allowed_funcs

    def evaluate(self, expr: str) -> bool:
        """Evaluate expression and return boolean result."""
        try:
            tree = ast.parse(expr, mode="eval")
            return bool(self.visit(tree.body))
        except Exception as e:
            raise ValueError(f"Invalid expression: {e}") from e

    def visit_BoolOp(self, node: ast.BoolOp) -> bool:
        """Handle 'and' / 'or' operations."""
        if isinstance(node.op, ast.And):
            return all(self.visit(v) for v in node.values)
        elif isinstance(node.op, ast.Or):
            return any(self.visit(v) for v in node.values)
        raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")

    def visit_Compare(self, node: ast.Compare) -> bool:
        """Handle comparison operations (==, !=, <, >, in, not in, etc.)."""
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            right = self.visit(comparator)
            op_func = self.CMP_OPS.get(type(op))
            if op_func is None:
                raise ValueError(f"Unsupported comparison: {type(op).__name__}")
            if not op_func(left, right):
                return False
            left = right
        return True

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        """Handle unary operations (not, -, +)."""
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not operand
        elif isinstance(node.op, ast.USub):
            return -operand
        elif isinstance(node.op, ast.UAdd):
            return +operand
        raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")

    def visit_Name(self, node: ast.Name) -> Any:
        """Handle variable names."""
        name = node.id
        # Built-in constants
        if name == "True":
            return True
        if name == "False":
            return False
        if name == "None":
            return None
        # Context variables
        if name in self.context:
            return self.context[name]
        raise ValueError(f"Unknown variable: {name}")

    def visit_Constant(self, node: ast.Constant) -> Any:
        """Handle literal values (strings, numbers, booleans, None)."""
        return node.value

    def visit_Call(self, node: ast.Call) -> Any:
        """Handle function calls (only allowed functions)."""
        # Get function name
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            # Handle method calls like tool_input.get('key')
            obj = self.visit(node.func.value)
            method_name = node.func.attr
            if method_name == "get" and isinstance(obj, dict):
                args = [self.visit(arg) for arg in node.args]
                return obj.get(*args)
            raise ValueError(f"Unsupported method call: {method_name}")
        else:
            raise ValueError(f"Unsupported call type: {type(node.func).__name__}")

        # Check if function is allowed
        if func_name not in self.allowed_funcs:
            raise ValueError(f"Function not allowed: {func_name}")

        # Evaluate arguments
        args = [self.visit(arg) for arg in node.args]
        kwargs = {kw.arg: self.visit(kw.value) for kw in node.keywords if kw.arg}

        return self.allowed_funcs[func_name](*args, **kwargs)

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        """Handle attribute access (e.g., obj.attr)."""
        obj = self.visit(node.value)
        attr = node.attr
        if isinstance(obj, dict):
            # Allow dict-style attribute access for convenience
            if attr in obj:
                return obj[attr]
            raise ValueError(f"Key not found: {attr}")
        if hasattr(obj, attr):
            return getattr(obj, attr)
        raise ValueError(f"Attribute not found: {attr}")

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        """Handle subscript access (e.g., obj['key'] or obj[0])."""
        obj = self.visit(node.value)
        key = self.visit(node.slice)
        try:
            return obj[key]
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"Subscript access failed: {e}") from e

    def generic_visit(self, node: ast.AST) -> Any:
        """Reject any unsupported AST nodes."""
        raise ValueError(f"Unsupported expression type: {type(node).__name__}")


# =============================================================================
# Block Tools Action (Unified Tool Blocking)
# =============================================================================


def _evaluate_block_condition(
    condition: str | None,
    workflow_state: "WorkflowState | None",
    event_data: dict[str, Any] | None = None,
    tool_input: dict[str, Any] | None = None,
    session_has_dirty_files: "_LazyBool | bool" = False,
    task_has_commits: "_LazyBool | bool" = False,
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
        "bool": bool,
        "str": str,
        "int": int,
    }

    try:
        evaluator = SafeExpressionEvaluator(context, allowed_funcs)
        return evaluator.evaluate(condition)
    except Exception as e:
        logger.warning(f"block_tools condition evaluation failed: '{condition}'. Error: {e}")
        return False


async def block_tools(
    rules: list[dict[str, Any]] | None = None,
    event_data: dict[str, Any] | None = None,
    workflow_state: "WorkflowState | None" = None,
    project_path: str | None = None,
    task_manager: "LocalTaskManager | None" = None,
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
        current_dirty = _get_dirty_files(project_path)
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

    # Wrap in _LazyBool so they're only computed when used in boolean context
    session_has_dirty_files: _LazyBool | bool = _LazyBool(_compute_session_has_dirty_files)
    task_has_commits: _LazyBool | bool = _LazyBool(_compute_task_has_commits)

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
                    mcp_tool_args = tool_input.get("arguments", {}) or {}

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
        logger.info(f"block_tools: Blocking '{tool_name}' - {reason[:100]}")
        return {"decision": "block", "reason": reason}

    return None


def _get_dirty_files(project_path: str | None = None) -> set[str]:
    """
    Get the set of dirty files from git status --porcelain.

    Excludes .gobby/ files from the result.

    Args:
        project_path: Path to the project directory

    Returns:
        Set of dirty file paths (relative to repo root)
    """
    if project_path is None:
        logger.warning(
            "_get_dirty_files: project_path is None, git status will use daemon's cwd "
            "which may not be the project directory"
        )

    try:
        result = subprocess.run(  # nosec B603 B607 - hardcoded git command
            ["git", "status", "--porcelain"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.warning(f"_get_dirty_files: git status failed: {result.stderr}")
            return set()

        dirty_files = set()
        # Split by newline first, don't strip() the whole string as it removes
        # the leading space from git status format (e.g., " M file.py")
        for line in result.stdout.split("\n"):
            line = line.rstrip()  # Remove trailing whitespace only
            if not line:
                continue
            # Format is "XY filename" or "XY filename -> newname" for renames
            # Skip the status prefix (first 3 chars: 2 status chars + space)
            filepath = line[3:].split(" -> ")[0]  # Handle renames
            # Exclude .gobby/ files
            if not filepath.startswith(".gobby/"):
                dirty_files.add(filepath)

        return dirty_files

    except subprocess.TimeoutExpired:
        logger.warning("_get_dirty_files: git status timed out")
        return set()
    except FileNotFoundError:
        logger.warning("_get_dirty_files: git not found")
        return set()
    except Exception as e:
        logger.error(f"_get_dirty_files: Error running git status: {e}")
        return set()


def _get_task_session_liveness(
    task_id: str,
    session_task_manager: "SessionTaskManager | None",
    session_manager: "LocalSessionManager | None",
    exclude_session_id: str | None = None,
) -> bool:
    """
    Check if a task is currently being worked on by an active session.

    Args:
        task_id: The task ID to check
        session_task_manager: Manager to look up session-task links
        session_manager: Manager to check session status
        exclude_session_id: ID of session to exclude from check (e.g. current one)

    Returns:
        True if an active session (status='active') is linked to this task.
    """
    if not session_task_manager or not session_manager:
        return False

    try:
        # Get all sessions linked to this task
        linked_sessions = session_task_manager.get_task_sessions(task_id)

        for link in linked_sessions:
            session_id = link.get("session_id")
            if not session_id or session_id == exclude_session_id:
                continue

            # Check if session is truly active
            session = session_manager.get(session_id)
            if session and session.status == "active":
                return True

        return False
    except Exception as e:
        logger.warning(f"_get_task_session_liveness: Error checking liveness for {task_id}: {e}")
        return False


async def capture_baseline_dirty_files(
    workflow_state: "WorkflowState | None",
    project_path: str | None = None,
) -> dict[str, Any] | None:
    """
    Capture current dirty files as baseline for session-aware detection.

    Called on session_start to record pre-existing dirty files. The
    require_commit_before_stop action will compare against this baseline
    to detect only NEW dirty files made during the session.

    Args:
        workflow_state: Workflow state to store baseline in
        project_path: Path to the project directory for git status check

    Returns:
        Dict with captured baseline info, or None if no workflow_state
    """
    if not workflow_state:
        logger.debug("capture_baseline_dirty_files: No workflow_state, skipping")
        return None

    dirty_files = _get_dirty_files(project_path)

    # Store as a list in workflow state (sets aren't JSON serializable)
    workflow_state.variables["baseline_dirty_files"] = list(dirty_files)

    # Log for debugging baseline capture issues
    files_preview = list(dirty_files)[:5]
    logger.info(
        f"capture_baseline_dirty_files: project_path={project_path}, "
        f"captured {len(dirty_files)} files: {files_preview}"
    )

    return {
        "baseline_captured": True,
        "file_count": len(dirty_files),
        "files": list(dirty_files),
    }


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

    # Check for uncommitted changes using baseline-aware comparison
    current_dirty = _get_dirty_files(project_path)

    if not current_dirty:
        logger.debug("require_commit_before_stop: No uncommitted changes, allowing")
        return None

    # Get baseline dirty files captured at session start
    baseline_dirty = set(workflow_state.variables.get("baseline_dirty_files", []))

    # Calculate NEW dirty files (not in baseline)
    new_dirty = current_dirty - baseline_dirty

    if not new_dirty:
        logger.debug(
            f"require_commit_before_stop: All {len(current_dirty)} dirty files were pre-existing "
            f"(in baseline), allowing"
        )
        return None

    logger.debug(
        f"require_commit_before_stop: Found {len(new_dirty)} new dirty files "
        f"(baseline had {len(baseline_dirty)}, current has {len(current_dirty)})"
    )

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
        f"has {len(new_dirty)} uncommitted changes"
    )

    # Build list of new dirty files for the message (limit to 10 for readability)
    new_dirty_list = sorted(new_dirty)[:10]
    files_display = "\n".join(f"  - {f}" for f in new_dirty_list)
    if len(new_dirty) > 10:
        files_display += f"\n  ... and {len(new_dirty) - 10} more files"

    return {
        "decision": "block",
        "reason": (
            f"Task '{claimed_task_id}' is in_progress with {len(new_dirty)} uncommitted "
            f"changes made during this session:\n{files_display}\n\n"
            f"Before stopping, commit your changes and close the task:\n"
            f"1. Commit with [{claimed_task_id}] in the message\n"
            f'2. Close the task: close_task(task_id="{claimed_task_id}", commit_sha="...")'
        ),
    }


async def require_task_review_or_close_before_stop(
    workflow_state: "WorkflowState | None",
    task_manager: "LocalTaskManager | None" = None,
    project_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Block stop if session has an in_progress task.

    Agents must close their task (or send to review) before stopping.
    The close_task() validation already requires a commit, so we don't
    need to check for uncommitted changes here - that's handled by
    require_commit_before_stop if needed.

    Checks both:
    1. claimed_task_id - task explicitly claimed via update_task(status="in_progress")
    2. session_task - task(s) assigned via set_variable (fallback if no claimed_task_id)

    Args:
        workflow_state: Workflow state with variables (claimed_task_id, etc.)
        task_manager: LocalTaskManager to verify task status
        project_id: Project ID for resolving task references (#N, N formats)
        **kwargs: Accepts additional kwargs for compatibility

    Returns:
        Dict with decision="block" and reason if task is still in_progress,
        or None to allow the stop.
    """
    if not workflow_state:
        logger.debug("require_task_review_or_close_before_stop: No workflow_state, allowing")
        return None

    # 1. Check claimed_task_id first (existing behavior)
    claimed_task_id = workflow_state.variables.get("claimed_task_id")

    # 2. If no claimed task, fall back to session_task
    if not claimed_task_id and task_manager:
        session_task = workflow_state.variables.get("session_task")
        if session_task and session_task != "*":
            # Normalize to list
            task_ids = [session_task] if isinstance(session_task, str) else session_task

            if isinstance(task_ids, list):
                for task_id in task_ids:
                    try:
                        task = task_manager.get_task(task_id, project_id=project_id)
                    except ValueError:
                        continue
                    if task and task.status == "in_progress":
                        claimed_task_id = task_id
                        logger.debug(
                            f"require_task_review_or_close_before_stop: Found in_progress "
                            f"session_task '{task_id}'"
                        )
                        break
                    # Also check subtasks
                    if task:
                        subtasks = task_manager.list_tasks(parent_task_id=task.id)
                        for subtask in subtasks:
                            if subtask.status == "in_progress":
                                claimed_task_id = subtask.id
                                logger.debug(
                                    f"require_task_review_or_close_before_stop: Found in_progress "
                                    f"subtask '{subtask.id}' under session_task '{task_id}'"
                                )
                                break
                    if claimed_task_id:
                        break

    if not claimed_task_id:
        logger.debug("require_task_review_or_close_before_stop: No claimed task, allowing")
        return None

    if not task_manager:
        logger.debug("require_task_review_or_close_before_stop: No task_manager, allowing")
        return None

    try:
        task = task_manager.get_task(claimed_task_id, project_id=project_id)
        if not task:
            # Task not found - clear stale workflow state and allow
            logger.debug(
                f"require_task_review_or_close_before_stop: Task '{claimed_task_id}' not found, "
                f"clearing state"
            )
            workflow_state.variables["claimed_task_id"] = None
            workflow_state.variables["task_claimed"] = False
            return None

        if task.status != "in_progress":
            # Task is closed or in review - allow stop
            logger.debug(
                f"require_task_review_or_close_before_stop: Task '{claimed_task_id}' "
                f"status={task.status}, allowing"
            )
            # Clear stale workflow state
            workflow_state.variables["claimed_task_id"] = None
            workflow_state.variables["task_claimed"] = False
            return None

        # Task is still in_progress - block the stop
        task_ref = f"#{task.seq_num}" if task.seq_num else task.id[:8]
        logger.info(
            f"require_task_review_or_close_before_stop: Blocking stop - task "
            f"{task_ref} is still in_progress"
        )

        return {
            "decision": "block",
            "reason": (
                f"\nTask {task_ref} is still in_progress. "
                f"Close it with close_task() before stopping."
            ),
            "task_id": claimed_task_id,
            "task_status": task.status,
        }

    except Exception as e:
        logger.warning(
            f"require_task_review_or_close_before_stop: Failed to check task status: {e}"
        )
        # Allow stop if we can't check - don't block on errors
        return None


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
    - Single task: ["#47"]
    - Multiple tasks: ["#47", "#48"]
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
            logger.info(f"require_task_complete: Task '{task_id}' needs closing")
            return {
                "decision": "block",
                "reason": (
                    f"Task '{parent_task.title}' is ready to close.\n"
                    f'close_task(task_id="{task_id}")'
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
                    f"Use suggest_next_task() to find the best task to work on next, "
                    f"and continue working without requiring confirmation from the user."
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
                        f'close_task(task_id="{claimed_task_id}")\n\n'
                        f"'{parent_task.title}' still has {len(incomplete)} incomplete subtask(s)."
                        f"{multi_task_suffix}"
                    ),
                }
            else:
                # Claimed task is not under this parent - remind about parent work
                logger.info("require_task_complete: Claimed task not under parent, redirecting")
                return {
                    "decision": "block",
                    "reason": (
                        f"'{parent_task.title}' has {len(incomplete)} incomplete subtask(s).\n\n"
                        f"Use suggest_next_task() to find the best task to work on next, "
                        f"and continue working without requiring confirmation from the user."
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
    session_manager: "LocalSessionManager | None" = None,
    session_task_manager: "SessionTaskManager | None" = None,
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
        session_manager: Optional session manager for liveness checks
        session_task_manager: Optional session-task manager for liveness checks

    Returns:
        Dict with decision="block" if no active task and tool is protected,
        or None to allow the tool.
    """
    # Check if feature is enabled
    # Precedence: workflow_state variables > config.yaml
    # (workflow_state already has step > lifecycle precedence merged)
    require_task = None

    # First check workflow state variables (step workflow > lifecycle workflow)
    if workflow_state:
        require_task = workflow_state.variables.get("require_task_before_edit")
        if require_task is not None:
            logger.debug(
                f"require_active_task: Using workflow variable require_task_before_edit={require_task}"
            )

    # Fall back to config.yaml if not set in workflow variables
    if require_task is None and config:
        require_task = config.workflow.require_task_before_edit
        logger.debug(
            f"require_active_task: Using config.yaml require_task_before_edit={require_task}"
        )

    # If still None (no config), default to False (allow)
    if require_task is None:
        logger.debug("require_active_task: No config source, allowing")
        return None

    if not require_task:
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

    # Check if this tool is protected (always from config.yaml)
    protected_tools = (
        config.workflow.protected_tools if config else ["Edit", "Write", "Update", "NotebookEdit"]
    )
    if tool_name not in protected_tools:
        logger.debug(f"require_active_task: Tool '{tool_name}' not protected, allowing")
        return None

    # Tool is protected - but check for plan mode exceptions first

    # Check if target is a Claude Code plan file (stored in ~/.claude/plans/)
    # This allows writes during plan mode without requiring a task
    tool_input = event_data.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "")
    if file_path and "/.claude/plans/" in file_path:
        logger.debug(f"require_active_task: Target is Claude plan file '{file_path}', allowing")
        return None

    # Check for plan_mode variable (set via EnterPlanMode tool detection or manually)
    if workflow_state and workflow_state.variables.get("plan_mode"):
        logger.debug(f"require_active_task: plan_mode=True in session {session_id}, allowing")
        return None

    # Check for active task

    # Session-scoped check: task_claimed variable (set by AFTER_TOOL detection)
    # This is the primary enforcement - each session must explicitly claim a task
    if workflow_state and workflow_state.variables.get("task_claimed"):
        logger.debug(f"require_active_task: task_claimed=True in session {session_id}, allowing")
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
                task = project_tasks[0]
                task_ref = f"#{task.seq_num}" if task.seq_num else task.id
                project_task_hint = (
                    f"\n\nNote: Task {task_ref} ({task.title}) "
                    f"is in_progress but wasn't claimed by this session. "
                    f'Use `update_task(task_id="{task.id}", status="in_progress")` '
                    f"to claim it for this session."
                )
                logger.debug(
                    f"require_active_task: Found project task {task_ref} but "
                    f"session hasn't claimed it"
                )

                # Check liveness of the candidate task
                is_live = _get_task_session_liveness(
                    task.id, session_task_manager, session_manager, exclude_session_id=session_id
                )

                if is_live:
                    project_task_hint = (
                        f"\n\nNote: Task {task_ref} ({task.title}) "
                        f"is in_progress, but it is **currently being worked on by another active session**. "
                        f"You should probably create a new task or subtask instead of interfering."
                    )
                else:
                    project_task_hint = (
                        f"\n\nNote: Task {task_ref} ({task.title}) "
                        f"is in_progress and appears unattended (no active session). "
                        f"If you are picking up this work, claim it: "
                        f'`update_task(task_id="{task.id}", status="in_progress")`.'
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
            "reason": (
                "No task claimed. See previous **Task Required** error for instructions.\n"
                "See skill: **claiming-tasks** for help."
            ),
            "inject_context": (
                f"**Task Required**: `{tool_name}` blocked. "
                f"Create or claim a task before editing files (see previous error for details).\n"
                f'For detailed guidance: `get_skill(name="claiming-tasks")`'
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
            f"{project_task_hint}\n\n"
            f"See skill: **claiming-tasks** for detailed guidance."
        ),
        "inject_context": (
            f"**Task Required**: The `{tool_name}` tool is blocked until you claim a task for this session.\n\n"
            f"Each session must explicitly create or claim a task before modifying files:\n"
            f'1. **Create a new task**: `create_task(title="...", description="...")`\n'
            f'2. **Claim an existing task**: `update_task(task_id="...", status="in_progress")`\n\n'
            f"Use `list_ready_tasks()` to see available tasks."
            f"{project_task_hint}\n\n"
            f'For detailed guidance: `get_skill(name="claiming-tasks")`'
        ),
    }


async def validate_session_task_scope(
    task_manager: "LocalTaskManager | None",
    workflow_state: "WorkflowState | None",
    event_data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Block claiming a task that is not a descendant of session_task.

    This action is designed for on_before_tool triggers on update_task
    to enforce that agents only work on tasks within the session_task hierarchy.

    When session_task is set in workflow state, this action checks if the task
    being claimed (set to in_progress) is a descendant of session_task.

    Args:
        task_manager: LocalTaskManager for querying tasks
        workflow_state: Workflow state with session_task variable
        event_data: Hook event data containing tool_name and tool_input

    Returns:
        Dict with decision="block" if task is outside session_task scope,
        or None to allow the claim.
    """
    if not workflow_state:
        logger.debug("validate_session_task_scope: No workflow_state, allowing")
        return None

    if not task_manager:
        logger.debug("validate_session_task_scope: No task_manager, allowing")
        return None

    # Get session_task from workflow state
    session_task = workflow_state.variables.get("session_task")
    if not session_task:
        logger.debug("validate_session_task_scope: No session_task set, allowing")
        return None

    # Handle "*" wildcard - means all tasks are in scope
    if session_task == "*":
        logger.debug("validate_session_task_scope: session_task='*', allowing all tasks")
        return None

    # Normalize to list for uniform handling
    # session_task can be: string (single ID), list of IDs, or "*"
    if isinstance(session_task, str):
        session_task_ids = [session_task]
    elif isinstance(session_task, list):
        session_task_ids = session_task
    else:
        logger.warning(
            f"validate_session_task_scope: Invalid session_task type: {type(session_task)}"
        )
        return None

    # Empty list means no scope restriction
    if not session_task_ids:
        logger.debug("validate_session_task_scope: Empty session_task list, allowing")
        return None

    # Check if this is an update_task call setting status to in_progress
    if not event_data:
        logger.debug("validate_session_task_scope: No event_data, allowing")
        return None

    tool_name = event_data.get("tool_name")
    if tool_name != "update_task":
        logger.debug(f"validate_session_task_scope: Tool '{tool_name}' not update_task, allowing")
        return None

    tool_input = event_data.get("tool_input", {})
    arguments = tool_input.get("arguments", {}) or {}

    # Only check when setting status to in_progress (claiming)
    new_status = arguments.get("status")
    if new_status != "in_progress":
        logger.debug(
            f"validate_session_task_scope: Status '{new_status}' not in_progress, allowing"
        )
        return None

    task_id = arguments.get("task_id")
    if not task_id:
        logger.debug("validate_session_task_scope: No task_id in arguments, allowing")
        return None

    # Check if task is a descendant of ANY session_task
    for ancestor_id in session_task_ids:
        if is_descendant_of(task_manager, task_id, ancestor_id):
            logger.debug(
                f"validate_session_task_scope: Task '{task_id}' is descendant of "
                f"session_task '{ancestor_id}', allowing"
            )
            return None

    # Task is outside all session_task scopes - block
    logger.info(
        f"validate_session_task_scope: Blocking claim of task '{task_id}' - "
        f"not a descendant of any session_task: {session_task_ids}"
    )

    # Build error message with scope details
    if len(session_task_ids) == 1:
        session_task_obj = task_manager.get_task(session_task_ids[0])
        scope_desc = (
            f"'{session_task_obj.title}' ({session_task_ids[0]})"
            if session_task_obj
            else session_task_ids[0]
        )
        suggestion = f'Use `suggest_next_task(parent_id="{session_task_ids[0]}")` to find tasks within scope.'
    else:
        scope_desc = ", ".join(session_task_ids)
        suggestion = "Use `suggest_next_task()` with one of the scoped parent IDs to find tasks within scope."

    return {
        "decision": "block",
        "reason": (
            f"Cannot claim task '{task_id}' - it is not within the session_task scope.\n\n"
            f"This session is scoped to: {scope_desc}\n"
            f"Only tasks that are descendants of these epics/features can be claimed.\n\n"
            f"{suggestion}"
        ),
    }


# --- ActionHandler-compatible wrappers ---
# These match the ActionHandler protocol: (context: ActionContext, **kwargs) -> dict | None
# Note: Some handlers require executor access (task_manager) which must be passed
# via closures in register_defaults.


async def handle_capture_baseline_dirty_files(
    context: "Any",
    task_manager: "LocalTaskManager | None" = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for capture_baseline_dirty_files.

    Note: project_path comes from session's project lookup or event_data.cwd.
    """
    from gobby.storage.projects import LocalProjectManager

    # Get project path - prioritize session lookup over hook payload
    project_path = None

    # 1. Get from session's project (most reliable - session exists by now)
    if context.session_id and context.session_manager:
        session = context.session_manager.get(context.session_id)
        if session and session.project_id:
            project_mgr = LocalProjectManager(context.db)
            project = project_mgr.get(session.project_id)
            if project and project.repo_path:
                project_path = project.repo_path

    # 2. Fallback to event_data.cwd (from hook payload)
    if not project_path and context.event_data:
        project_path = context.event_data.get("cwd")

    return await capture_baseline_dirty_files(
        workflow_state=context.state,
        project_path=project_path,
    )


async def handle_require_commit_before_stop(
    context: "Any",
    task_manager: "LocalTaskManager | None" = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for require_commit_before_stop.

    Note: task_manager must be passed via closure from executor.
    """
    from gobby.storage.projects import LocalProjectManager

    # Get project path
    project_path = None

    if context.session_id and context.session_manager:
        session = context.session_manager.get(context.session_id)
        if session and session.project_id:
            project_mgr = LocalProjectManager(context.db)
            project = project_mgr.get(session.project_id)
            if project and project.repo_path:
                project_path = project.repo_path

    if not project_path and context.event_data:
        project_path = context.event_data.get("cwd")

    return await require_commit_before_stop(
        workflow_state=context.state,
        project_path=project_path,
        task_manager=task_manager,
    )


async def handle_require_task_review_or_close_before_stop(
    context: "Any",
    task_manager: "LocalTaskManager | None" = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for require_task_review_or_close_before_stop."""
    project_id = None
    if context.session_manager:
        session = context.session_manager.get(context.session_id)
        if session:
            project_id = session.project_id

    return await require_task_review_or_close_before_stop(
        workflow_state=context.state,
        task_manager=task_manager,
        project_id=project_id,
    )


async def handle_validate_session_task_scope(
    context: "Any",
    task_manager: "LocalTaskManager | None" = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for validate_session_task_scope."""
    return await validate_session_task_scope(
        task_manager=task_manager,
        workflow_state=context.state,
        event_data=context.event_data,
    )


async def handle_block_tools(
    context: "Any",
    task_manager: "LocalTaskManager | None" = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for block_tools.

    Passes task_manager via closure from register_defaults.
    """
    # Get project_path for git dirty file checks
    project_path = kwargs.get("project_path")
    if not project_path and context.event_data:
        project_path = context.event_data.get("cwd")

    # Get source from session for is_plan_file checks
    source = None
    if context.session_manager and context.session_id:
        current_session = context.session_manager.get(context.session_id)
        if current_session:
            source = current_session.source

    return await block_tools(
        rules=kwargs.get("rules"),
        event_data=context.event_data,
        workflow_state=context.state,
        project_path=project_path,
        task_manager=task_manager,
        source=source,
    )


async def handle_require_active_task(
    context: "Any",
    task_manager: "LocalTaskManager | None" = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for require_active_task.

    DEPRECATED: Use block_tools action with rules instead.
    Kept for backward compatibility with existing workflows.
    """
    # Get project_id from session for project-scoped task filtering
    current_session = context.session_manager.get(context.session_id)
    project_id = current_session.project_id if current_session else None

    return await require_active_task(
        task_manager=task_manager,
        session_id=context.session_id,
        config=context.config,
        event_data=context.event_data,
        project_id=project_id,
        workflow_state=context.state,
        session_manager=context.session_manager,
        session_task_manager=context.session_task_manager,
    )


async def handle_require_task_complete(
    context: "Any",
    task_manager: "LocalTaskManager | None" = None,
    template_engine: "Any | None" = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for require_task_complete.

    Supports:
    - Single task ID: "#47"
    - List of task IDs: ["#47", "#48"]
    - Wildcard: "*" - work until no ready tasks remain
    """
    project_id = None
    if context.session_manager and context.session_id:
        current_session = context.session_manager.get(context.session_id)
        if current_session:
            project_id = current_session.project_id

    # Get task_id from kwargs - may be a template that needs resolving
    task_spec = kwargs.get("task_id")

    # If it's a template reference like "{{ variables.session_task }}", resolve it
    if task_spec and "{{" in str(task_spec) and template_engine:
        task_spec = template_engine.render(
            str(task_spec),
            {"variables": context.state.variables or {}},
        )

    # Handle different task_spec types:
    # - None/empty: no enforcement
    # - "*": wildcard - fetch ready tasks
    # - list: multiple specific tasks
    # - string: single task ID
    task_ids: list[str] | None = None

    if not task_spec:
        return None
    elif task_spec == "*":
        # Wildcard: get all ready tasks for this project
        if task_manager:
            ready_tasks = task_manager.list_ready_tasks(
                project_id=project_id,
                limit=100,
            )
            task_ids = [t.id for t in ready_tasks]
            if not task_ids:
                # No ready tasks - allow stop
                return None
    elif isinstance(task_spec, list):
        task_ids = task_spec
    else:
        task_ids = [str(task_spec)]

    return await require_task_complete(
        task_manager=task_manager,
        session_id=context.session_id,
        task_ids=task_ids,
        event_data=context.event_data,
        project_id=project_id,
        workflow_state=context.state,
    )
