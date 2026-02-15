"""
Workflow definition routes for Gobby HTTP server.

Provides CRUD endpoints for managing workflow definitions in the database.
"""

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


class CreateWorkflowRequest(BaseModel):
    """Request body for creating a workflow definition."""

    name: str
    definition_json: str
    workflow_type: str = "workflow"
    project_id: str | None = None
    description: str | None = None
    version: str = "1.0"
    enabled: bool = True
    priority: int = 100
    sources: list[str] | None = None
    canvas_json: str | None = None
    source: str = "custom"
    tags: list[str] | None = None


class UpdateWorkflowRequest(BaseModel):
    """Request body for updating a workflow definition."""

    name: str | None = None
    definition_json: str | None = None
    workflow_type: str | None = None
    description: str | None = None
    version: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    sources: list[str] | None = None
    canvas_json: str | None = None
    tags: list[str] | None = None


class ImportYAMLRequest(BaseModel):
    """Request body for importing a workflow from YAML."""

    yaml_content: str
    project_id: str | None = None


class DuplicateRequest(BaseModel):
    """Request body for duplicating a workflow."""

    new_name: str


def create_workflows_router(server: "HTTPServer") -> APIRouter:
    """
    Create workflows router with endpoints bound to server instance.

    Args:
        server: HTTPServer instance for accessing state and dependencies

    Returns:
        Configured APIRouter with workflow definition endpoints
    """
    router = APIRouter(prefix="/api/workflows", tags=["workflows"])
    metrics = get_metrics_collector()

    def _get_manager() -> Any:
        from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager

        return LocalWorkflowDefinitionManager(server.services.database)

    @router.get("/templates")
    async def list_templates() -> dict[str, Any]:
        """List available workflow templates for the 'New' button."""
        from gobby.workflows.workflow_templates import get_workflow_templates

        metrics.inc_counter("http_requests_total")
        templates = get_workflow_templates()
        return {"status": "success", "templates": templates, "count": len(templates)}

    @router.get("")
    async def list_workflows(
        workflow_type: str | None = Query(None),
        enabled: bool | None = Query(None),
        project_id: str | None = Query(None),
    ) -> dict[str, Any]:
        """List workflow definitions with optional filters."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            rows = manager.list_all(
                project_id=project_id,
                workflow_type=workflow_type,
                enabled=enabled,
            )
            return {
                "status": "success",
                "definitions": [r.to_dict() for r in rows],
                "count": len(rows),
            }
        except Exception as e:
            logger.error(f"Error listing workflow definitions: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/{definition_id}/export")
    async def export_workflow(definition_id: str) -> Response:
        """Export a workflow definition as YAML."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            yaml_content = manager.export_to_yaml(definition_id)
            return Response(
                content=yaml_content,
                media_type="application/x-yaml",
                headers={"Content-Disposition": f'attachment; filename="{definition_id}.yaml"'},
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Error exporting workflow definition: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/{definition_id}")
    async def get_workflow(definition_id: str) -> dict[str, Any]:
        """Get a workflow definition by ID."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            row = manager.get(definition_id)
            return {"status": "success", "definition": row.to_dict()}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Error getting workflow definition: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/import")
    async def import_workflow(request: ImportYAMLRequest) -> dict[str, Any]:
        """Import a workflow definition from YAML content."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            row = manager.import_from_yaml(request.yaml_content, project_id=request.project_id)
            return {"status": "success", "definition": row.to_dict()}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Error importing workflow definition: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/{definition_id}/duplicate")
    async def duplicate_workflow(definition_id: str, request: DuplicateRequest) -> dict[str, Any]:
        """Duplicate a workflow definition with a new name."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            row = manager.duplicate(definition_id, request.new_name)
            return {"status": "success", "definition": row.to_dict()}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Error duplicating workflow definition: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("")
    async def create_workflow(request: CreateWorkflowRequest) -> dict[str, Any]:
        """Create a new workflow definition."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            row = manager.create(
                name=request.name,
                definition_json=request.definition_json,
                workflow_type=request.workflow_type,
                project_id=request.project_id,
                description=request.description,
                version=request.version,
                enabled=request.enabled,
                priority=request.priority,
                sources=request.sources,
                canvas_json=request.canvas_json,
                source=request.source,
                tags=request.tags,
            )
            return {"status": "success", "definition": row.to_dict()}
        except Exception as e:
            logger.error(f"Error creating workflow definition: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.put("/{definition_id}/toggle")
    async def toggle_workflow(definition_id: str) -> dict[str, Any]:
        """Toggle a workflow definition's enabled status."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            row = manager.get(definition_id)
            updated = manager.update(definition_id, enabled=not row.enabled)
            return {"status": "success", "definition": updated.to_dict()}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Error toggling workflow definition: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.put("/{definition_id}")
    async def update_workflow(definition_id: str, request: UpdateWorkflowRequest) -> dict[str, Any]:
        """Update a workflow definition."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            fields = request.model_dump(exclude_unset=True)
            if not fields:
                raise HTTPException(status_code=400, detail="No fields to update")
            row = manager.update(definition_id, **fields)
            return {"status": "success", "definition": row.to_dict()}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating workflow definition: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.delete("/{definition_id}")
    async def delete_workflow(definition_id: str) -> dict[str, Any]:
        """Delete a workflow definition."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            deleted = manager.delete(definition_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="Definition not found")
            return {"status": "success", "deleted": True}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting workflow definition: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    return router
