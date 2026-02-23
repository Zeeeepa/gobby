"""
Agent definition routes for Gobby HTTP server.

Provides endpoints for viewing and managing agent definitions
(merged from file-based and database sources).
"""

import logging
from typing import TYPE_CHECKING, Any

import yaml
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


class CreateAgentDefinitionRequest(BaseModel):
    """Request body for creating an agent definition in the DB."""

    name: str
    project_id: str | None = None
    description: str | None = None
    role: str | None = None
    goal: str | None = None
    personality: str | None = None
    instructions: str | None = None
    provider: str = "claude"
    model: str | None = None
    mode: str = "headless"
    terminal: str = "auto"
    isolation: str | None = None
    base_branch: str = "main"
    timeout: float = 120.0
    max_turns: int = 10
    default_workflow: str | None = None
    sandbox_config: dict[str, Any] | None = None
    skill_profile: dict[str, Any] | None = None
    workflows: dict[str, Any] | None = None
    lifecycle_variables: dict[str, Any] | None = None
    default_variables: dict[str, Any] | None = None


class UpdateAgentDefinitionRequest(BaseModel):
    """Request body for updating an agent definition."""

    name: str | None = None
    description: str | None = None
    role: str | None = None
    goal: str | None = None
    personality: str | None = None
    instructions: str | None = None
    provider: str | None = None
    model: str | None = None
    mode: str | None = None
    terminal: str | None = None
    isolation: str | None = None
    base_branch: str | None = None
    timeout: float | None = None
    max_turns: int | None = None
    default_workflow: str | None = None
    sandbox_config: dict[str, Any] | None = None
    skill_profile: dict[str, Any] | None = None
    workflows: dict[str, Any] | None = None
    lifecycle_variables: dict[str, Any] | None = None
    default_variables: dict[str, Any] | None = None
    enabled: bool | None = None


def create_agents_router(server: "HTTPServer") -> APIRouter:
    """
    Create agents router with endpoints bound to server instance.

    Args:
        server: HTTPServer instance for accessing state and dependencies

    Returns:
        Configured APIRouter with agent definition endpoints
    """
    router = APIRouter(prefix="/api/agents", tags=["agents"])
    metrics = get_metrics_collector()

    def _get_manager() -> Any:
        from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager

        return LocalWorkflowDefinitionManager(server.services.database)

    def _row_to_api_dict(row: Any) -> dict[str, Any]:
        """Convert a workflow_definitions DB row to API response dict."""
        from gobby.workflows.definitions import AgentDefinitionBody

        body = AgentDefinitionBody.model_validate_json(row.definition_json)
        return {
            "definition": body.model_dump(exclude_none=True),
            "source": row.source,
            "db_id": row.id,
            "deleted_at": row.deleted_at,
        }

    @router.get("/definitions")
    async def list_definitions(
        project_id: str | None = Query(None),
        include_deleted: bool = Query(False),
    ) -> dict[str, Any]:
        """List all agent definitions from workflow_definitions."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            rows = manager.list_all(
                workflow_type="agent",
                project_id=project_id,
                include_deleted=include_deleted,
            )
            items = [_row_to_api_dict(r) for r in rows]
            return {
                "status": "success",
                "definitions": items,
                "count": len(items),
            }
        except Exception as e:
            logger.error(f"Error listing agent definitions: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/definitions/{name}/export")
    async def export_definition(
        name: str,
        project_id: str | None = Query(None),
    ) -> Response:
        """Export an agent definition as YAML for download."""
        metrics.inc_counter("http_requests_total")
        try:
            from gobby.workflows.definitions import AgentDefinitionBody

            manager = _get_manager()
            rows = manager.list_all(workflow_type="agent", project_id=project_id)
            row = next((r for r in rows if r.name == name), None)
            if not row:
                raise HTTPException(status_code=404, detail=f"Agent definition '{name}' not found")

            body = AgentDefinitionBody.model_validate_json(row.definition_json)
            data = body.model_dump(exclude_none=True)
            yaml_content = yaml.dump(data, default_flow_style=False, sort_keys=False)

            return Response(
                content=yaml_content,
                media_type="application/x-yaml",
                headers={"Content-Disposition": f'attachment; filename="{name}.yaml"'},
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error exporting agent definition '{name}': {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/definitions/{name}")
    async def get_definition(
        name: str,
        project_id: str | None = Query(None),
    ) -> dict[str, Any]:
        """Get a single agent definition by name."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            rows = manager.list_all(workflow_type="agent", project_id=project_id)
            row = next((r for r in rows if r.name == name), None)
            if not row:
                raise HTTPException(status_code=404, detail=f"Agent definition '{name}' not found")
            return {"status": "success", "definition": _row_to_api_dict(row)}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting agent definition '{name}': {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/definitions")
    async def create_definition(
        request: CreateAgentDefinitionRequest,
    ) -> dict[str, Any]:
        """Create a new agent definition in the DB."""
        metrics.inc_counter("http_requests_total")
        try:
            from gobby.workflows.definitions import AgentDefinitionBody, AgentWorkflows

            body = AgentDefinitionBody(
                name=request.name,
                description=request.description,
                role=request.role,
                goal=request.goal,
                personality=request.personality,
                instructions=request.instructions,
                provider=request.provider,
                model=request.model,
                mode=request.mode if request.mode != "self" else "headless",
                isolation=request.isolation,
                base_branch=request.base_branch,
                timeout=request.timeout,
                max_turns=request.max_turns,
                workflows=AgentWorkflows(),
            )

            manager = _get_manager()
            row = manager.create(
                name=body.name,
                definition_json=body.model_dump_json(),
                workflow_type="agent",
                project_id=request.project_id,
                description=body.description,
                source="installed",
                enabled=body.enabled,
            )
            return {"status": "success", "definition": row.to_dict()}
        except Exception as e:
            logger.error(f"Error creating agent definition: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.put("/definitions/{definition_id}")
    async def update_definition(
        definition_id: str, request: UpdateAgentDefinitionRequest
    ) -> dict[str, Any]:
        """Update a DB-backed agent definition."""
        metrics.inc_counter("http_requests_total")
        try:
            import json as _json

            manager = _get_manager()
            fields = request.model_dump(exclude_unset=True)
            if not fields:
                raise HTTPException(status_code=400, detail="No fields to update")

            # Load existing definition_json and apply updates
            row = manager.get(definition_id)
            body_dict: dict[str, Any] = _json.loads(row.definition_json)

            # Map body-level fields
            for key in (
                "name",
                "description",
                "role",
                "goal",
                "personality",
                "instructions",
                "provider",
                "model",
                "mode",
                "isolation",
                "base_branch",
                "timeout",
                "max_turns",
            ):
                if key in fields:
                    body_dict[key] = fields[key]

            update_fields: dict[str, Any] = {
                "definition_json": _json.dumps(body_dict),
            }
            if "description" in fields:
                update_fields["description"] = fields["description"]
            if "enabled" in fields:
                update_fields["enabled"] = fields["enabled"]
            if "name" in fields:
                update_fields["name"] = fields["name"]

            row = manager.update(definition_id, **update_fields)
            return {"status": "success", "definition": row.to_dict()}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating agent definition: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.delete("/definitions/{definition_id}")
    async def delete_definition(definition_id: str) -> dict[str, Any]:
        """Delete a DB-backed agent definition (soft-delete)."""
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
            logger.error(f"Error deleting agent definition: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/definitions/{definition_id}/restore")
    async def restore_definition(definition_id: str) -> dict[str, Any]:
        """Restore a soft-deleted agent definition."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            row = manager.restore(definition_id)
            return {"status": "success", "definition": row.to_dict()}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Error restoring agent definition: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    # -------------------------------------------------------------------------
    # Running agents and agent runs
    # -------------------------------------------------------------------------

    @router.get("/running")
    async def list_running_agents() -> dict[str, Any]:
        """List all currently running agents from the in-memory registry."""
        metrics.inc_counter("http_requests_total")
        try:
            from gobby.agents.registry import get_running_agent_registry

            registry = get_running_agent_registry()
            agents = registry.list_all()
            return {
                "status": "success",
                "agents": [a.to_dict() for a in agents],
                "count": len(agents),
            }
        except Exception as e:
            logger.error(f"Error listing running agents: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/runs")
    async def list_agent_runs(
        status: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
    ) -> dict[str, Any]:
        """List recent agent runs from the database."""
        metrics.inc_counter("http_requests_total")
        try:
            from gobby.storage.agents import LocalAgentRunManager

            manager = LocalAgentRunManager(server.services.database)
            runs = manager.list_by_status(status=status, limit=limit)
            return {
                "status": "success",
                "runs": [r.to_dict() for r in runs],
                "count": len(runs),
            }
        except Exception as e:
            logger.error(f"Error listing agent runs: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/runs/{run_id}/cancel")
    async def cancel_agent_run(run_id: str) -> dict[str, Any]:
        """Cancel a running agent."""
        metrics.inc_counter("http_requests_total")
        try:
            from gobby.agents.registry import get_running_agent_registry

            registry = get_running_agent_registry()
            agent = registry.get(run_id)
            if not agent:
                raise HTTPException(status_code=404, detail=f"Running agent '{run_id}' not found")

            result = await registry.kill(run_id)

            # Also update DB status — kill first since DB cancel is recoverable
            try:
                from gobby.storage.agents import LocalAgentRunManager

                db_manager = LocalAgentRunManager(server.services.database)
                db_manager.cancel(run_id)
            except Exception as e:
                logger.error(
                    f"Agent {run_id} killed in registry but DB cancel failed: {e}",
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"Agent '{run_id}' was killed in the process registry but "
                        f"the database status update failed: {e}. "
                        f"The DB record may still show 'running'. "
                        f"This will be auto-corrected by cleanup_stale_runs."
                    ),
                ) from e

            return {"status": "success", "result": result}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error cancelling agent run '{run_id}': {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/definitions/{name}/install")
    async def install_definition_from_template(
        name: str,
    ) -> dict[str, Any]:
        """Create an installed copy from a template agent definition."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            # Find the template definition by name
            rows = manager.list_all(workflow_type="agent")
            template = next(
                (r for r in rows if r.name == name and r.source == "template"),
                None,
            )
            if not template:
                raise HTTPException(
                    status_code=404,
                    detail=f"Template agent definition '{name}' not found",
                )
            row = manager.install_from_template(template.id)
            return {"status": "success", "definition": row.to_dict()}
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Error installing agent definition from template: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/definitions/import/{name}")
    async def import_definition(
        name: str,
        project_id: str | None = Query(None),
    ) -> dict[str, Any]:
        """Copy a file-based agent definition into the DB for customization."""
        metrics.inc_counter("http_requests_total")
        try:
            from gobby.agents.sync import get_bundled_agents_path
            from gobby.workflows.definitions import AgentDefinitionBody

            # Load from bundled agents directory
            agents_path = get_bundled_agents_path()
            yaml_path = agents_path / f"{name}.yaml"
            if not yaml_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"File-based agent definition '{name}' not found",
                )
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            data["name"] = data.get("name", name)
            body = AgentDefinitionBody.model_validate(data)
            manager = _get_manager()
            row = manager.create(
                name=body.name,
                definition_json=body.model_dump_json(),
                workflow_type="agent",
                project_id=project_id,
                description=body.description,
                source="installed",
                enabled=body.enabled,
            )
            return {"status": "success", "definition": row.to_dict()}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error importing agent definition '{name}': {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    return router
