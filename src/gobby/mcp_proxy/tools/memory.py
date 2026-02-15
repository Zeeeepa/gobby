"""
Internal MCP tools for Gobby Memory System.

Exposes functionality for:
- Creating memories (create_memory)
- Searching memories (search_memories)
- Deleting memories (delete_memory)
- Listing memories (list_memories)
- Getting memory details (get_memory)
- Updating memories (update_memory)
- Memory statistics (memory_stats)

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.memory.manager import MemoryManager

if TYPE_CHECKING:
    from gobby.llm.service import LLMService

logger = logging.getLogger(__name__)


# Helper to get current project context
def get_current_project_id() -> str | None:
    """Get the current project ID from context, or None if not in a project."""
    from gobby.utils.project_context import get_project_context

    ctx = get_project_context()
    if ctx and ctx.get("id"):
        return str(ctx["id"])
    return None


def create_memory_registry(
    memory_manager: MemoryManager,
    llm_service: LLMService | None = None,
) -> InternalToolRegistry:
    """
    Create a memory tool registry with all memory-related tools.

    Args:
        memory_manager: MemoryManager instance
        llm_service: LLM service for AI-powered extraction (optional)

    Returns:
        InternalToolRegistry with memory tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-memory",
        description="Memory management - create_memory, search_memories, delete_memory, get_related_memories",
    )

    @registry.tool(
        name="create_memory",
        description="Create a new memory. Returns similar existing memories to help detect duplicates.",
    )
    async def create_memory(
        content: str,
        memory_type: str = "fact",
        tags: list[str] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new memory.

        Args:
            content: The memory content to store
            memory_type: Type of memory (fact, preference, etc)
            tags: Optional list of tags
            session_id: Session ID that created this memory (accepts #N, N, UUID, or prefix)
        """
        try:
            project_id = get_current_project_id()

            # Resolve session_id to UUID before passing to storage layer
            # (memories.source_session_id has FK constraint on sessions.id)
            resolved_session_id: str | None = None
            if session_id:
                try:
                    from gobby.storage.session_resolution import resolve_session_reference

                    resolved_session_id = resolve_session_reference(
                        memory_manager.db, session_id, project_id
                    )
                except Exception as e:
                    logger.warning(f"Could not resolve session_id '{session_id}': {e}")

            memory = await memory_manager.create_memory(
                content=content,
                memory_type=memory_type,
                project_id=project_id,
                tags=tags,
                source_type="mcp_tool",
                source_session_id=resolved_session_id,
            )

            # Search for similar existing memories to surface potential duplicates
            similar_existing: list[dict[str, Any]] = []
            try:
                similar = await memory_manager.search_memories(
                    query=content,
                    project_id=project_id,
                    limit=4,  # fetch 4 since the new memory itself may appear
                )
                for m in similar:
                    if m.id != memory.id:
                        similar_existing.append(
                            {
                                "id": m.id,
                                "content": m.content,
                                "similarity": getattr(m, "similarity", None),
                            }
                        )
                similar_existing = similar_existing[:3]
            except Exception as e:
                logger.debug(
                    "Similarity search failed during memory creation "
                    "(project_id=%s, memory_id=%s): %s",
                    project_id,
                    memory.id,
                    e,
                    exc_info=True,
                )

            return {
                "success": True,
                "memory": {
                    "id": memory.id,
                },
                "similar_existing": similar_existing,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="search_memories",
        description="Search memories based on query and filters. Supports tag-based filtering.",
    )
    async def search_memories(
        query: str | None = None,
        limit: int = 10,
        tags_all: list[str] | None = None,
        tags_any: list[str] | None = None,
        tags_none: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Search memories based on query and filters.

        Args:
            query: Search query string
            limit: Maximum number of memories to return
            tags_all: Memory must have ALL of these tags
            tags_any: Memory must have at least ONE of these tags
            tags_none: Memory must have NONE of these tags
        """
        try:
            memories = await memory_manager.search_memories(
                query=query,
                project_id=get_current_project_id(),
                limit=limit,
                tags_all=tags_all,
                tags_any=tags_any,
                tags_none=tags_none,
            )
            return {
                "success": True,
                "memories": [
                    {
                        "id": m.id,
                        "content": m.content,
                        "type": m.memory_type,
                        "created_at": m.created_at,
                        "tags": m.tags,
                        "similarity": getattr(m, "similarity", None),  # Might be added by search
                    }
                    for m in memories
                ],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="delete_memory",
        description="Delete a memory by ID.",
    )
    async def delete_memory(memory_id: str) -> dict[str, Any]:
        """
        Delete a memory by ID.

        Args:
            memory_id: The ID of the memory to delete
        """
        try:
            success = await memory_manager.delete_memory(memory_id)
            if success:
                return {"success": True}
            else:
                return {"success": False, "error": f"Memory {memory_id} not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="list_memories",
        description="List all memories with optional filtering. Supports tag-based filtering.",
    )
    def list_memories(
        memory_type: str | None = None,
        limit: int = 50,
        tags_all: list[str] | None = None,
        tags_any: list[str] | None = None,
        tags_none: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        List all memories with optional filtering.

        Args:
            memory_type: Filter by memory type (fact, preference, pattern, context)
            limit: Maximum number of memories to return
            tags_all: Memory must have ALL of these tags
            tags_any: Memory must have at least ONE of these tags
            tags_none: Memory must have NONE of these tags
        """
        try:
            memories = memory_manager.list_memories(
                project_id=get_current_project_id(),
                memory_type=memory_type,
                limit=limit,
                tags_all=tags_all,
                tags_any=tags_any,
                tags_none=tags_none,
            )
            return {
                "success": True,
                "memories": [
                    {
                        "id": m.id,
                        "content": m.content,
                        "type": m.memory_type,
                        "created_at": m.created_at,
                        "tags": m.tags,
                    }
                    for m in memories
                ],
                "count": len(memories),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="get_memory",
        description="Get details of a specific memory by ID.",
    )
    def get_memory(memory_id: str) -> dict[str, Any]:
        """
        Get details of a specific memory.

        Args:
            memory_id: The ID of the memory to retrieve
        """
        try:
            memory = memory_manager.get_memory(memory_id)
            if memory:
                return {
                    "success": True,
                    "memory": {
                        "id": memory.id,
                        "content": memory.content,
                        "type": memory.memory_type,
                        "created_at": memory.created_at,
                        "updated_at": memory.updated_at,
                        "project_id": memory.project_id,
                        "source_type": memory.source_type,
                        "access_count": memory.access_count,
                        "tags": memory.tags,
                    },
                }
            else:
                return {"success": False, "error": f"Memory {memory_id} not found"}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="get_related_memories",
        description="Get memories related to a specific memory via cross-references.",
    )
    async def get_related_memories(
        memory_id: str,
        limit: int = 5,
        min_similarity: float = 0.0,
    ) -> dict[str, Any]:
        """
        Get memories linked to a specific memory via cross-references.

        Cross-references are automatically created based on semantic similarity
        when memories are stored (if auto_crossref is enabled in config).

        Args:
            memory_id: The ID of the memory to find related memories for
            limit: Maximum number of related memories to return
            min_similarity: Minimum similarity threshold (0.0-1.0)
        """
        try:
            memories = await memory_manager.get_related(
                memory_id=memory_id,
                limit=limit,
                min_similarity=min_similarity,
            )
            return {
                "success": True,
                "memory_id": memory_id,
                "related": [
                    {
                        "id": m.id,
                        "content": m.content,
                        "type": m.memory_type,
                        "created_at": m.created_at,
                        "tags": m.tags,
                    }
                    for m in memories
                ],
                "count": len(memories),
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="update_memory",
        description="Update an existing memory's content or tags.",
    )
    async def update_memory(
        memory_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Update an existing memory.

        Args:
            memory_id: The ID of the memory to update
            content: New content (optional)
            tags: New list of tags (optional)
        """
        try:
            memory = await memory_manager.update_memory(
                memory_id=memory_id,
                content=content,
                tags=tags,
            )
            return {
                "success": True,
                "memory": {
                    "id": memory.id,
                    "updated_at": memory.updated_at,
                },
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="remember_with_image",
        description="Create a memory from an image. Uses LLM to describe the image and stores it with the description.",
    )
    async def remember_with_image(
        image_path: str,
        context: str | None = None,
        memory_type: str = "fact",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create a memory from an image file.

        Uses the configured LLM provider to generate a description of the image,
        then stores the memory with the description as content and the image
        as a media attachment.

        Args:
            image_path: Path to the image file
            context: Optional context to guide the image description (e.g., "This is a screenshot of an error")
            memory_type: Type of memory (fact, preference, etc)
            tags: Optional list of tags
        """
        if not llm_service:
            return {
                "success": False,
                "error": "LLM service not configured. Image memories require an LLM provider.",
            }

        try:
            memory = await memory_manager.remember_with_image(
                image_path=image_path,
                context=context,
                memory_type=memory_type,
                project_id=get_current_project_id(),
                tags=tags,
                source_type="mcp_tool",
            )
            return {
                "success": True,
                "memory": {
                    "id": memory.id,
                    "content": memory.content,
                    "media_path": image_path,
                },
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="remember_screenshot",
        description="Create a memory from raw screenshot bytes (base64 encoded). Saves to .gobby/resources/ and describes with LLM.",
    )
    async def remember_screenshot(
        screenshot_base64: str,
        context: str | None = None,
        memory_type: str = "observation",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create a memory from raw screenshot bytes.

        Saves the screenshot to .gobby/resources/ with a timestamp-based filename,
        uses LLM to describe it, and stores the memory with the description.

        Args:
            screenshot_base64: Base64-encoded PNG screenshot bytes
            context: Optional context to guide the image description
            memory_type: Type of memory (default: "observation")
            tags: Optional list of tags
        """
        import base64

        if not llm_service:
            return {
                "success": False,
                "error": "LLM service not configured. Screenshot memories require an LLM provider.",
            }

        try:
            # Decode base64 to bytes
            screenshot_bytes = base64.b64decode(screenshot_base64)

            memory = await memory_manager.remember_screenshot(
                screenshot_bytes=screenshot_bytes,
                context=context,
                memory_type=memory_type,
                project_id=get_current_project_id(),
                tags=tags,
                source_type="mcp_tool",
            )
            return {
                "success": True,
                "memory": {
                    "id": memory.id,
                    "content": memory.content,
                },
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="memory_stats",
        description="Get statistics about the memory system.",
    )
    def memory_stats() -> dict[str, Any]:
        """
        Get statistics about stored memories.
        """
        try:
            stats = memory_manager.get_stats(project_id=get_current_project_id())
            return {"success": True, "stats": stats}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="search_knowledge_graph",
        description="Search the Neo4j knowledge graph for entities matching a query.",
    )
    async def search_knowledge_graph(
        query: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Search the knowledge graph for entities matching a query.

        Args:
            query: Search query string
            limit: Maximum number of results to return
        """
        try:
            kg_service = memory_manager.kg_service
            if not kg_service:
                return {"success": True, "results": []}

            results = await kg_service.search_graph(query, limit=limit)
            return {"success": True, "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    return registry
