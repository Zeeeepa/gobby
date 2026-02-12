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
        from gobby.storage.agent_definitions import LocalAgentDefinitionManager

        return LocalAgentDefinitionManager(server.services.database)

    def _get_loader() -> Any:
        from gobby.agents.definitions import AgentDefinitionLoader

        return AgentDefinitionLoader(db=server.services.database)

    @router.get("/definitions")
    async def list_definitions(
        project_id: str | None = Query(None),
    ) -> dict[str, Any]:
        """List all agent definitions (merged from files + DB, with source tags)."""
        metrics.inc_counter("http_requests_total")
        try:
            loader = _get_loader()
            items = loader.list_all(project_id=project_id)
            return {
                "status": "success",
                "definitions": [i.to_api_dict() for i in items],
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
            loader = _get_loader()
            items = loader.list_all(project_id=project_id)
            match = next((i for i in items if i.definition.name == name), None)
            if not match:
                raise HTTPException(status_code=404, detail=f"Agent definition '{name}' not found")

            # For file-based agents, read the original YAML (preserves comments)
            if match.source_path:
                from pathlib import Path

                source = Path(match.source_path)
                if source.exists():
                    yaml_content = source.read_text(encoding="utf-8")
                else:
                    # Fall back to model serialization
                    data = match.definition.model_dump(exclude_none=True)
                    yaml_content = yaml.dump(data, default_flow_style=False, sort_keys=False)
            else:
                # DB-backed: serialize from model
                data = match.definition.model_dump(exclude_none=True)
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
        """Get a single agent definition resolved per priority order."""
        metrics.inc_counter("http_requests_total")
        try:
            loader = _get_loader()
            items = loader.list_all(project_id=project_id)
            match = next((i for i in items if i.definition.name == name), None)
            if not match:
                raise HTTPException(status_code=404, detail=f"Agent definition '{name}' not found")
            return {"status": "success", "definition": match.to_api_dict()}
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
            manager = _get_manager()
            row = manager.create(
                name=request.name,
                project_id=request.project_id,
                description=request.description,
                role=request.role,
                goal=request.goal,
                personality=request.personality,
                instructions=request.instructions,
                provider=request.provider,
                model=request.model,
                mode=request.mode,
                terminal=request.terminal,
                isolation=request.isolation,
                base_branch=request.base_branch,
                timeout=request.timeout,
                max_turns=request.max_turns,
                default_workflow=request.default_workflow,
                sandbox_config=request.sandbox_config,
                skill_profile=request.skill_profile,
                workflows=request.workflows,
                lifecycle_variables=request.lifecycle_variables,
                default_variables=request.default_variables,
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
            logger.error(f"Error updating agent definition: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.delete("/definitions/{definition_id}")
    async def delete_definition(definition_id: str) -> dict[str, Any]:
        """Delete a DB-backed agent definition."""
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
            if status == "running":
                runs = manager.list_running(limit=limit)
            else:
                # Get recent runs across all sessions
                rows = server.services.database.fetchall(
                    """
                    SELECT * FROM agent_runs
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                from gobby.storage.agents import AgentRun

                runs = [AgentRun.from_row(row) for row in rows]
                if status:
                    runs = [r for r in runs if r.status == status]
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

            # Also update DB status
            from gobby.storage.agents import LocalAgentRunManager

            db_manager = LocalAgentRunManager(server.services.database)
            db_manager.cancel(run_id)

            return {"status": "success", "result": result}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error cancelling agent run '{run_id}': {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/definitions/import/{name}")
    async def import_definition(
        name: str,
        project_id: str | None = Query(None),
    ) -> dict[str, Any]:
        """Copy a file-based agent definition into the DB for customization."""
        metrics.inc_counter("http_requests_total")
        try:
            from gobby.agents.definitions import AgentDefinitionLoader

            # Load from files only (no DB fallback)
            file_loader = AgentDefinitionLoader()
            defn = file_loader.load(name)
            if not defn:
                raise HTTPException(
                    status_code=404,
                    detail=f"File-based agent definition '{name}' not found",
                )
            manager = _get_manager()
            row = manager.import_from_definition(defn, project_id=project_id)
            return {"status": "success", "definition": row.to_dict()}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error importing agent definition '{name}': {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    return router
