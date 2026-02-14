"""Memory maintenance functions: stats and export.

Extracted from manager.py as part of Strangler Fig decomposition (Wave 2).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.memory.vectorstore import VectorStore
    from gobby.storage.database import DatabaseProtocol
    from gobby.storage.memories import LocalMemoryManager, Memory

logger = logging.getLogger(__name__)


def get_stats(
    storage: LocalMemoryManager,
    db: DatabaseProtocol,
    project_id: str | None = None,
    vector_store: VectorStore | None = None,
) -> dict[str, Any]:
    """Get statistics about stored memories.

    Args:
        storage: Local memory storage manager.
        db: Database connection.
        project_id: Optional project to filter stats by.
        vector_store: Optional VectorStore for vector count stats.

    Returns:
        Dictionary with memory statistics.
    """
    memories = storage.list_memories(project_id=project_id, limit=10000)

    if not memories:
        return {
            "total_count": 0,
            "by_type": {},
            "project_id": project_id,
        }

    by_type: dict[str, int] = {}

    for m in memories:
        by_type[m.memory_type] = by_type.get(m.memory_type, 0) + 1

    stats: dict[str, Any] = {
        "total_count": len(memories),
        "by_type": by_type,
        "project_id": project_id,
    }

    # Vector store count
    if vector_store is not None:
        try:
            stats["vector_count"] = vector_store.count_sync()
        except Exception:
            stats["vector_count"] = -1

    return stats


def export_markdown(
    storage: LocalMemoryManager,
    project_id: str | None = None,
    include_metadata: bool = True,
    include_stats: bool = True,
) -> str:
    """Export memories as a formatted markdown document.

    Args:
        storage: Local memory storage manager.
        project_id: Filter by project ID (None for all memories).
        include_metadata: Include memory metadata (type, tags).
        include_stats: Include summary statistics at the top.

    Returns:
        Formatted markdown string with all memories.
    """
    memories = storage.list_memories(project_id=project_id, limit=10000)

    lines: list[str] = []

    lines.append("# Memory Export")
    lines.append("")

    if include_stats:
        now = datetime.now(UTC)
        lines.append(f"**Exported:** {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        lines.append(f"**Total memories:** {len(memories)}")
        if project_id:
            lines.append(f"**Project:** {project_id}")

        if memories:
            by_type: dict[str, int] = {}
            for m in memories:
                by_type[m.memory_type] = by_type.get(m.memory_type, 0) + 1
            type_str = ", ".join(f"{k}: {v}" for k, v in sorted(by_type.items()))
            lines.append(f"**By type:** {type_str}")

        lines.append("")
        lines.append("---")
        lines.append("")

    for memory in memories:
        short_id = memory.id[:8] if len(memory.id) > 8 else memory.id
        lines.append(f"## Memory: {short_id}")
        lines.append("")

        lines.append(memory.content)
        lines.append("")

        if include_metadata:
            _append_metadata(lines, memory)

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _append_metadata(lines: list[str], memory: Memory) -> None:
    """Append memory metadata lines to the export."""
    lines.append(f"- **Type:** {memory.memory_type}")

    if memory.tags:
        tags_str = ", ".join(memory.tags)
        lines.append(f"- **Tags:** {tags_str}")

    if memory.source_type:
        lines.append(f"- **Source:** {memory.source_type}")

    try:
        created = datetime.fromisoformat(memory.created_at)
        created_str = created.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        created_str = memory.created_at
    lines.append(f"- **Created:** {created_str}")

    if memory.access_count > 0:
        lines.append(f"- **Accessed:** {memory.access_count} times")

    lines.append("")
