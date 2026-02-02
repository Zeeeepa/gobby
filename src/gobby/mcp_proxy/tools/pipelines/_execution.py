"""Pipeline execution tools."""

import json
from typing import Any

from gobby.workflows.pipeline_state import ApprovalRequired


async def run_pipeline(
    loader: Any,
    executor: Any,
    name: str,
    inputs: dict[str, Any],
    project_id: str,
) -> dict[str, Any]:
    """
    Run a pipeline by name.

    Args:
        loader: WorkflowLoader instance
        executor: PipelineExecutor instance
        name: Pipeline name to run
        inputs: Input values for the pipeline
        project_id: Project context for the execution

    Returns:
        Dict with success status, execution status, and outputs or approval info
    """
    if not executor:
        return {
            "success": False,
            "error": "No executor configured",
        }

    if not loader:
        return {
            "success": False,
            "error": "No loader configured",
        }

    # Load the pipeline definition
    pipeline = loader.load_pipeline(name)
    if not pipeline:
        return {
            "success": False,
            "error": f"Pipeline '{name}' not found",
        }

    try:
        # Execute the pipeline
        execution = await executor.execute(
            pipeline=pipeline,
            inputs=inputs,
            project_id=project_id,
        )

        # Parse outputs if available
        outputs = None
        if execution.outputs_json:
            try:
                outputs = json.loads(execution.outputs_json)
            except json.JSONDecodeError:
                outputs = execution.outputs_json

        return {
            "success": True,
            "status": execution.status.value,
            "execution_id": execution.id,
            "outputs": outputs,
        }

    except ApprovalRequired as e:
        # Pipeline paused waiting for approval
        return {
            "success": True,
            "status": "waiting_approval",
            "execution_id": e.execution_id,
            "step_id": e.step_id,
            "token": e.token,
            "message": e.message,
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Execution failed: {e}",
        }


async def approve_pipeline(
    executor: Any,
    token: str,
    approved_by: str | None = None,
) -> dict[str, Any]:
    """
    Approve a pipeline execution waiting for approval.

    Args:
        executor: PipelineExecutor instance
        token: Approval token from the waiting execution
        approved_by: Identifier of who approved (email, user ID, etc.)

    Returns:
        Dict with success status and execution status
    """
    if not executor:
        return {
            "success": False,
            "error": "No executor configured",
        }

    try:
        execution = await executor.approve(
            token=token,
            approved_by=approved_by,
        )

        return {
            "success": True,
            "status": execution.status.value,
            "execution_id": execution.id,
        }

    except ValueError as e:
        return {
            "success": False,
            "error": str(e),
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Approval failed: {e}",
        }


async def reject_pipeline(
    executor: Any,
    token: str,
    rejected_by: str | None = None,
) -> dict[str, Any]:
    """
    Reject a pipeline execution waiting for approval.

    Args:
        executor: PipelineExecutor instance
        token: Approval token from the waiting execution
        rejected_by: Identifier of who rejected (email, user ID, etc.)

    Returns:
        Dict with success status and execution status (cancelled)
    """
    if not executor:
        return {
            "success": False,
            "error": "No executor configured",
        }

    try:
        execution = await executor.reject(
            token=token,
            rejected_by=rejected_by,
        )

        return {
            "success": True,
            "status": execution.status.value,
            "execution_id": execution.id,
        }

    except ValueError as e:
        return {
            "success": False,
            "error": str(e),
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Rejection failed: {e}",
        }
