"""
Internal MCP tools for Gobby Workflow System.

Exposes functionality for:
- get_workflow: Get details about a specific workflow definition
- list_workflows: Discover available workflow definitions
- activate_workflow: Start a step-based workflow (supports initial variables)
- end_workflow: Complete/terminate active workflow
- get_workflow_status: Get current workflow state
- request_step_transition: Request transition to a different step
- mark_artifact_complete: Register an artifact as complete
- set_variable: Set a workflow variable for the session
- get_variable: Get workflow variable(s) for the session
- import_workflow: Import a workflow from a file path
- reload_cache: Clear the workflow loader cache to pick up file changes
- close_terminal: Agent self-termination

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.workflows._artifacts import (
    get_variable,
    mark_artifact_complete,
    set_variable,
)
from gobby.mcp_proxy.tools.workflows._import import import_workflow, reload_cache
from gobby.mcp_proxy.tools.workflows._lifecycle import (
    activate_workflow,
    end_workflow,
    request_step_transition,
)
from gobby.mcp_proxy.tools.workflows._query import (
    get_workflow,
    get_workflow_status,
    list_workflows,
)
from gobby.mcp_proxy.tools.workflows._terminal import close_terminal
from gobby.storage.database import DatabaseProtocol
from gobby.storage.sessions import LocalSessionManager
from gobby.utils.project_context import get_workflow_project_path
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

__all__ = [
    "create_workflows_registry",
    "get_workflow_project_path",
]


def create_workflows_registry(
    loader: WorkflowLoader | None = None,
    state_manager: WorkflowStateManager | None = None,
    session_manager: LocalSessionManager | None = None,
    db: DatabaseProtocol | None = None,
) -> InternalToolRegistry:
    """
    Create a workflow tool registry with all workflow-related tools.

    Args:
        loader: WorkflowLoader instance
        state_manager: WorkflowStateManager instance (created from db if not provided)
        session_manager: LocalSessionManager instance (created from db if not provided)
        db: Database instance for creating default managers

    Returns:
        InternalToolRegistry with workflow tools registered

    Note:
        If db is None and state_manager/session_manager are not provided,
        tools requiring database access will return errors when called.
    """
    _db = db
    _loader = loader or WorkflowLoader()

    # Create default managers only if db is provided
    if state_manager is not None:
        _state_manager = state_manager
    elif _db is not None:
        _state_manager = WorkflowStateManager(_db)
    else:
        _state_manager = None

    if session_manager is not None:
        _session_manager = session_manager
    elif _db is not None:
        _session_manager = LocalSessionManager(_db)
    else:
        _session_manager = None

    registry = InternalToolRegistry(
        name="gobby-workflows",
        description="Workflow management - list, activate, status, transition, end",
    )

    @registry.tool(
        name="get_workflow",
        description="Get details about a specific workflow definition.",
    )
    def _get_workflow(
        name: str,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        return get_workflow(_loader, name, project_path)

    @registry.tool(
        name="list_workflows",
        description="List available workflow definitions from project and global directories.",
    )
    def _list_workflows(
        project_path: str | None = None,
        workflow_type: str | None = None,
        global_only: bool = False,
    ) -> dict[str, Any]:
        return list_workflows(_loader, project_path, workflow_type, global_only)

    @registry.tool(
        name="activate_workflow",
        description="Activate a step-based workflow for the current session. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def _activate_workflow(
        name: str,
        session_id: str | None = None,
        initial_step: str | None = None,
        variables: dict[str, Any] | None = None,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        if _state_manager is None or _session_manager is None or _db is None:
            return {"success": False, "error": "Workflow tools require database connection"}
        return activate_workflow(
            _loader,
            _state_manager,
            _session_manager,
            _db,
            name,
            session_id,
            initial_step,
            variables,
            project_path,
        )

    @registry.tool(
        name="end_workflow",
        description="End the currently active step-based workflow. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def _end_workflow(
        session_id: str | None = None,
        reason: str | None = None,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        if _state_manager is None or _session_manager is None:
            return {"success": False, "error": "Workflow tools require database connection"}
        return end_workflow(
            _loader, _state_manager, _session_manager, session_id, reason, project_path
        )

    @registry.tool(
        name="get_workflow_status",
        description="Get current workflow step and state. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def _get_workflow_status(session_id: str | None = None) -> dict[str, Any]:
        if _state_manager is None or _session_manager is None:
            return {"success": False, "error": "Workflow tools require database connection"}
        return get_workflow_status(_state_manager, _session_manager, session_id)

    @registry.tool(
        name="request_step_transition",
        description="Request transition to a different step. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def _request_step_transition(
        to_step: str,
        reason: str | None = None,
        session_id: str | None = None,
        force: bool = False,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        if _state_manager is None or _session_manager is None:
            return {"success": False, "error": "Workflow tools require database connection"}
        return request_step_transition(
            _loader,
            _state_manager,
            _session_manager,
            to_step,
            reason,
            session_id,
            force,
            project_path,
        )

    @registry.tool(
        name="mark_artifact_complete",
        description="Register an artifact as complete (plan, spec, etc.). Accepts #N, N, UUID, or prefix for session_id.",
    )
    def _mark_artifact_complete(
        artifact_type: str,
        file_path: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if _state_manager is None or _session_manager is None:
            return {"success": False, "error": "Workflow tools require database connection"}
        return mark_artifact_complete(
            _state_manager, _session_manager, artifact_type, file_path, session_id
        )

    @registry.tool(
        name="set_variable",
        description="Set a workflow variable for the current session (session-scoped, not persisted to YAML). Accepts #N, N, UUID, or prefix for session_id.",
    )
    def _set_variable(
        name: str,
        value: str | int | float | bool | None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if _state_manager is None or _session_manager is None or _db is None:
            return {"success": False, "error": "Workflow tools require database connection"}
        return set_variable(_state_manager, _session_manager, _db, name, value, session_id)

    @registry.tool(
        name="get_variable",
        description="Get workflow variable(s) for the current session. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def _get_variable(
        name: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if _state_manager is None or _session_manager is None:
            return {"success": False, "error": "Workflow tools require database connection"}
        return get_variable(_state_manager, _session_manager, name, session_id)

    @registry.tool(
        name="import_workflow",
        description="Import a workflow from a file path into the project or global directory.",
    )
    def _import_workflow(
        source_path: str,
        workflow_name: str | None = None,
        is_global: bool = False,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        return import_workflow(_loader, source_path, workflow_name, is_global, project_path)

    @registry.tool(
        name="reload_cache",
        description="Clear the workflow cache. Use this after modifying workflow YAML files.",
    )
    def _reload_cache() -> dict[str, Any]:
        return reload_cache(_loader)

    @registry.tool(
        name="close_terminal",
        description=(
            "Close the current terminal window/pane (agent self-termination). "
            "Launches ~/.gobby/scripts/agent_shutdown.sh which handles "
            "terminal-specific shutdown (tmux, iTerm, etc.). Rebuilds script if missing."
        ),
    )
    async def _close_terminal(
        signal: str = "TERM",
        delay_ms: int = 0,
    ) -> dict[str, Any]:
        return await close_terminal(signal, delay_ms)

    return registry
