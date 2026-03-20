"""Blast radius / impact analysis tool for code index.

Exposes transitive dependency traversal as an MCP tool,
cross-referenced with task affected files.
"""

from __future__ import annotations

import logging
from typing import Any

from gobby.mcp_proxy.tools.code._context import CodeRegistryContext
from gobby.mcp_proxy.tools.internal import InternalToolRegistry

logger = logging.getLogger(__name__)


def create_impact_registry(ctx: CodeRegistryContext) -> InternalToolRegistry:
    """Create the impact analysis sub-registry."""
    registry = InternalToolRegistry(
        name="gobby-code-impact",
        description="Blast radius and impact analysis tools",
    )

    @registry.tool(
        description=(
            "Analyze the blast radius of changing a symbol or file. "
            "Walks the call/import graph transitively to find all affected code, "
            "then cross-references with task affected files. "
            "Provide exactly one of symbol_name or file_path."
        ),
    )
    async def blast_radius(
        symbol_name: str = "",
        file_path: str = "",
        depth: int = 3,
        include_tasks: bool = True,
        project_id: str = "",
    ) -> dict[str, Any]:
        """Analyze blast radius of changing a symbol or file."""
        if not symbol_name and not file_path:
            return {"error": "Provide exactly one of symbol_name or file_path"}
        if symbol_name and file_path:
            return {"error": "Provide exactly one of symbol_name or file_path, not both"}

        pid = project_id or ctx.project_id or ""

        # Check graph availability
        if ctx.graph is None or not ctx.graph.available:
            return {
                "warning": "Graph not available (Neo4j not configured)",
                "query": {
                    "symbol_name": symbol_name or None,
                    "file_path": file_path or None,
                    "depth": depth,
                },
                "summary": {
                    "affected_symbols": 0,
                    "affected_files": 0,
                    "affected_tasks": 0,
                    "max_distance": 0,
                },
                "affected_files": [],
            }

        # Run transitive traversal
        raw_results = await ctx.graph.find_blast_radius(
            symbol_name=symbol_name or None,
            file_path=file_path or None,
            project_id=pid,
            depth=depth,
        )

        # Group by file path
        files_map: dict[str, dict[str, Any]] = {}
        for r in raw_results:
            fp = r.get("file_path") or "unknown"
            if fp not in files_map:
                files_map[fp] = {
                    "file_path": fp,
                    "min_distance": r.get("distance", 1),
                    "symbols": [],
                    "tasks": [],
                }
            entry = files_map[fp]
            entry["min_distance"] = min(entry["min_distance"], r.get("distance", 1))

            # Only add symbol info if present (import-only results lack symbol_id)
            if r.get("symbol_id"):
                entry["symbols"].append({
                    "symbol_id": r["symbol_id"],
                    "symbol_name": r.get("symbol_name", ""),
                    "kind": r.get("kind", ""),
                    "distance": r.get("distance", 1),
                })

        # Cross-reference with tasks
        all_task_ids: set[str] = set()
        if include_tasks and ctx.db is not None:
            try:
                from gobby.storage.task_affected_files import TaskAffectedFileManager

                af_manager = TaskAffectedFileManager(ctx.db)
                for fp, entry in files_map.items():
                    if fp == "unknown":
                        continue
                    task_files = af_manager.get_tasks_for_file(fp)
                    for tf in task_files:
                        entry["tasks"].append({
                            "task_id": tf.task_id,
                            "annotation_source": tf.annotation_source,
                        })
                        all_task_ids.add(tf.task_id)
            except Exception as e:
                logger.debug(f"Task cross-reference failed: {e}")

        # Build sorted file list
        affected_files = sorted(
            files_map.values(),
            key=lambda f: (f["min_distance"], f["file_path"]),
        )

        # Count unique symbols
        total_symbols = sum(len(f["symbols"]) for f in affected_files)
        max_distance = max(
            (f["min_distance"] for f in affected_files), default=0
        )

        return {
            "query": {
                "symbol_name": symbol_name or None,
                "file_path": file_path or None,
                "depth": depth,
            },
            "summary": {
                "affected_symbols": total_symbols,
                "affected_files": len(affected_files),
                "affected_tasks": len(all_task_ids),
                "max_distance": max_distance,
            },
            "affected_files": affected_files,
        }

    return registry
