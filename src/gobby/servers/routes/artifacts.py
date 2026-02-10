"""
Artifact routes for Gobby HTTP server.

Provides list, search, get, delete, tag, and stats endpoints for artifacts.
"""

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer
    from gobby.storage.artifacts import LocalArtifactManager

logger = logging.getLogger(__name__)


class TagRequest(BaseModel):
    """Request body for adding a tag."""

    tag: str = Field(..., description="Tag to add")


def create_artifacts_router(server: "HTTPServer") -> APIRouter:
    """Create artifacts router with endpoints bound to server instance."""
    router = APIRouter(prefix="/artifacts", tags=["artifacts"])

    def _get_manager() -> "LocalArtifactManager":
        """Lazy-create artifact manager from server's DB."""
        from gobby.storage.artifacts import LocalArtifactManager

        cached = getattr(server, "_artifact_manager", None)
        if isinstance(cached, LocalArtifactManager):
            return cached
        mcp_mgr = server.services.mcp_db_manager
        if mcp_mgr is None:
            raise HTTPException(status_code=503, detail="Database not available")
        db = mcp_mgr.db
        manager = LocalArtifactManager(db)
        server._artifact_manager = manager  # type: ignore[attr-defined]
        return manager

    def _enrich_with_tags(artifact_dicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Add tags to each artifact dict."""
        manager = _get_manager()
        for d in artifact_dicts:
            d["tags"] = manager.get_tags(d["id"])
        return artifact_dicts

    @router.get("")
    async def list_artifacts(
        session_id: str | None = Query(None, description="Filter by session ID"),
        task_id: str | None = Query(None, description="Filter by task ID"),
        artifact_type: str | None = Query(None, description="Filter by artifact type"),
        tag: str | None = Query(None, description="Filter by tag"),
        limit: int = Query(100, description="Maximum results"),
        offset: int = Query(0, description="Pagination offset"),
    ) -> dict[str, Any]:
        """List artifacts with optional filters."""
        manager = _get_manager()
        if tag:
            artifacts = manager.list_by_tag(tag, limit=limit, offset=offset)
            if session_id:
                artifacts = [a for a in artifacts if a.session_id == session_id]
            if artifact_type:
                artifacts = [a for a in artifacts if a.artifact_type == artifact_type]
            if task_id:
                artifacts = [a for a in artifacts if a.task_id == task_id]
        else:
            artifacts = manager.list_artifacts(
                session_id=session_id,
                artifact_type=artifact_type,
                limit=limit,
                offset=offset,
            )
            if task_id:
                artifacts = [a for a in artifacts if a.task_id == task_id]

        result_dicts = _enrich_with_tags([a.to_dict() for a in artifacts])
        return {"artifacts": result_dicts, "count": len(result_dicts)}

    @router.get("/search")
    async def search_artifacts(
        q: str = Query(..., description="Search query"),
        session_id: str | None = Query(None, description="Filter by session ID"),
        task_id: str | None = Query(None, description="Filter by task ID"),
        artifact_type: str | None = Query(None, description="Filter by type"),
        tag: str | None = Query(None, description="Filter by tag"),
        limit: int = Query(50, description="Maximum results"),
    ) -> dict[str, Any]:
        """Full-text search across artifact content."""
        manager = _get_manager()
        artifacts = manager.search_artifacts(
            query_text=q,
            session_id=session_id,
            artifact_type=artifact_type,
            limit=limit,
        )
        if task_id:
            artifacts = [a for a in artifacts if a.task_id == task_id]
        if tag:
            tag_ids = {a.id for a in manager.list_by_tag(tag)}
            artifacts = [a for a in artifacts if a.id in tag_ids]

        result_dicts = _enrich_with_tags([a.to_dict() for a in artifacts])
        return {"query": q, "artifacts": result_dicts, "count": len(result_dicts)}

    @router.get("/stats")
    async def artifact_stats(
        session_id: str | None = Query(None, description="Filter by session ID"),
    ) -> dict[str, Any]:
        """Get aggregate artifact statistics."""
        manager = _get_manager()
        all_artifacts = manager.list_artifacts(session_id=session_id, limit=10000)

        by_type: dict[str, int] = {}
        by_session: dict[str, int] = {}
        for a in all_artifacts:
            by_type[a.artifact_type] = by_type.get(a.artifact_type, 0) + 1
            by_session[a.session_id] = by_session.get(a.session_id, 0) + 1

        return {
            "total_count": len(all_artifacts),
            "by_type": by_type,
            "by_session": by_session,
        }

    @router.get("/timeline/{session_id}")
    async def get_timeline(
        session_id: str,
        artifact_type: str | None = Query(None, description="Filter by type"),
        limit: int = Query(100, description="Maximum results"),
    ) -> dict[str, Any]:
        """Get artifacts for a session in chronological order."""
        manager = _get_manager()
        artifacts = manager.list_artifacts(
            session_id=session_id,
            artifact_type=artifact_type,
            limit=limit,
        )
        # Reverse to chronological (oldest first)
        artifacts = list(reversed(artifacts))
        result_dicts = _enrich_with_tags([a.to_dict() for a in artifacts])
        return {"session_id": session_id, "artifacts": result_dicts, "count": len(result_dicts)}

    @router.get("/{artifact_id}")
    async def get_artifact(artifact_id: str) -> dict[str, Any]:
        """Get a single artifact by ID."""
        manager = _get_manager()
        artifact = manager.get_artifact(artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        artifact_dict = artifact.to_dict()
        artifact_dict["tags"] = manager.get_tags(artifact_id)
        return artifact_dict

    @router.delete("/{artifact_id}")
    async def delete_artifact(artifact_id: str) -> dict[str, Any]:
        """Delete an artifact."""
        manager = _get_manager()
        deleted = manager.delete_artifact(artifact_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return {"deleted": True, "id": artifact_id}

    @router.post("/{artifact_id}/tags", status_code=201)
    async def add_tag(artifact_id: str, request_data: TagRequest) -> dict[str, Any]:
        """Add a tag to an artifact."""
        manager = _get_manager()
        artifact = manager.get_artifact(artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        manager.add_tag(artifact_id, request_data.tag)
        return {"artifact_id": artifact_id, "tag": request_data.tag}

    @router.delete("/{artifact_id}/tags/{tag}")
    async def remove_tag(artifact_id: str, tag: str) -> dict[str, Any]:
        """Remove a tag from an artifact."""
        manager = _get_manager()
        removed = manager.remove_tag(artifact_id, tag)
        if not removed:
            raise HTTPException(status_code=404, detail="Tag not found")
        return {"artifact_id": artifact_id, "tag": tag, "removed": True}

    return router
