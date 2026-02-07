"""Pipeline execution tools."""

import json
from typing import Any, Protocol

from gobby.workflows.pipeline_state import ApprovalRequired


class PipelineLoader(Protocol):
    async def load_pipeline(self, name: str) -> Any: ...


class PipelineExecutor(Protocol):
    async def execute(self, *, pipeline: Any, inputs: dict[str, Any], project_id: str) -> Any: ...


async def run_pipeline(
    loader: PipelineLoader | None,
    executor: PipelineExecutor | None,
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
        Dict with execution status and outputs or approval info
    """
    if not executor:
        return {"success": False, "error": "No executor configured"}

    if not loader:
        return {"success": False, "error": "No loader configured"}

    # Load the pipeline definition
    pipeline = await loader.load_pipeline(name)
    if not pipeline:
        return {"success": False, "error": f"Pipeline '{name}' not found"}

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
        return {"success": False, "error": f"Execution failed: {e}"}


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
        Dict with execution status
    """
    if not executor:
        return {"success": False, "error": "No executor configured"}

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
        return {"success": False, "error": str(e)}

    except Exception as e:
        return {"success": False, "error": f"Approval failed: {e}"}


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
        Dict with execution status (cancelled)
    """
    if not executor:
        return {"success": False, "error": "No executor configured"}

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
        return {"success": False, "error": str(e)}

    except Exception as e:
        return {"success": False, "error": f"Rejection failed: {e}"}


def get_pipeline_status(
    execution_manager: Any,
    execution_id: str,
) -> dict[str, Any]:
    """
    Get the status of a pipeline execution.

    Args:
        execution_manager: LocalPipelineExecutionManager instance
        execution_id: Execution ID to query

    Returns:
        Dict with execution details and step statuses
    """
    if not execution_manager:
        return {"success": False, "error": "No execution manager configured"}

    try:
        execution = execution_manager.get_execution(execution_id)
        if not execution:
            return {"success": False, "error": f"Execution '{execution_id}' not found"}

        # Get step executions
        steps = execution_manager.get_steps_for_execution(execution_id)

        # Parse inputs if available
        inputs = None
        if execution.inputs_json:
            try:
                inputs = json.loads(execution.inputs_json)
            except json.JSONDecodeError:
                inputs = execution.inputs_json

        # Parse outputs if available
        outputs = None
        if execution.outputs_json:
            try:
                outputs = json.loads(execution.outputs_json)
            except json.JSONDecodeError:
                outputs = execution.outputs_json

        # Build execution dict
        execution_dict = {
            "id": execution.id,
            "pipeline_name": execution.pipeline_name,
            "project_id": execution.project_id,
            "status": execution.status.value,
            "inputs": inputs,
            "outputs": outputs,
            "created_at": execution.created_at,
            "updated_at": execution.updated_at,
            "completed_at": execution.completed_at,
            "resume_token": execution.resume_token,
            "session_id": execution.session_id,
        }

        # Build steps list
        steps_list = []
        for step in steps:
            step_output = None
            if step.output_json:
                try:
                    step_output = json.loads(step.output_json)
                except json.JSONDecodeError:
                    step_output = step.output_json

            steps_list.append(
                {
                    "id": step.id,
                    "step_id": step.step_id,
                    "status": step.status.value,
                    "started_at": step.started_at,
                    "completed_at": step.completed_at,
                    "output": step_output,
                    "error": step.error,
                    "approval_token": step.approval_token,
                    "approved_by": step.approved_by,
                    "approved_at": step.approved_at,
                }
            )

        return {
            "success": True,
            "execution": execution_dict,
            "steps": steps_list,
        }

    except Exception as e:
        return {"success": False, "error": f"Failed to get status: {e}"}
