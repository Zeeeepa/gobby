"""Workflow activation logic for the engine.

Extracted from engine.py as part of Strangler Fig decomposition (Wave 2).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .definitions import WorkflowDefinition, WorkflowState

if TYPE_CHECKING:
    from .engine import WorkflowEngine

logger = logging.getLogger(__name__)


async def activate_workflow(
    engine: WorkflowEngine,
    workflow_name: str,
    session_id: str,
    project_path: Path | None = None,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Activate a step-based workflow for a session.

    This is used internally during session startup for terminal-mode agents
    that have a workflow_name set. It creates the initial workflow state.

    Args:
        engine: WorkflowEngine instance providing loader, state_manager, etc.
        workflow_name: Name of the workflow to activate
        session_id: Session ID to activate for
        project_path: Optional project path for workflow discovery
        variables: Optional initial variables to merge with workflow defaults

    Returns:
        Dict with success status and workflow info
    """
    # Load workflow
    definition = await engine.loader.load_workflow(workflow_name, project_path)
    if not definition:
        logger.warning(f"Workflow '{workflow_name}' not found for auto-activation")
        return {"success": False, "error": f"Workflow '{workflow_name}' not found"}

    # Only WorkflowDefinition can be activated as step workflows
    if not isinstance(definition, WorkflowDefinition):
        logger.debug(f"Workflow '{workflow_name}' is a pipeline, not a step workflow")
        return {
            "success": False,
            "error": f"'{workflow_name}' is a pipeline. Use pipeline execution instead.",
        }

    if definition.enabled:
        logger.debug(f"Skipping activation of always-on workflow '{workflow_name}'")
        return {
            "success": False,
            "error": f"Workflow '{workflow_name}' is already enabled (auto-runs on events)",
        }

    # Check for existing step workflow
    existing = engine.state_manager.get_state(session_id)
    if existing and existing.workflow_name not in ("__lifecycle__", "__ended__"):
        # Check if existing is an always-on workflow (can coexist)
        existing_def = await engine.loader.load_workflow(existing.workflow_name, project_path)
        if not existing_def or not getattr(existing_def, "enabled", False):
            logger.warning(
                f"Session {session_id} already has workflow '{existing.workflow_name}' active"
            )
            return {
                "success": False,
                "error": f"Session already has workflow '{existing.workflow_name}' active",
            }

    # Determine initial step - fail fast if no steps defined
    if not definition.steps:
        logger.error(f"Workflow '{workflow_name}' has no steps defined")
        return {
            "success": False,
            "error": f"Workflow '{workflow_name}' has no steps defined",
        }
    step = definition.steps[0].name

    # Merge variables: preserve existing lifecycle variables, then apply workflow declarations
    # Priority: existing state < workflow defaults < passed-in variables
    # This preserves lifecycle variables (like unlocked_tools) that the step workflow doesn't declare
    merged_variables = dict(existing.variables) if existing else {}
    merged_variables.update(definition.variables)  # Override with workflow-declared defaults
    if variables:
        merged_variables.update(variables)  # Override with passed-in values

    # Create state
    state = WorkflowState(
        session_id=session_id,
        workflow_name=workflow_name,
        step=step,
        step_entered_at=datetime.now(UTC),
        step_action_count=0,
        total_action_count=0,
        observations=[],
        reflection_pending=False,
        context_injected=False,
        variables=merged_variables,
        task_list=None,
        current_task_index=0,
        files_modified_this_task=0,
    )

    engine.state_manager.save_state(state)
    logger.info(f"Auto-activated workflow '{workflow_name}' for session {session_id}")

    return {
        "success": True,
        "session_id": session_id,
        "workflow": workflow_name,
        "step": step,
        "steps": [s.name for s in definition.steps],
        "variables": merged_variables,
    }
