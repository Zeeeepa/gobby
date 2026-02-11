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
        description="Artifact management - search, list, get, save, delete, tag, timeline",
    )

    def _enrich_with_tags(artifact_dicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Add tags to each artifact dict (returns new list, no mutation)."""
        return [{**d, "tags": _artifact_manager.get_tags(d["id"])} for d in artifact_dicts]

    @registry.tool(
        name="search_artifacts",
        description="Search artifacts by content using full-text search. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def search_artifacts(
        query: str,
        session_id: str | None = None,
        artifact_type: str | None = None,
        task_id: str | None = None,
        tag: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Search artifacts by content using FTS5 full-text search.

        Args:
            query: Search query text
            session_id: Optional session reference (accepts #N, N, UUID, or prefix) to filter by
            artifact_type: Optional artifact type to filter by (code, diff, error, etc.)
            task_id: Optional task ID to filter by
            tag: Optional tag to filter by
            limit: Maximum number of results (default: 50)

        Returns:
            Dict with success status and list of matching artifacts with tags
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

            # Apply post-search filters for task_id and tag
            if task_id:
                artifacts = [a for a in artifacts if a.task_id == task_id]
            if tag:
                tag_set = {a.id for a in _artifact_manager.list_by_tag(tag)}
                artifacts = [a for a in artifacts if a.id in tag_set]

            result_dicts = _enrich_with_tags([a.to_dict() for a in artifacts])
            return {
                "success": True,
                "artifacts": result_dicts,
                "count": len(result_dicts),
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
        task_id: str | None = None,
        tag: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        List artifacts with optional filters.

        Args:
            session_id: Optional session reference (accepts #N, N, UUID, or prefix) to filter by
            artifact_type: Optional artifact type to filter by
            task_id: Optional task ID to filter by
            tag: Optional tag to filter by
            limit: Maximum number of results (default: 100)
            offset: Offset for pagination (default: 0)

        Returns:
            Dict with success status and list of artifacts with tags
        """
        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        resolved_session_id = session_id
        if session_id:
            try:
                resolved_session_id = _resolve_session_id(session_id)
            except ValueError as e:
                return {"success": False, "error": str(e), "artifacts": []}

        try:
            # If filtering by tag, use list_by_tag and apply other filters
            if tag:
                artifacts = _artifact_manager.list_by_tag(tag, limit=limit, offset=offset)
                if resolved_session_id:
                    artifacts = [a for a in artifacts if a.session_id == resolved_session_id]
                if artifact_type:
                    artifacts = [a for a in artifacts if a.artifact_type == artifact_type]
                if task_id:
                    artifacts = [a for a in artifacts if a.task_id == task_id]
            else:
                artifacts = _artifact_manager.list_artifacts(
                    session_id=resolved_session_id,
                    artifact_type=artifact_type,
                    limit=limit,
                    offset=offset,
                )
                if task_id:
                    artifacts = [a for a in artifacts if a.task_id == task_id]

            result_dicts = _enrich_with_tags([a.to_dict() for a in artifacts])
            return {
                "success": True,
                "artifacts": result_dicts,
                "count": len(result_dicts),
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
            artifact_dict = artifact.to_dict()
            artifact_dict["tags"] = _artifact_manager.get_tags(artifact_id)
            return {"success": True, "artifact": artifact_dict}
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
            return {"error": str(e), "artifacts": []}

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
            result_dicts = _enrich_with_tags([a.to_dict() for a in artifacts])
            return {
                "success": True,
                "artifacts": result_dicts,
                "count": len(result_dicts),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "artifacts": []}

    @registry.tool(
        name="save_artifact",
        description="Save an artifact explicitly. Auto-classifies type if not provided. Accepts #N, N, UUID, or prefix for session_id.",
    )
    def save_artifact(
        content: str,
        session_id: str,
        artifact_type: str | None = None,
        title: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        source_file: str | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
    ) -> dict[str, Any]:
        """
        Save an artifact explicitly.

        Args:
            content: The artifact content (required)
            session_id: Session reference (accepts #N, N, UUID, or prefix) (required)
            artifact_type: Type of artifact. If omitted, auto-classified from content.
            title: Optional human-readable title
            task_id: Optional task ID to link this artifact to
            metadata: Optional metadata dict
            source_file: Optional source file path
            line_start: Optional starting line number
            line_end: Optional ending line number

        Returns:
            Dict with success status and created artifact
        """
        # Resolve session_id
        resolved_session_id = session_id
        try:
            resolved_session_id = _resolve_session_id(session_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        # Auto-classify if no type provided
        if not artifact_type:
            from gobby.storage.artifact_classifier import classify_artifact

            classification = classify_artifact(content)
            artifact_type = classification.artifact_type.value
            # Merge classification metadata with provided metadata
            if classification.metadata:
                if metadata:
                    merged = classification.metadata.copy()
                    merged.update(metadata)
                    metadata = merged
                else:
                    metadata = classification.metadata

        try:
            artifact = _artifact_manager.create_artifact(
                session_id=resolved_session_id,
                artifact_type=artifact_type,
                content=content,
                metadata=metadata,
                source_file=source_file,
                line_start=line_start,
                line_end=line_end,
                title=title,
                task_id=task_id,
            )
            return {"success": True, "artifact": artifact.to_dict()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="delete_artifact",
        description="Delete an artifact by ID.",
    )
    def delete_artifact(artifact_id: str) -> dict[str, Any]:
        """
        Delete an artifact by its ID.

        Args:
            artifact_id: The artifact ID to delete

        Returns:
            Dict with success status
        """
        try:
            deleted = _artifact_manager.delete_artifact(artifact_id)
            if not deleted:
                return {
                    "success": False,
                    "error": f"Artifact '{artifact_id}' not found",
                }
            return {"success": True, "deleted": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="tag_artifact",
        description="Add a tag to an artifact.",
    )
    def tag_artifact(artifact_id: str, tag: str) -> dict[str, Any]:
        """
        Add a tag to an artifact.

        Args:
            artifact_id: The artifact ID
            tag: The tag to add

        Returns:
            Dict with success status
        """
        try:
            _artifact_manager.add_tag(artifact_id, tag)
            return {"success": True, "artifact_id": artifact_id, "tag": tag}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="untag_artifact",
        description="Remove a tag from an artifact.",
    )
    def untag_artifact(artifact_id: str, tag: str) -> dict[str, Any]:
        """
        Remove a tag from an artifact.

        Args:
            artifact_id: The artifact ID
            tag: The tag to remove

        Returns:
            Dict with success status
        """
        try:
            removed = _artifact_manager.remove_tag(artifact_id, tag)
            if not removed:
                return {
                    "success": False,
                    "error": f"Tag '{tag}' not found on artifact '{artifact_id}'",
                }
            return {"success": True, "artifact_id": artifact_id, "tag": tag}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="list_artifacts_by_task",
        description="List artifacts linked to a specific task.",
    )
    def list_artifacts_by_task(
        task_id: str,
        artifact_type: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        List artifacts linked to a specific task.

        Args:
            task_id: The task ID to filter by (required)
            artifact_type: Optional artifact type filter
            limit: Maximum number of results (default: 100)

        Returns:
            Dict with success status and list of artifacts
        """
        try:
            artifacts = _artifact_manager.list_by_task(
                task_id=task_id,
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

    return registry
