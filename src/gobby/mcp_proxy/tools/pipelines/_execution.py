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
