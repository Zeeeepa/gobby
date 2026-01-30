"""
Internal MCP tools for Gobby Artifacts System.

Exposes functionality for:
- search_artifacts: Full-text search across artifact content
- list_artifacts: List artifacts with session_id and type filters
- get_artifact: Get a single artifact by ID
- get_timeline: Get artifacts for a session in chronological order

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry

if TYPE_CHECKING:
    from gobby.storage.artifacts import LocalArtifactManager
    from gobby.storage.database import DatabaseProtocol


def create_artifacts_registry(
    db: DatabaseProtocol | None = None,
    artifact_manager: LocalArtifactManager | None = None,
    session_manager: Any | None = None,
) -> InternalToolRegistry:
    """
    Create an artifacts tool registry with all artifact-related tools.

    Args:
        db: DatabaseProtocol instance (used to create artifact_manager if not provided)
        artifact_manager: LocalArtifactManager instance
        session_manager: Session manager for resolving session references

    Returns:
        InternalToolRegistry with artifact tools registered
    """
    from gobby.utils.project_context import get_project_context

    def _resolve_session_id(ref: str) -> str:
        """Resolve session reference (#N, N, UUID, or prefix) to UUID."""
        if session_manager is None:
            return ref  # No resolution available, return as-is
        ctx = get_project_context()
        project_id = ctx.get("id") if ctx else None
        return str(session_manager.resolve_session_reference(ref, project_id))

    # Create artifact manager if not provided
    if artifact_manager is None:
        if db is None:
            from gobby.storage.database import LocalDatabase

            db = LocalDatabase()
        from gobby.storage.artifacts import LocalArtifactManager

        artifact_manager = LocalArtifactManager(db)

    _artifact_manager = artifact_manager

    registry = InternalToolRegistry(
        name="gobby-artifacts",
        description="Artifact management - search, list, get, timeline",
    )

    @registry.tool(
        name="search_artifacts",
        description="Search artifacts by content using full-text search. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def search_artifacts(
        query: str,
        session_id: str | None = None,
        artifact_type: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Search artifacts by content using FTS5 full-text search.

        Args:
            query: Search query text
            session_id: Optional session reference (accepts #N, N, UUID, or prefix) to filter by
            artifact_type: Optional artifact type to filter by (code, diff, error, etc.)
            limit: Maximum number of results (default: 50)

        Returns:
            Dict with success status and list of matching artifacts
        """
        if not query or not query.strip():
            return {"success": True, "artifacts": [], "count": 0}

        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        resolved_session_id = session_id
        if session_id:
            try:
                resolved_session_id = _resolve_session_id(session_id)
            except ValueError as e:
                return {"success": False, "error": str(e), "artifacts": []}

        try:
            artifacts = _artifact_manager.search_artifacts(
                query_text=query,
                session_id=resolved_session_id,
                artifact_type=artifact_type,
                limit=limit,
            )
            return {
                "success": True,
                "artifacts": [a.to_dict() for a in artifacts],
                "count": len(artifacts),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "artifacts": []}

    @registry.tool(
        name="list_artifacts",
        description="List artifacts with optional filters. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def list_artifacts(
        session_id: str | None = None,
        artifact_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        List artifacts with optional filters.

        Args:
            session_id: Optional session reference (accepts #N, N, UUID, or prefix) to filter by
            artifact_type: Optional artifact type to filter by
            limit: Maximum number of results (default: 100)
            offset: Offset for pagination (default: 0)

        Returns:
            Dict with success status and list of artifacts
        """
        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        resolved_session_id = session_id
        if session_id:
            try:
                resolved_session_id = _resolve_session_id(session_id)
            except ValueError as e:
                return {"success": False, "error": str(e), "artifacts": []}

        try:
            artifacts = _artifact_manager.list_artifacts(
                session_id=resolved_session_id,
                artifact_type=artifact_type,
                limit=limit,
                offset=offset,
            )
            return {
                "success": True,
                "artifacts": [a.to_dict() for a in artifacts],
                "count": len(artifacts),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "artifacts": []}

    @registry.tool(
        name="get_artifact",
        description="Get a single artifact by ID.",
    )
    def get_artifact(artifact_id: str) -> dict[str, Any]:
        """
        Get a single artifact by its ID.

        Args:
            artifact_id: The artifact ID to retrieve

        Returns:
            Dict with success status and artifact data
        """
        try:
            artifact = _artifact_manager.get_artifact(artifact_id)
            if artifact is None:
                return {
                    "success": False,
                    "error": f"Artifact '{artifact_id}' not found",
                    "artifact": None,
                }
            return {
                "success": True,
                "artifact": artifact.to_dict(),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "artifact": None}

    @registry.tool(
        name="get_timeline",
        description="Get artifacts for a session in chronological order. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def get_timeline(
        session_id: str | None = None,
        artifact_type: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Get artifacts for a session in chronological order (oldest first).

        Args:
            session_id: Required session reference (accepts #N, N, UUID, or prefix) to get timeline for
            artifact_type: Optional artifact type to filter by
            limit: Maximum number of results (default: 100)

        Returns:
            Dict with success status and chronologically ordered artifacts
        """
        if not session_id:
            return {
                "success": False,
                "error": "session_id is required for timeline",
                "artifacts": [],
            }

        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        try:
            resolved_session_id = _resolve_session_id(session_id)
        except ValueError as e:
            return {"success": False, "error": str(e), "artifacts": []}

        try:
            # Get artifacts (list_artifacts returns newest first by default)
            artifacts = _artifact_manager.list_artifacts(
                session_id=resolved_session_id,
                artifact_type=artifact_type,
                limit=limit,
                offset=0,
            )
            # Reverse to get chronological order (oldest first)
            artifacts = list(reversed(artifacts))
            return {
                "success": True,
                "artifacts": [a.to_dict() for a in artifacts],
                "count": len(artifacts),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "artifacts": []}

    return registry
