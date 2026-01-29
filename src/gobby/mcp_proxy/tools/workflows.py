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
- get_workflow_status: Get current workflow state
- request_step_transition: Request transition to a different step
- mark_artifact_complete: Register an artifact as complete
- set_variable: Set a workflow variable for the session
- get_variable: Get workflow variable(s) for the session
- import_workflow: Import a workflow from a file path
- reload_cache: Clear the workflow loader cache to pick up file changes

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.database import LocalDatabase
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.tasks._id import resolve_task_reference
from gobby.storage.tasks._models import TaskNotFoundError
from gobby.utils.project_context import get_workflow_project_path
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

logger = logging.getLogger(__name__)


def _resolve_session_task_value(
    value: str,
    session_id: str | None,
    session_manager: LocalSessionManager,
    db: LocalDatabase,
) -> str:
    """
    Resolve a session_task value from seq_num reference (#N or N) to UUID.

    This prevents repeated resolution failures in condition evaluation when
    task_tree_complete() is called with a seq_num that requires project_id.

    Args:
        value: The value to potentially resolve (e.g., "#4424", "47", or a UUID)
        session_id: Session ID to look up project_id
        session_manager: Session manager for lookups
        db: Database for task resolution

    Returns:
        Resolved UUID if value was a seq_num reference, otherwise original value
    """
    # Only process string values that look like seq_num references
    if not isinstance(value, str):
        return value

    # Check if it's a seq_num reference (#N or plain N)
    is_seq_ref = value.startswith("#") or value.isdigit()
    if not is_seq_ref:
        return value

    # Need session to get project_id
    if not session_id:
        logger.warning(f"Cannot resolve task reference '{value}': no session_id provided")
        return value

    # Get project_id from session
    session = session_manager.get(session_id)
    if not session or not session.project_id:
        logger.warning(f"Cannot resolve task reference '{value}': session has no project_id")
        return value

    # Resolve the reference
    try:
        resolved = resolve_task_reference(db, value, session.project_id)
        logger.debug(f"Resolved session_task '{value}' to UUID '{resolved}'")
        return resolved
    except TaskNotFoundError as e:
        logger.warning(f"Could not resolve task reference '{value}': {e}")
        return value
    except Exception as e:
        logger.warning(f"Unexpected error resolving task reference '{value}': {e}")
        return value


def create_workflows_registry(
    loader: WorkflowLoader | None = None,
    state_manager: WorkflowStateManager | None = None,
    session_manager: LocalSessionManager | None = None,
    db: LocalDatabase | None = None,
) -> InternalToolRegistry:
    """
    Create a workflow tool registry with all workflow-related tools.

    Args:
        loader: WorkflowLoader instance
        state_manager: WorkflowStateManager instance
        session_manager: LocalSessionManager instance
        db: LocalDatabase instance

    Returns:
        InternalToolRegistry with workflow tools registered
    """
    from gobby.utils.project_context import get_project_context

    # Create defaults if not provided
    _db = db or LocalDatabase()
    _loader = loader or WorkflowLoader()
    _state_manager = state_manager or WorkflowStateManager(_db)
    _session_manager = session_manager or LocalSessionManager(_db)

    def _resolve_session_id(ref: str) -> str:
        """Resolve session reference (#N, N, UUID, or prefix) to UUID."""
        project_ctx = get_project_context()
        project_id = project_ctx.get("id") if project_ctx else None
        return _session_manager.resolve_session_reference(ref, project_id)

    registry = InternalToolRegistry(
        name="gobby-workflows",
        description="Workflow management - list, activate, status, transition, end",
    )

    @registry.tool(
        name="get_workflow",
        description="Get details about a specific workflow definition.",
    )
    def get_workflow(
        name: str,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Get workflow details including steps, triggers, and settings.

        Args:
            name: Workflow name (without .yaml extension)
            project_path: Project directory path. Auto-discovered from cwd if not provided.

        Returns:
            Workflow definition details
        """
        # Auto-discover project path if not provided
        if not project_path:
            discovered = get_workflow_project_path()
            if discovered:
                project_path = str(discovered)

        proj = Path(project_path) if project_path else None
        definition = _loader.load_workflow(name, proj)

        if not definition:
            return {"success": False, "error": f"Workflow '{name}' not found"}

        return {
            "success": True,
            "name": definition.name,
            "type": definition.type,
            "description": definition.description,
            "version": definition.version,
            "steps": (
                [
                    {
                        "name": s.name,
                        "description": s.description,
                        "allowed_tools": s.allowed_tools,
                        "blocked_tools": s.blocked_tools,
                    }
                    for s in definition.steps
                ]
                if definition.steps
                else []
            ),
            "triggers": (
                {name: len(actions) for name, actions in definition.triggers.items()}
                if definition.triggers
                else {}
            ),
            "settings": definition.settings,
        }

    @registry.tool(
        name="list_workflows",
        description="List available workflow definitions from project and global directories.",
    )
    def list_workflows(
        project_path: str | None = None,
        workflow_type: str | None = None,
        global_only: bool = False,
    ) -> dict[str, Any]:
        """
        List available workflows.

        Lists workflows from both project (.gobby/workflows) and global (~/.gobby/workflows)
        directories. Project workflows shadow global ones with the same name.

        Args:
            project_path: Project directory path. Auto-discovered from cwd if not provided.
            workflow_type: Filter by type ("step" or "lifecycle")
            global_only: If True, only show global workflows (ignore project)

        Returns:
            List of workflows with name, type, description, and source
        """
        import yaml

        # Auto-discover project path if not provided
        if not project_path:
            discovered = get_workflow_project_path()
            if discovered:
                project_path = str(discovered)

        search_dirs = list(_loader.global_dirs)
        proj = Path(project_path) if project_path else None

        # Include project workflows unless global_only (project searched first to shadow global)
        if not global_only and proj:
            project_dir = proj / ".gobby" / "workflows"
            if project_dir.exists():
                search_dirs.insert(0, project_dir)

        workflows = []
        seen_names = set()

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            is_project = proj and search_dir == (proj / ".gobby" / "workflows")

            for yaml_path in search_dir.glob("*.yaml"):
                name = yaml_path.stem
                if name in seen_names:
                    continue

                try:
                    with open(yaml_path) as f:
                        data = yaml.safe_load(f)

                    if not data:
                        continue

                    wf_type = data.get("type", "step")

                    if workflow_type and wf_type != workflow_type:
                        continue

                    workflows.append(
                        {
                            "name": name,
                            "type": wf_type,
                            "description": data.get("description", ""),
                            "source": "project" if is_project else "global",
                        }
                    )
                    seen_names.add(name)

                except Exception:
                    pass  # nosec B110 - skip invalid workflow files

        return {"workflows": workflows, "count": len(workflows)}

    @registry.tool(
        name="activate_workflow",
        description="Activate a step-based workflow for the current session. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def activate_workflow(
        name: str,
        session_id: str | None = None,
        initial_step: str | None = None,
        variables: dict[str, Any] | None = None,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Activate a step-based workflow for the current session.

        Args:
            name: Workflow name (e.g., "plan-act-reflect", "auto-task")
            session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed
            initial_step: Optional starting step (defaults to first step)
            variables: Optional initial variables to set (merged with workflow defaults)
            project_path: Project directory path. Auto-discovered from cwd if not provided.

        Returns:
            Success status, workflow info, and current step.

        Example:
            activate_workflow(
                name="auto-task",
                variables={"session_task": "#47"},
                session_id="#5"
            )

        Errors if:
            - session_id not provided
            - Another step-based workflow is currently active
            - Workflow not found
            - Workflow is lifecycle type (those auto-run, not manually activated)
        """
        # Auto-discover project path if not provided
        if not project_path:
            discovered = get_workflow_project_path()
            if discovered:
                project_path = str(discovered)

        proj = Path(project_path) if project_path else None

        # Load workflow
        definition = _loader.load_workflow(name, proj)
        if not definition:
            return {"success": False, "error": f"Workflow '{name}' not found"}

        if definition.type == "lifecycle":
            return {
                "success": False,
                "error": f"Workflow '{name}' is lifecycle type (auto-runs on events, not manually activated)",
            }

        # Require explicit session_id to prevent cross-session bleed
        if not session_id:
            return {
                "success": False,
                "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
            }

        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        try:
            resolved_session_id = _resolve_session_id(session_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        # Check for existing workflow
        # Allow if:
        # - No existing state
        # - Existing is __lifecycle__ placeholder
        # - Existing is a lifecycle-type workflow (they run concurrently with step workflows)
        existing = _state_manager.get_state(resolved_session_id)
        if existing and existing.workflow_name != "__lifecycle__":
            # Check if existing workflow is a lifecycle type
            existing_def = _loader.load_workflow(existing.workflow_name, proj)
            # Only allow if we can confirm it's a lifecycle workflow
            # If definition not found or it's a step workflow, block activation
            if not existing_def or existing_def.type != "lifecycle":
                # It's a step workflow (or unknown) - can only have one active
                return {
                    "success": False,
                    "error": f"Session already has step workflow '{existing.workflow_name}' active. Use end_workflow first.",
                }
            # Existing is a lifecycle workflow - allow step workflow to activate alongside it

        # Determine initial step
        if initial_step:
            if not any(s.name == initial_step for s in definition.steps):
                return {
                    "success": False,
                    "error": f"Step '{initial_step}' not found. Available: {[s.name for s in definition.steps]}",
                }
            step = initial_step
        else:
            step = definition.steps[0].name if definition.steps else "default"

        # Merge workflow default variables with passed-in variables
        merged_variables = dict(definition.variables)  # Start with workflow defaults
        if variables:
            merged_variables.update(variables)  # Override with passed-in values

        # Resolve session_task references (#N or N) to UUIDs upfront
        # This prevents repeated resolution failures in condition evaluation
        if "session_task" in merged_variables:
            session_task_val = merged_variables["session_task"]
            if isinstance(session_task_val, str):
                merged_variables["session_task"] = _resolve_session_task_value(
                    session_task_val, resolved_session_id, _session_manager, _db
                )

        # Create state
        state = WorkflowState(
            session_id=resolved_session_id,
            workflow_name=name,
            step=step,
            step_entered_at=datetime.now(UTC),
            step_action_count=0,
            total_action_count=0,
            artifacts={},
            observations=[],
            reflection_pending=False,
            context_injected=False,
            variables=merged_variables,
            task_list=None,
            current_task_index=0,
            files_modified_this_task=0,
        )

        _state_manager.save_state(state)

        return {
            "success": True,
            "session_id": resolved_session_id,
            "workflow": name,
            "step": step,
            "steps": [s.name for s in definition.steps],
            "variables": merged_variables,
        }

    @registry.tool(
        name="end_workflow",
        description="End the currently active step-based workflow. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def end_workflow(
        session_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """
        End the currently active step-based workflow.

        Allows starting a different workflow afterward.
        Does not affect lifecycle workflows (they continue running).

        Args:
            session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed
            reason: Optional reason for ending

        Returns:
            Success status
        """
        # Require explicit session_id to prevent cross-session bleed
        if not session_id:
            return {
                "success": False,
                "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
            }

        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        try:
            resolved_session_id = _resolve_session_id(session_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        state = _state_manager.get_state(resolved_session_id)
        if not state:
            return {"error": "No workflow active for session"}

        _state_manager.delete_state(resolved_session_id)

        return {}

    @registry.tool(
        name="get_workflow_status",
        description="Get current workflow step and state. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def get_workflow_status(session_id: str | None = None) -> dict[str, Any]:
        """
        Get current workflow step and state.

        Args:
            session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed

        Returns:
            Workflow state including step, action counts, artifacts
        """
        # Require explicit session_id to prevent cross-session bleed
        if not session_id:
            return {
                "has_workflow": False,
                "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
            }

        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        try:
            resolved_session_id = _resolve_session_id(session_id)
        except ValueError as e:
            return {"has_workflow": False, "error": str(e)}

        state = _state_manager.get_state(resolved_session_id)
        if not state:
            return {"has_workflow": False, "session_id": resolved_session_id}

        return {
            "has_workflow": True,
            "session_id": resolved_session_id,
            "workflow_name": state.workflow_name,
            "step": state.step,
            "step_action_count": state.step_action_count,
            "total_action_count": state.total_action_count,
            "reflection_pending": state.reflection_pending,
            "artifacts": list(state.artifacts.keys()) if state.artifacts else [],
            "variables": state.variables,
            "task_progress": (
                f"{state.current_task_index + 1}/{len(state.task_list)}"
                if state.task_list
                else None
            ),
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }

    @registry.tool(
        name="request_step_transition",
        description="Request transition to a different step. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def request_step_transition(
        to_step: str,
        reason: str | None = None,
        session_id: str | None = None,
        force: bool = False,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Request transition to a different step. May require approval.

        Args:
            to_step: Target step name
            reason: Reason for transition
            session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed
            force: Skip exit condition checks
            project_path: Project directory path. Auto-discovered from cwd if not provided.

        Returns:
            Success status and new step info
        """
        # Auto-discover project path if not provided
        if not project_path:
            discovered = get_workflow_project_path()
            if discovered:
                project_path = str(discovered)

        proj = Path(project_path) if project_path else None

        # Require explicit session_id to prevent cross-session bleed
        if not session_id:
            return {
                "success": False,
                "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
            }

        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        try:
            resolved_session_id = _resolve_session_id(session_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        state = _state_manager.get_state(resolved_session_id)
        if not state:
            return {"success": False, "error": "No workflow active for session"}

        # Load workflow to validate step
        definition = _loader.load_workflow(state.workflow_name, proj)
        if not definition:
            return {"success": False, "error": f"Workflow '{state.workflow_name}' not found"}

        if not any(s.name == to_step for s in definition.steps):
            return {
                "success": False,
                "error": f"Step '{to_step}' not found. Available: {[s.name for s in definition.steps]}",
            }

        # Block manual transitions to steps that have conditional auto-transitions
        # These steps should only be reached when their conditions are met
        current_step_def = next((s for s in definition.steps if s.name == state.step), None)
        if current_step_def and current_step_def.transitions:
            for transition in current_step_def.transitions:
                if transition.to == to_step and transition.when:
                    # This step has a conditional transition - block manual transition
                    return {
                        "success": False,
                        "error": (
                            f"Step '{to_step}' has a conditional auto-transition "
                            f"(when: {transition.when}). Manual transitions to this step "
                            f"are blocked to prevent workflow circumvention. "
                            f"The transition will occur automatically when the condition is met."
                        ),
                    }

        old_step = state.step
        state.step = to_step
        state.step_entered_at = datetime.now(UTC)
        state.step_action_count = 0

        _state_manager.save_state(state)

        return {
            "success": True,
            "from_step": old_step,
            "to_step": to_step,
            "reason": reason,
            "forced": force,
        }

    @registry.tool(
        name="mark_artifact_complete",
        description="Register an artifact as complete (plan, spec, etc.). Accepts #N, N, UUID, or prefix for session_id.",
    )
    def mark_artifact_complete(
        artifact_type: str,
        file_path: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Register an artifact as complete.

        Args:
            artifact_type: Type of artifact (e.g., "plan", "spec", "test")
            file_path: Path to the artifact file
            session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed

        Returns:
            Success status
        """
        # Require explicit session_id to prevent cross-session bleed
        if not session_id:
            return {
                "success": False,
                "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
            }

        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        try:
            resolved_session_id = _resolve_session_id(session_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        state = _state_manager.get_state(resolved_session_id)
        if not state:
            return {"error": "No workflow active for session"}

        # Update artifacts
        state.artifacts[artifact_type] = file_path
        _state_manager.save_state(state)

        return {}

    @registry.tool(
        name="set_variable",
        description="Set a workflow variable for the current session (session-scoped, not persisted to YAML). Accepts #N, N, UUID, or prefix for session_id.",
    )
    def set_variable(
        name: str,
        value: str | int | float | bool | None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Set a workflow variable for the current session.

        Variables set this way are session-scoped - they persist in the database
        for the duration of the session but do not modify the workflow YAML file.

        This is useful for:
        - Setting session_epic to enforce epic completion before stopping
        - Setting is_worktree to mark a session as a worktree agent
        - Dynamic configuration without modifying workflow definitions

        Args:
            name: Variable name (e.g., "session_epic", "is_worktree")
            value: Variable value (string, number, boolean, or null)
            session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed

        Returns:
            Success status and updated variables
        """
        # Require explicit session_id to prevent cross-session bleed
        if not session_id:
            return {
                "success": False,
                "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
            }

        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        try:
            resolved_session_id = _resolve_session_id(session_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        # Get or create state
        state = _state_manager.get_state(resolved_session_id)
        if not state:
            # Create a minimal lifecycle state for variable storage
            state = WorkflowState(
                session_id=resolved_session_id,
                workflow_name="__lifecycle__",
                step="",
                step_entered_at=datetime.now(UTC),
                variables={},
            )

        # Block modification of session_task when a real workflow is active
        # This prevents circumventing workflows by changing the tracked task
        if name == "session_task" and state.workflow_name != "__lifecycle__":
            current_value = state.variables.get("session_task")
            if current_value is not None and value != current_value:
                return {
                    "success": False,
                    "error": (
                        f"Cannot modify session_task while workflow '{state.workflow_name}' is active. "
                        f"Current value: {current_value}. "
                        f"Use end_workflow() first if you need to change the tracked task."
                    ),
                }

        # Resolve session_task references (#N or N) to UUIDs upfront
        # This prevents repeated resolution failures in condition evaluation
        if name == "session_task" and isinstance(value, str):
            value = _resolve_session_task_value(value, resolved_session_id, _session_manager, _db)

        # Set the variable
        state.variables[name] = value
        _state_manager.save_state(state)

        # Add deprecation warning for session_task variable (when no workflow active)
        if name == "session_task" and value and state.workflow_name == "__lifecycle__":
            return {
                "warning": (
                    "DEPRECATED: Setting session_task directly is deprecated. "
                    "Use activate_workflow(name='auto-task', variables={'session_task': ...}) instead "
                    "for proper state machine semantics and on_premature_stop handling."
                ),
            }

        return {}

    @registry.tool(
        name="get_variable",
        description="Get workflow variable(s) for the current session. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def get_variable(
        name: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Get workflow variable(s) for the current session.

        Args:
            name: Variable name to get (if None, returns all variables)
            session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed

        Returns:
            Variable value(s) and session info
        """
        # Require explicit session_id to prevent cross-session bleed
        if not session_id:
            return {
                "success": False,
                "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
            }

        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        try:
            resolved_session_id = _resolve_session_id(session_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        state = _state_manager.get_state(resolved_session_id)
        if not state:
            if name:
                return {
                    "success": True,
                    "session_id": resolved_session_id,
                    "variable": name,
                    "value": None,
                    "exists": False,
                }
            return {
                "success": True,
                "session_id": resolved_session_id,
                "variables": {},
            }

        if name:
            value = state.variables.get(name)
            return {
                "success": True,
                "session_id": resolved_session_id,
                "variable": name,
                "value": value,
                "exists": name in state.variables,
            }

        return {
            "success": True,
            "session_id": resolved_session_id,
            "variables": state.variables,
        }

    @registry.tool(
        name="import_workflow",
        description="Import a workflow from a file path into the project or global directory.",
    )
    def import_workflow(
        source_path: str,
        workflow_name: str | None = None,
        is_global: bool = False,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Import a workflow from a file.

        Args:
            source_path: Path to the workflow YAML file
            workflow_name: Override the workflow name (defaults to name in file)
            is_global: Install to global ~/.gobby/workflows instead of project
            project_path: Project directory path. Auto-discovered from cwd if not provided.

        Returns:
            Success status and destination path
        """
        import shutil

        import yaml

        source = Path(source_path)
        if not source.exists():
            return {"success": False, "error": f"File not found: {source_path}"}

        if source.suffix != ".yaml":
            return {"success": False, "error": "Workflow file must have .yaml extension"}

        try:
            with open(source) as f:
                data = yaml.safe_load(f)

            if not data or "name" not in data:
                return {"success": False, "error": "Invalid workflow: missing 'name' field"}

        except yaml.YAMLError as e:
            return {"success": False, "error": f"Invalid YAML: {e}"}

        name = workflow_name or data.get("name", source.stem)
        filename = f"{name}.yaml"

        if is_global:
            dest_dir = Path.home() / ".gobby" / "workflows"
        else:
            # Auto-discover project path if not provided
            if not project_path:
                discovered = get_workflow_project_path()
                if discovered:
                    project_path = str(discovered)

            proj = Path(project_path) if project_path else None
            if not proj:
                return {
                    "success": False,
                    "error": "project_path required when not using is_global (could not auto-discover)",
                }
            dest_dir = proj / ".gobby" / "workflows"

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        shutil.copy(source, dest_path)

        # Clear loader cache so new workflow is discoverable
        _loader.clear_cache()

        return {
            "success": True,
            "workflow_name": name,
            "destination": str(dest_path),
            "is_global": is_global,
        }

    @registry.tool(
        name="reload_cache",
        description="Clear the workflow cache. Use this after modifying workflow YAML files.",
    )
    def reload_cache() -> dict[str, Any]:
        """
        Clear the workflow loader cache.

        This forces the daemon to re-read workflow YAML files from disk
        on the next access. Use this when you've modified workflow files
        and want the changes to take effect immediately without restarting
        the daemon.

        Returns:
            Success status
        """
        _loader.clear_cache()
        logger.info("Workflow cache cleared via reload_cache tool")
        return {"message": "Workflow cache cleared"}

    @registry.tool(
        name="close_terminal",
        description=(
            "Close the current terminal window/pane (agent self-termination). "
            "Launches ~/.gobby/scripts/agent_shutdown.sh which handles "
            "terminal-specific shutdown (tmux, iTerm, etc.). Rebuilds script if missing."
        ),
    )
    async def close_terminal(
        signal: str = "TERM",
        delay_ms: int = 0,
    ) -> dict[str, Any]:
        """
        Close the current terminal by running the agent shutdown script.

        This is for agent self-termination (meeseeks-style). The agent calls
        this to close its own terminal window when done with its workflow.

        The script is located at ~/.gobby/scripts/agent_shutdown.sh and is
        automatically rebuilt if missing. It handles different terminal types
        (tmux, iTerm, Terminal.app, Ghostty, Kitty, WezTerm, etc.).

        Args:
            signal: Signal to use for shutdown (TERM, KILL, INT). Default: TERM.
            delay_ms: Optional delay in milliseconds before shutdown. Default: 0.

        Returns:
            Dict with success status and message.
        """
        import asyncio
        import os
        import stat
        import subprocess  # nosec B404 - subprocess needed for agent shutdown script

        # Script location
        gobby_dir = Path.home() / ".gobby"
        scripts_dir = gobby_dir / "scripts"
        script_path = scripts_dir / "agent_shutdown.sh"

        # Source script from the install directory (single source of truth)
        source_script_path = (
            Path(__file__).parent.parent.parent
            / "install"
            / "shared"
            / "scripts"
            / "agent_shutdown.sh"
        )

        def get_script_version(script_content: str) -> str | None:
            """Extract VERSION marker from script content."""
            import re

            match = re.search(r"^# VERSION:\s*(.+)$", script_content, re.MULTILINE)
            return match.group(1).strip() if match else None

        # Ensure directories exist and script is present/up-to-date
        script_rebuilt = False
        try:
            scripts_dir.mkdir(parents=True, exist_ok=True)

            # Read source script content
            if source_script_path.exists():
                source_content = source_script_path.read_text()
                source_version = get_script_version(source_content)
            else:
                logger.warning(f"Source shutdown script not found at {source_script_path}")
                source_content = None
                source_version = None

            # Check if installed script exists and compare versions
            needs_rebuild = False
            if not script_path.exists():
                needs_rebuild = True
            elif source_content:
                installed_content = script_path.read_text()
                installed_version = get_script_version(installed_content)
                # Rebuild if versions differ or installed has no version marker
                if installed_version != source_version:
                    needs_rebuild = True
                    logger.info(
                        f"Shutdown script version mismatch: installed={installed_version}, source={source_version}"
                    )

            if needs_rebuild and source_content:
                script_path.write_text(source_content)
                # Make executable
                script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
                script_rebuilt = True
                logger.info(f"Created/updated agent shutdown script at {script_path}")
        except OSError as e:
            return {
                "success": False,
                "error": f"Failed to create shutdown script: {e}",
            }

        # Validate signal
        valid_signals = {"TERM", "KILL", "INT", "HUP", "QUIT"}
        if signal.upper() not in valid_signals:
            return {
                "success": False,
                "error": f"Invalid signal '{signal}'. Valid: {valid_signals}",
            }

        # Apply delay before launching script (non-blocking)
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)

        # Launch the script
        try:
            # Run in background - we don't wait for it since it kills our process
            env = os.environ.copy()

            subprocess.Popen(  # nosec B603 - script path is from gobby scripts directory
                [str(script_path), signal.upper(), "0"],  # Delay already applied
                env=env,
                start_new_session=True,  # Detach from parent
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            return {
                "success": True,
                "message": "Shutdown script launched",
                "script_path": str(script_path),
                "script_rebuilt": script_rebuilt,
                "signal": signal.upper(),
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to launch shutdown script: {e}",
            }

    return registry
