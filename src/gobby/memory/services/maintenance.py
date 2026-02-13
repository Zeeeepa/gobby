"""Memory maintenance functions: stats, decay, and export.

Extracted from manager.py as part of Strangler Fig decomposition (Wave 2).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.config.persistence import MemoryConfig
    from gobby.memory.mem0_client import Mem0Client
    from gobby.storage.database import DatabaseProtocol
    from gobby.storage.memories import LocalMemoryManager, Memory

logger = logging.getLogger(__name__)


def get_stats(
    storage: LocalMemoryManager,
    db: DatabaseProtocol,
    mem0_client: Mem0Client | None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Get statistics about stored memories.

    Args:
        storage: Local memory storage manager.
        db: Database connection for mem0 sync queries.
        mem0_client: Mem0 client (or None if standalone mode).
        project_id: Optional project to filter stats by.

    Returns:
        Dictionary with memory statistics.
    """
    memories = storage.list_memories(project_id=project_id, limit=10000)

    if not memories:
        return {
            "total_count": 0,
            "by_type": {},
            "avg_importance": 0.0,
            "project_id": project_id,
        }

    by_type: dict[str, int] = {}
    total_importance = 0.0

    for m in memories:
        by_type[m.memory_type] = by_type.get(m.memory_type, 0) + 1
        total_importance += m.importance

    stats: dict[str, Any] = {
        "total_count": len(memories),
        "by_type": by_type,
        "avg_importance": round(total_importance / len(memories), 3),
        "project_id": project_id,
    }

    # Mem0 sync observability
    if mem0_client:
        try:
            rows = db.fetchall("SELECT COUNT(*) as cnt FROM memories WHERE mem0_id IS NULL", ())
            pending = rows[0]["cnt"] if rows else 0
            stats["mem0_sync"] = {"pending": pending}
        except Exception:
            stats["mem0_sync"] = {"pending": -1}

    return stats


def decay_memories(config: MemoryConfig, storage: LocalMemoryManager) -> int:
    """Apply importance decay to all memories.

    Args:
        config: Memory configuration with decay settings.
        storage: Local memory storage manager.

    Returns:
        Number of memories updated.
    """
    if not config.decay_enabled:
        return 0

    rate = config.decay_rate
    floor = config.decay_floor

    count = 0
    memories = storage.list_memories(min_importance=floor + 0.001, limit=10000)

    for memory in memories:
        last_update = datetime.fromisoformat(memory.updated_at)
        if last_update.tzinfo is None:
            last_update = last_update.replace(tzinfo=UTC)
        hours_since = (datetime.now(UTC) - last_update).total_seconds() / 3600

        if hours_since < 24:
            continue

        months_passed = hours_since / (24 * 30)
        decay_amount = rate * months_passed

        if decay_amount < 0.001:
            continue

        new_importance = max(floor, memory.importance - decay_amount)

        if new_importance != memory.importance:
            storage.update_memory(
                memory.id,
                importance=new_importance,
            )
            count += 1

    return count


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
        include_metadata: Include memory metadata (type, importance, tags).
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
    lines.append(f"- **Importance:** {memory.importance}")

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
