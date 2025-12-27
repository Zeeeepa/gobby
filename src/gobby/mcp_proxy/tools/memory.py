"""
Internal MCP tools for Gobby Memory System.

Exposes functionality for:
- Storing memories (remember)
- Retrieving memories (recall)
- Deleting memories (forget)

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool).
"""

from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.memory.manager import MemoryManager


def create_memory_registry(memory_manager: MemoryManager) -> InternalToolRegistry:
    """
    Create a memory tool registry with all memory-related tools.

    Args:
        memory_manager: MemoryManager instance

    Returns:
        InternalToolRegistry with memory tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-memory",
        description="Memory management - remember, recall, forget",
    )

    @registry.tool(
        name="remember",
        description="Store a new memory.",
    )
    def remember(
        content: str,
        memory_type: str = "fact",
        importance: float = 0.5,
        project_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Store a new memory.

        Args:
            content: The memory content to store
            memory_type: Type of memory (fact, preference, etc)
            importance: Importance score (0.0-1.0)
            project_id: Optional project ID to associate with
            tags: Optional list of tags
        """
        try:
            memory = memory_manager.remember(
                content=content,
                memory_type=memory_type,
                importance=importance,
                project_id=project_id,
                tags=tags,
                source_type="mcp_tool",
            )
            return {
                "success": True,
                "memory": {
                    "id": memory.id,
                    "content": memory.content,
                    "type": memory.memory_type,
                    "importance": memory.importance,
                    "tags": memory.tags,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="recall",
        description="Recall memories based on query and filters.",
    )
    def recall(
        query: str | None = None,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
    ) -> dict[str, Any]:
        """
        Recall memories.

        Args:
            query: Search query string
            project_id: Optional project to filter by
            limit: Maximum number of memories to return
            min_importance: Minimum importance threshold
        """
        try:
            memories = memory_manager.recall(
                query=query,
                project_id=project_id,
                limit=limit,
                min_importance=min_importance,
            )
            return {
                "success": True,
                "memories": [
                    {
                        "id": m.id,
                        "content": m.content,
                        "type": m.memory_type,
                        "importance": m.importance,
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
        name="forget",
        description="Delete a memory by ID.",
    )
    def forget(memory_id: str) -> dict[str, Any]:
        """
        Delete a memory by ID.

        Args:
            memory_id: The ID of the memory to delete
        """
        try:
            success = memory_manager.forget(memory_id)
            if success:
                return {"success": True, "message": f"Memory {memory_id} deleted"}
            else:
                return {"success": False, "error": f"Memory {memory_id} not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    return registry
