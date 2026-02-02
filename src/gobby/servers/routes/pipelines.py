"""
Pipeline routes for Gobby HTTP server.

Provides endpoints for running, approving, and monitoring pipelines.
"""

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


class PipelineRunRequest(BaseModel):
    """Request body for POST /api/pipelines/run."""

    name: str
    inputs: dict[str, Any] = {}
    project_id: str | None = None


class PipelineRunResponse(BaseModel):
    """Response body for successful pipeline execution."""

    status: str
    execution_id: str
    pipeline_name: str
    outputs: dict[str, Any] | None = None


class PipelineApprovalResponse(BaseModel):
    """Response body when pipeline requires approval."""

    status: str
    execution_id: str
    step_id: str
    token: str
    message: str


def create_pipelines_router(server: "HTTPServer") -> APIRouter:
    """
    Create pipelines router with endpoints bound to server instance.

    Args:
        server: HTTPServer instance for accessing state and dependencies

    Returns:
        Configured APIRouter with pipeline endpoints
    """
    router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])

    @router.post("/run")
    async def run_pipeline(request: PipelineRunRequest) -> dict[str, Any]:
        """
        Run a pipeline by name.

        Returns:
            200: Pipeline completed successfully
            202: Pipeline waiting for approval
            404: Pipeline not found
            500: Execution error
        """
        from gobby.workflows.pipeline_state import ApprovalRequired

        # Get loader and executor from services
        loader = server.services.workflow_loader
        executor = server.services.pipeline_executor

        if loader is None:
            raise HTTPException(status_code=500, detail="Workflow loader not configured")

        if executor is None:
            raise HTTPException(status_code=500, detail="Pipeline executor not configured")

        # Load the pipeline
        pipeline = loader.load_pipeline(request.name)
        if pipeline is None:
            raise HTTPException(status_code=404, detail=f"Pipeline '{request.name}' not found")

        try:
            # Execute the pipeline
            execution = await executor.execute(
                pipeline=pipeline,
                inputs=request.inputs,
                project_id=request.project_id or "",
            )

            # Return success response
            return {
                "status": execution.status.value,
                "execution_id": execution.id,
                "pipeline_name": execution.pipeline_name,
            }

        except ApprovalRequired as e:
            # Return 202 Accepted for approval required
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=202,
                content={
                    "status": "waiting_approval",
                    "execution_id": e.execution_id,
                    "step_id": e.step_id,
                    "token": e.token,
                    "message": e.message,
                },
            )

        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Execution error: {e}") from None

    @router.get("/{execution_id}")
    async def get_execution(execution_id: str) -> dict[str, Any]:
        """
        Get execution details by ID.

        Returns:
            200: Execution details with steps
            404: Execution not found
        """
        # Get execution manager from services
        execution_manager = server.services.pipeline_execution_manager

        if execution_manager is None:
            raise HTTPException(status_code=500, detail="Pipeline execution manager not configured")

        # Fetch execution
        execution = execution_manager.get_execution(execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

        # Fetch steps
        steps = execution_manager.get_steps_for_execution(execution_id)

        return {
            "id": execution.id,
            "pipeline_name": execution.pipeline_name,
            "project_id": execution.project_id,
            "status": execution.status.value,
            "created_at": execution.created_at,
            "updated_at": execution.updated_at,
            "steps": [
                {
                    "id": step.id,
                    "step_id": step.step_id,
                    "status": step.status.value,
                }
                for step in steps
            ],
        }

    @router.post("/approve/{token}")
    async def approve_execution(token: str) -> dict[str, Any]:
        """
        Approve a pipeline execution waiting for approval.

        Returns:
            200: Execution resumed and completed (or continued)
            202: Execution resumed but needs another approval
            404: Invalid token
        """
        from gobby.workflows.pipeline_state import ApprovalRequired

        executor = server.services.pipeline_executor

        if executor is None:
            raise HTTPException(status_code=500, detail="Pipeline executor not configured")

        try:
            execution = await executor.approve(token, approved_by=None)

            return {
                "status": execution.status.value,
                "execution_id": execution.id,
                "pipeline_name": execution.pipeline_name,
            }

        except ApprovalRequired as e:
            # Pipeline needs another approval
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=202,
                content={
                    "status": "waiting_approval",
                    "execution_id": e.execution_id,
                    "step_id": e.step_id,
                    "token": e.token,
                    "message": e.message,
                },
            )

        except ValueError as e:
            raise HTTPException(status_code=404, detail=f"Invalid token: {e}") from None

    @router.post("/reject/{token}")
    async def reject_execution(token: str) -> dict[str, Any]:
        """
        Reject a pipeline execution waiting for approval.

        Returns:
            200: Execution rejected/cancelled
            404: Invalid token
        """
        executor = server.services.pipeline_executor

        if executor is None:
            raise HTTPException(status_code=500, detail="Pipeline executor not configured")

        try:
            execution = await executor.reject(token, rejected_by=None)

            return {
                "status": execution.status.value,
                "execution_id": execution.id,
                "pipeline_name": execution.pipeline_name,
            }

        except ValueError as e:
            raise HTTPException(status_code=404, detail=f"Invalid token: {e}") from None

    return router
