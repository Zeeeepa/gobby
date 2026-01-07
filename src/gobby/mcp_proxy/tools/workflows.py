"""
Internal MCP tools for Gobby Workflow System.

Exposes functionality for:
- list_workflows: Discover available workflow definitions
- activate_workflow: Start a step-based workflow
- end_workflow: Complete/terminate active workflow
- get_workflow_status: Get current workflow state
- request_step_transition: Request transition to a different step
- mark_artifact_complete: Register an artifact as complete

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.database import LocalDatabase
from gobby.storage.sessions import LocalSessionManager
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager


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
    # Create defaults if not provided
    _db = db or LocalDatabase()
    _loader = loader or WorkflowLoader()
    _state_manager = state_manager or WorkflowStateManager(_db)
    _session_manager = session_manager or LocalSessionManager(_db)

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
            project_path: Optional project directory path

        Returns:
            Workflow definition details
        """
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
            "steps": [
                {
                    "name": s.name,
                    "description": s.description,
                    "allowed_tools": s.allowed_tools,
                    "blocked_tools": s.blocked_tools,
                }
                for s in definition.steps
            ]
            if definition.steps
            else [],
            "triggers": {name: len(actions) for name, actions in definition.triggers.items()}
            if definition.triggers
            else {},
            "settings": definition.settings,
        }

    @registry.tool(
        name="list_workflows",
        description="List available workflow definitions from project and global directories.",
    )
    def list_workflows(
        project_path: str | None = None,
        workflow_type: str | None = None,
    ) -> dict[str, Any]:
        """
        List available workflows.

        Args:
            project_path: Optional project directory path
            workflow_type: Filter by type ("step" or "lifecycle")

        Returns:
            List of workflows with name, type, description, and source
        """
        import yaml

        search_dirs = list(_loader.global_dirs)
        proj = Path(project_path) if project_path else None

        if proj:
            project_dir = proj / ".gobby" / "workflows"
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
                    pass

        return {"workflows": workflows, "count": len(workflows)}

    @registry.tool(
        name="activate_workflow",
        description="Activate a step-based workflow for the current session.",
    )
    def activate_workflow(
        name: str,
        session_id: str | None = None,
        initial_step: str | None = None,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Activate a step-based workflow for the current session.

        Args:
            name: Workflow name (e.g., "plan-act-reflect", "tdd")
            session_id: Required session ID (must be provided to prevent cross-session bleed)
            initial_step: Optional starting step (defaults to first step)
            project_path: Optional project directory path

        Returns:
            Success status, workflow info, and current step.

        Errors if:
            - session_id not provided
            - Another step-based workflow is currently active
            - Workflow not found
            - Workflow is lifecycle type (those auto-run, not manually activated)
        """
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

        # Check for existing workflow
        existing = _state_manager.get_state(session_id)
        if existing:
            return {
                "success": False,
                "error": f"Session already has workflow '{existing.workflow_name}' active. Use end_workflow first.",
            }

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

        # Create state
        state = WorkflowState(
            session_id=session_id,
            workflow_name=name,
            step=step,
            step_entered_at=datetime.now(UTC),
            step_action_count=0,
            total_action_count=0,
            artifacts={},
            observations=[],
            reflection_pending=False,
            context_injected=False,
            variables={},
            task_list=None,
            current_task_index=0,
            files_modified_this_task=0,
        )

        _state_manager.save_state(state)

        return {
            "success": True,
            "session_id": session_id,
            "workflow": name,
            "step": step,
            "steps": [s.name for s in definition.steps],
        }

    @registry.tool(
        name="end_workflow",
        description="End the currently active step-based workflow.",
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
            session_id: Required session ID (must be provided to prevent cross-session bleed)
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

        state = _state_manager.get_state(session_id)
        if not state:
            return {"success": False, "error": "No workflow active for session"}

        workflow_name = state.workflow_name
        _state_manager.delete_state(session_id)

        return {
            "success": True,
            "ended_workflow": workflow_name,
            "reason": reason,
        }

    @registry.tool(
        name="get_workflow_status",
        description="Get current workflow step and state.",
    )
    def get_workflow_status(session_id: str | None = None) -> dict[str, Any]:
        """
        Get current workflow step and state.

        Args:
            session_id: Required session ID (must be provided to prevent cross-session bleed)

        Returns:
            Workflow state including step, action counts, artifacts
        """
        # Require explicit session_id to prevent cross-session bleed
        if not session_id:
            return {
                "has_workflow": False,
                "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
            }

        state = _state_manager.get_state(session_id)
        if not state:
            return {"has_workflow": False, "session_id": session_id}

        return {
            "has_workflow": True,
            "session_id": session_id,
            "workflow_name": state.workflow_name,
            "step": state.step,
            "step_action_count": state.step_action_count,
            "total_action_count": state.total_action_count,
            "reflection_pending": state.reflection_pending,
            "artifacts": list(state.artifacts.keys()) if state.artifacts else [],
            "variables": state.variables,
            "task_progress": f"{state.current_task_index + 1}/{len(state.task_list)}"
            if state.task_list
            else None,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }

    @registry.tool(
        name="request_step_transition",
        description="Request transition to a different step.",
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
            session_id: Required session ID (must be provided to prevent cross-session bleed)
            force: Skip exit condition checks
            project_path: Optional project directory path

        Returns:
            Success status and new step info
        """
        proj = Path(project_path) if project_path else None

        # Require explicit session_id to prevent cross-session bleed
        if not session_id:
            return {
                "success": False,
                "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
            }

        state = _state_manager.get_state(session_id)
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
        description="Register an artifact as complete (plan, spec, etc.).",
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
            session_id: Required session ID (must be provided to prevent cross-session bleed)

        Returns:
            Success status
        """
        # Require explicit session_id to prevent cross-session bleed
        if not session_id:
            return {
                "success": False,
                "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
            }

        state = _state_manager.get_state(session_id)
        if not state:
            return {"success": False, "error": "No workflow active for session"}

        # Update artifacts
        state.artifacts[artifact_type] = file_path
        _state_manager.save_state(state)

        return {
            "success": True,
            "artifact_type": artifact_type,
            "file_path": file_path,
            "all_artifacts": list(state.artifacts.keys()),
        }

    @registry.tool(
        name="set_variable",
        description="Set a workflow variable for the current session (session-scoped, not persisted to YAML).",
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
            session_id: Required session ID (must be provided to prevent cross-session bleed)

        Returns:
            Success status and updated variables
        """
        # Require explicit session_id to prevent cross-session bleed
        if not session_id:
            return {
                "success": False,
                "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
            }

        # Get or create state
        state = _state_manager.get_state(session_id)
        if not state:
            # Create a minimal lifecycle state for variable storage
            state = WorkflowState(
                session_id=session_id,
                workflow_name="__lifecycle__",
                step="",
                step_entered_at=datetime.now(UTC),
                variables={},
            )

        # Set the variable
        state.variables[name] = value
        _state_manager.save_state(state)

        return {
            "success": True,
            "session_id": session_id,
            "variable": name,
            "value": value,
            "all_variables": state.variables,
        }

    @registry.tool(
        name="get_variable",
        description="Get workflow variable(s) for the current session.",
    )
    def get_variable(
        name: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Get workflow variable(s) for the current session.

        Args:
            name: Variable name to get (if None, returns all variables)
            session_id: Required session ID (must be provided to prevent cross-session bleed)

        Returns:
            Variable value(s) and session info
        """
        # Require explicit session_id to prevent cross-session bleed
        if not session_id:
            return {
                "success": False,
                "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
            }

        state = _state_manager.get_state(session_id)
        if not state:
            if name:
                return {
                    "success": True,
                    "session_id": session_id,
                    "variable": name,
                    "value": None,
                    "exists": False,
                }
            return {
                "success": True,
                "session_id": session_id,
                "variables": {},
            }

        if name:
            value = state.variables.get(name)
            return {
                "success": True,
                "session_id": session_id,
                "variable": name,
                "value": value,
                "exists": name in state.variables,
            }

        return {
            "success": True,
            "session_id": session_id,
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
            project_path: Project directory path (required if not is_global)

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
            proj = Path(project_path) if project_path else None
            if not proj:
                return {"success": False, "error": "project_path required when not using is_global"}
            dest_dir = proj / ".gobby" / "workflows"

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        shutil.copy(source, dest_path)

        # Clear loader cache so new workflow is discoverable
        _loader.clear_discovery_cache()

        return {
            "success": True,
            "workflow_name": name,
            "destination": str(dest_path),
            "is_global": is_global,
        }

    @registry.tool(
        name="activate_autonomous_task",
        description="Activate autonomous-task workflow with a session_task (atomic operation).",
    )
    def activate_autonomous_task(
        task_id: str,
        session_id: str | None = None,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Activate the autonomous-task step workflow with a task assignment.

        This is a convenience helper that atomically:
        1. Sets the session_task variable to the given task ID
        2. Activates the autonomous-task workflow

        The workflow will keep the agent working until the task tree is complete.
        Use this instead of manually setting variables and activating separately.

        Args:
            task_id: Task ID (e.g., "gt-abc123") or list of task IDs to work on
            session_id: Required session ID (must be provided explicitly)
            project_path: Optional project directory path

        Returns:
            Success status, workflow info, and current step.

        Example:
            activate_autonomous_task(task_id="gt-abc123", session_id="sess-xyz")
        """
        proj = Path(project_path) if project_path else None

        # Require explicit session_id
        if not session_id:
            return {
                "success": False,
                "error": "session_id is required. Pass the session ID explicitly.",
            }

        # Check for existing workflow
        existing = _state_manager.get_state(session_id)
        if existing and existing.workflow_name != "__lifecycle__":
            return {
                "success": False,
                "error": f"Session already has workflow '{existing.workflow_name}' active. Use end_workflow first.",
            }

        # Load the autonomous-task workflow
        definition = _loader.load_workflow("autonomous-task", proj)
        if not definition:
            return {
                "success": False,
                "error": "Workflow 'autonomous-task' not found. Ensure it's installed.",
            }

        # Create state with session_task already set
        state = WorkflowState(
            session_id=session_id,
            workflow_name="autonomous-task",
            step="work",  # Start in 'work' step
            step_entered_at=datetime.now(UTC),
            step_action_count=0,
            total_action_count=0,
            artifacts={},
            observations=[],
            reflection_pending=False,
            context_injected=False,
            variables={"session_task": task_id},  # Key: set session_task
            task_list=None,
            current_task_index=0,
            files_modified_this_task=0,
        )

        _state_manager.save_state(state)

        return {
            "success": True,
            "session_id": session_id,
            "workflow": "autonomous-task",
            "step": "work",
            "session_task": task_id,
            "message": f"Autonomous task workflow activated. Work on task {task_id} until all subtasks are complete.",
        }

    return registry
