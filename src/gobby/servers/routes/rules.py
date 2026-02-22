"""
Rule routes for Gobby HTTP server.

Provides CRUD endpoints for standalone rules stored as workflow_definitions
with workflow_type='rule'. Wraps LocalWorkflowDefinitionManager with
rule-specific filtering and validation.
"""

import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from gobby.mcp_proxy.tools.workflows._rules import (
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    toggle_rule,
)
from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer
    from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager

logger = logging.getLogger(__name__)


# =============================================================================
# Request models
# =============================================================================


class RuleCreateRequest(BaseModel):
    """Request body for creating a rule."""

    name: str = Field(..., description="Rule name (must be unique)")
    definition: dict[str, Any] = Field(
        ..., description="Rule definition (event, effect, optional when/group/match)"
    )


class RuleUpdateRequest(BaseModel):
    """Request body for updating a rule."""

    description: str | None = Field(default=None, description="New description")
    enabled: bool | None = Field(default=None, description="New enabled state")
    priority: int | None = Field(default=None, description="New priority")
    tags: list[str] | None = Field(default=None, description="New tags")


class RuleToggleRequest(BaseModel):
    """Request body for toggling a rule."""

    enabled: bool = Field(..., description="New enabled state")


# =============================================================================
# Router
# =============================================================================


def create_rules_router(server: "HTTPServer") -> APIRouter:
    """Create rules router with endpoints bound to server instance."""
    router = APIRouter(prefix="/api/rules", tags=["rules"])
    metrics = get_metrics_collector()

    def _get_manager() -> "LocalWorkflowDefinitionManager":
        from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager

        return LocalWorkflowDefinitionManager(server.services.database)

    # -----------------------------------------------------------------
    # GET /api/rules/groups (must be before /{name} to avoid conflict)
    # -----------------------------------------------------------------

    @router.get("/groups")
    async def list_groups() -> dict[str, Any]:
        """List distinct rule groups."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            rows = manager.list_all(workflow_type="rule")
            groups: set[str] = set()
            for row in rows:
                body = json.loads(row.definition_json)
                group = body.get("group")
                if group:
                    groups.add(group)
            return {
                "status": "success",
                "groups": sorted(groups),
            }
        except Exception as e:
            logger.exception("Error listing rule groups")
            raise HTTPException(status_code=500, detail=str(e)) from e

    # -----------------------------------------------------------------
    # GET /api/rules
    # -----------------------------------------------------------------

    @router.get("")
    async def list_rules_endpoint(
        event: str | None = Query(None, description="Filter by event type"),
        group: str | None = Query(None, description="Filter by group"),
        enabled: bool | None = Query(None, description="Filter by enabled status"),
    ) -> dict[str, Any]:
        """List rules with optional filters."""
        metrics.inc_counter("http_requests_total")
        try:
            manager = _get_manager()
            result = list_rules(manager, event=event, group=group, enabled=enabled)
            return {"status": "success", "rules": result["rules"], "count": result["count"]}
        except Exception as e:
            logger.exception("Error listing rules")
            raise HTTPException(status_code=500, detail=str(e)) from e

    # -----------------------------------------------------------------
    # POST /api/rules
    # -----------------------------------------------------------------

    @router.post("", status_code=201)
    async def create_rule_endpoint(request: RuleCreateRequest) -> dict[str, Any]:
        """Create a new rule."""
        metrics.inc_counter("http_requests_total")
        manager = _get_manager()
        result = create_rule(manager, name=request.name, definition=request.definition)

        if not result["success"]:
            error = result["error"]
            if "already exists" in error.lower():
                raise HTTPException(status_code=409, detail=error)
            raise HTTPException(status_code=400, detail=error)

        return {"status": "success", "rule": result["rule"]}

    # -----------------------------------------------------------------
    # GET /api/rules/{name}
    # -----------------------------------------------------------------

    @router.get("/{name}")
    async def get_rule_endpoint(name: str) -> dict[str, Any]:
        """Get a rule by name."""
        metrics.inc_counter("http_requests_total")
        manager = _get_manager()
        result = get_rule(manager, name=name)

        if not result["success"]:
            raise HTTPException(status_code=404, detail=result["error"])

        return {"status": "success", "rule": result["rule"]}

    # -----------------------------------------------------------------
    # PUT /api/rules/{name}
    # -----------------------------------------------------------------

    @router.put("/{name}")
    async def update_rule_endpoint(name: str, request: RuleUpdateRequest) -> dict[str, Any]:
        """Update rule fields."""
        metrics.inc_counter("http_requests_total")
        manager = _get_manager()

        row = manager.get_by_name(name)
        if row is None or row.workflow_type != "rule":
            raise HTTPException(status_code=404, detail=f"Rule '{name}' not found")

        fields = request.model_dump(exclude_unset=True)
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        try:
            updated = manager.update(row.id, **fields)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

        body = json.loads(updated.definition_json)
        return {
            "status": "success",
            "rule": {
                "id": updated.id,
                "name": updated.name,
                "event": body.get("event"),
                "group": body.get("group"),
                "enabled": updated.enabled,
                "priority": updated.priority,
                "description": updated.description,
                "source": updated.source,
                "tags": updated.tags,
            },
        }

    # -----------------------------------------------------------------
    # DELETE /api/rules/{name}
    # -----------------------------------------------------------------

    @router.delete("/{name}")
    async def delete_rule_endpoint(
        name: str,
        force: bool = Query(False, description="Override bundled protection"),
    ) -> dict[str, Any]:
        """Soft-delete a rule. Bundled rules are protected unless force=True."""
        metrics.inc_counter("http_requests_total")
        manager = _get_manager()
        result = delete_rule(manager, name=name, force=force)

        if not result["success"]:
            error = result["error"]
            if "not found" in error.lower():
                raise HTTPException(status_code=404, detail=error)
            if "bundled" in error.lower():
                raise HTTPException(status_code=403, detail=error)
            raise HTTPException(status_code=400, detail=error)

        return {"status": "success", "deleted": result["deleted"]}

    # -----------------------------------------------------------------
    # PUT /api/rules/{name}/toggle
    # -----------------------------------------------------------------

    @router.put("/{name}/toggle")
    async def toggle_rule_endpoint(name: str, request: RuleToggleRequest) -> dict[str, Any]:
        """Toggle a rule's enabled state."""
        metrics.inc_counter("http_requests_total")
        manager = _get_manager()
        result = toggle_rule(manager, name=name, enabled=request.enabled)

        if not result["success"]:
            raise HTTPException(status_code=404, detail=result["error"])

        return {"status": "success", "rule": result["rule"]}

    return router
