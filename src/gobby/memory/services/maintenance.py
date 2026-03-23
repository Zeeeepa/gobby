"""Memory maintenance functions: stats, export, and cleanup.

Extracted from manager.py as part of Strangler Fig decomposition (Wave 2).
Cleanup functions added for nightly memory hygiene pipeline (#10572).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.memory.manager import MemoryManager
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
            "recent_count": 0,
            "project_id": project_id,
        }

    by_type: dict[str, int] = {}
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    recent_count = 0

    for m in memories:
        by_type[m.memory_type] = by_type.get(m.memory_type, 0) + 1
        try:
            created = datetime.fromisoformat(m.created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            if created > cutoff:
                recent_count += 1
        except (ValueError, AttributeError, TypeError):
            pass

    stats: dict[str, Any] = {
        "total_count": len(memories),
        "by_type": by_type,
        "recent_count": recent_count,
        "project_id": project_id,
    }

    # Vector store count — use sync Qdrant client to avoid async issues
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


# ---------------------------------------------------------------------------
# Cleanup functions for nightly memory hygiene (#10572)
# ---------------------------------------------------------------------------

# Patterns that indicate a memory is just describing code structure.
# These memories can be re-derived by reading the codebase.
_CODE_DERIVABLE_PATTERNS: list[re.Pattern[str]] = [
    # "File X contains ...", "The file X has ..."
    re.compile(
        r"^(?:the\s+)?file\s+[`'\"]?[\w./-]+[`'\"]?\s+(?:contains?|has|defines?|exports?|includes?)",
        re.IGNORECASE,
    ),
    # "Function/method/class X is defined in Y"
    re.compile(
        r"^(?:the\s+)?(?:function|method|class|module|variable|constant)\s+[`'\"]?\w+[`'\"]?\s+"
        r"(?:is\s+)?(?:defined|located|found|declared)\s+in",
        re.IGNORECASE,
    ),
    # "The directory X contains ..."
    re.compile(
        r"^(?:the\s+)?directory\s+[`'\"]?[\w./-]+[`'\"]?\s+(?:contains?|has|holds)",
        re.IGNORECASE,
    ),
    # "X is imported from Y" / "import X from Y"
    re.compile(
        r"^(?:the\s+)?(?:import|from)\s+[`'\"]?[\w./-]+[`'\"]?",
        re.IGNORECASE,
    ),
    # Bare file path (just a path, nothing else)
    re.compile(r"^[`'\"]?[\w./-]+\.(?:py|ts|tsx|js|jsx|yaml|yml|json|toml|md|rs|go)[`'\"]?\s*$"),
]

# Maximum content length for code-derivable heuristic — longer memories
# are more likely to contain substantive context beyond code structure.
_CODE_DERIVABLE_MAX_LEN = 200


def find_stale_memories(
    db: DatabaseProtocol,
    max_age_days: int = 30,
    project_id: str | None = None,
    limit: int = 500,
) -> list[Memory]:
    """Find memories that have never been accessed and are older than max_age_days.

    Args:
        db: Database connection.
        max_age_days: Memories older than this with 0 access_count are stale.
        project_id: Optional project filter.
        limit: Maximum results to return.

    Returns:
        List of stale Memory objects.
    """
    from gobby.storage.memories import Memory

    cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()

    if project_id:
        rows = db.fetchall(
            """SELECT * FROM memories
               WHERE access_count = 0
                 AND created_at < ?
                 AND (project_id = ? OR project_id IS NULL)
               ORDER BY created_at ASC
               LIMIT ?""",
            (cutoff, project_id, limit),
        )
    else:
        rows = db.fetchall(
            """SELECT * FROM memories
               WHERE access_count = 0
                 AND created_at < ?
               ORDER BY created_at ASC
               LIMIT ?""",
            (cutoff, limit),
        )

    return [Memory.from_row(row) for row in rows]


async def find_duplicate_memories(
    storage: LocalMemoryManager,
    vector_store: VectorStore,
    embed_fn: Callable[..., Any],
    project_id: str | None = None,
    similarity_threshold: float = 0.95,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Find near-duplicate memory pairs using vector similarity.

    For each pair, determines which to keep (higher access_count, then more
    recent updated_at) and which to delete.

    Args:
        storage: Local memory storage.
        vector_store: VectorStore for similarity search.
        embed_fn: Embedding function.
        project_id: Optional project filter.
        similarity_threshold: Minimum similarity score for duplicates.
        limit: Maximum memories to scan.

    Returns:
        List of dicts: {keep_id, delete_id, score, delete_content_preview}.
    """
    import asyncio

    memories = storage.list_memories(project_id=project_id, limit=limit)
    if not memories:
        return []

    duplicates: list[dict[str, Any]] = []
    seen_delete_ids: set[str] = set()

    for i, memory in enumerate(memories):
        if memory.id in seen_delete_ids:
            continue

        try:
            embedding = await embed_fn(memory.content)
            filters = {"project_id": project_id} if project_id else None
            results = await vector_store.search(
                query_embedding=embedding,
                limit=5,
                filters=filters,
            )
        except Exception as e:
            logger.warning(f"Duplicate scan failed for {memory.id}: {e}")
            continue

        for match_id, score in results:
            if match_id == memory.id or match_id in seen_delete_ids:
                continue
            if score < similarity_threshold:
                continue

            # Determine which to keep
            try:
                match = storage.get_memory(match_id)
            except ValueError:
                continue

            # Keep the one with higher access_count; tie-break by updated_at
            if (memory.access_count, memory.updated_at) >= (
                match.access_count,
                match.updated_at,
            ):
                keep, delete = memory, match
            else:
                keep, delete = match, memory

            seen_delete_ids.add(delete.id)
            duplicates.append(
                {
                    "keep_id": keep.id,
                    "delete_id": delete.id,
                    "score": round(score, 4),
                    "delete_content_preview": delete.content[:120],
                }
            )

        # Yield to event loop periodically
        if i % 10 == 9:
            await asyncio.sleep(0)

    return duplicates


def find_code_derivable_memories(
    storage: LocalMemoryManager,
    project_id: str | None = None,
    limit: int = 500,
) -> list[Memory]:
    """Find memories whose content just describes code structure.

    Uses regex heuristics to detect memories like "File X contains function Y"
    that can be re-derived from the codebase. Only flags short memories
    (< _CODE_DERIVABLE_MAX_LEN chars) to avoid false positives on longer
    memories that may contain substantive design context.

    Args:
        storage: Local memory storage.
        project_id: Optional project filter.
        limit: Maximum memories to scan.

    Returns:
        List of code-derivable Memory objects.
    """
    memories = storage.list_memories(project_id=project_id, limit=limit)
    results: list[Memory] = []

    for memory in memories:
        content = memory.content.strip()
        if len(content) > _CODE_DERIVABLE_MAX_LEN:
            continue
        if any(pattern.match(content) for pattern in _CODE_DERIVABLE_PATTERNS):
            results.append(memory)

    return results


def find_orphaned_memories(
    db: DatabaseProtocol,
    min_age_days: int = 30,
    project_id: str | None = None,
    limit: int = 500,
) -> list[Memory]:
    """Find memories whose source session no longer exists.

    Only flags orphaned memories that are also old (> min_age_days), since
    a recently created memory whose session was cleaned up is still likely
    valuable.

    Args:
        db: Database connection.
        min_age_days: Only flag orphans older than this many days.
        project_id: Optional project filter.
        limit: Maximum results to return.

    Returns:
        List of orphaned Memory objects.
    """
    from gobby.storage.memories import Memory

    cutoff = (datetime.now(UTC) - timedelta(days=min_age_days)).isoformat()

    params: list[Any] = [cutoff]
    project_clause = ""
    if project_id:
        project_clause = "AND (m.project_id = ? OR m.project_id IS NULL)"
        params.append(project_id)
    params.append(limit)

    rows = db.fetchall(
        f"""SELECT m.* FROM memories m
            LEFT JOIN sessions s ON m.source_session_id = s.id
            WHERE m.source_session_id IS NOT NULL
              AND s.id IS NULL
              AND m.created_at < ?
              {project_clause}
            ORDER BY m.created_at ASC
            LIMIT ?""",  # nosec B608
        tuple(params),
    )

    return [Memory.from_row(row) for row in rows]


async def execute_cleanup(
    memory_manager: MemoryManager,
    dry_run: bool = False,
    categories: list[str] | None = None,
    max_stale_age_days: int = 30,
    similarity_threshold: float = 0.95,
    limit_per_category: int = 500,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Run the full memory cleanup pipeline.

    Finds stale, duplicate, code-derivable, and orphaned memories, then
    optionally deletes them via MemoryManager (which handles SQLite, Qdrant,
    and Neo4j cleanup).

    Args:
        memory_manager: MemoryManager instance (for delete + vector access).
        dry_run: If True, report what would be cleaned without deleting.
        categories: Which categories to clean. None = all four.
            Valid values: "stale", "duplicates", "code_derivable", "orphaned".
        max_stale_age_days: Age threshold for stale/orphaned memories.
        similarity_threshold: Vector similarity threshold for duplicates.
        limit_per_category: Max memories to scan per category.
        project_id: Optional project filter.

    Returns:
        Structured report dict with per-category results and totals.
    """
    all_categories = {"stale", "duplicates", "code_derivable", "orphaned"}
    active = set(categories) if categories else all_categories
    # Validate
    invalid = active - all_categories
    if invalid:
        return {"error": f"Invalid categories: {invalid}. Valid: {all_categories}"}

    report: dict[str, Any] = {"dry_run": dry_run}
    delete_ids: dict[str, str] = {}  # id -> category (first found)

    # --- Stale ---
    if "stale" in active:
        stale = await asyncio.to_thread(
            find_stale_memories,
            db=memory_manager.db,
            max_age_days=max_stale_age_days,
            project_id=project_id,
            limit=limit_per_category,
        )
        report["stale"] = {
            "found": len(stale),
            "items": [{"id": m.id, "content_preview": m.content[:120]} for m in stale],
        }
        for m in stale:
            if m.id not in delete_ids:
                delete_ids[m.id] = "stale"

    # --- Duplicates ---
    if "duplicates" in active:
        if memory_manager.vector_store and memory_manager.embed_fn:
            dupes = await find_duplicate_memories(
                storage=memory_manager.storage,
                vector_store=memory_manager.vector_store,
                embed_fn=memory_manager.embed_fn,
                project_id=project_id,
                similarity_threshold=similarity_threshold,
                limit=limit_per_category,
            )
        else:
            dupes = []
            logger.info("Skipping duplicate scan: VectorStore or embed_fn unavailable")
        report["duplicates"] = {
            "found": len(dupes),
            "items": dupes,
        }
        for d in dupes:
            did = d["delete_id"]
            if did not in delete_ids:
                delete_ids[did] = "duplicates"

    # --- Code-derivable ---
    if "code_derivable" in active:
        derivable = find_code_derivable_memories(
            storage=memory_manager.storage,
            project_id=project_id,
            limit=limit_per_category,
        )
        report["code_derivable"] = {
            "found": len(derivable),
            "items": [{"id": m.id, "content_preview": m.content[:120]} for m in derivable],
        }
        for m in derivable:
            if m.id not in delete_ids:
                delete_ids[m.id] = "code_derivable"

    # --- Orphaned ---
    if "orphaned" in active:
        orphaned = await asyncio.to_thread(
            find_orphaned_memories,
            db=memory_manager.db,
            min_age_days=max_stale_age_days,
            project_id=project_id,
            limit=limit_per_category,
        )
        report["orphaned"] = {
            "found": len(orphaned),
            "items": [{"id": m.id, "content_preview": m.content[:120]} for m in orphaned],
        }
        for m in orphaned:
            if m.id not in delete_ids:
                delete_ids[m.id] = "orphaned"

    report["total_found"] = len(delete_ids)

    # --- Execute deletions ---
    if dry_run or not delete_ids:
        report["total_deleted"] = 0
    else:
        deleted = 0
        errors = 0
        deleted_per_category: dict[str, int] = {}
        for memory_id in delete_ids:
            # Re-check stale memories haven't been accessed since the scan
            category = delete_ids[memory_id]
            if category == "stale":
                try:
                    mem = memory_manager.storage.get_memory(memory_id)
                    if mem.access_count > 0:
                        logger.debug(f"Skipping {memory_id}: accessed since scan")
                        continue
                except ValueError:
                    continue  # Already gone

            try:
                result = await memory_manager.delete_memory(memory_id)
                if result:
                    deleted += 1
                    deleted_per_category[category] = deleted_per_category.get(category, 0) + 1
            except Exception as e:
                logger.warning(f"Failed to delete memory {memory_id}: {e}")
                errors += 1

        report["total_deleted"] = deleted
        if errors:
            report["delete_errors"] = errors

        # Add per-category deleted counts to their report sections
        for cat, count in deleted_per_category.items():
            if cat in report:
                report[cat]["deleted"] = count

    return report
