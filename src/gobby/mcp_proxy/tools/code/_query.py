"""Query tools for gobby-code."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gobby.mcp_proxy.tools.code._context import CodeRegistryContext
from gobby.mcp_proxy.tools.internal import InternalToolRegistry


def create_query_registry(ctx: CodeRegistryContext) -> InternalToolRegistry:
    """Create query sub-registry."""
    registry = InternalToolRegistry(
        name="gobby-code-query",
        description="Code symbol query tools",
    )

    @registry.tool(description="File tree with symbol counts per file.")
    def get_file_tree(project_id: str = "") -> list[dict[str, Any]]:
        """Get file structure with symbol counts for an indexed project."""
        pid = project_id or ctx.project_id or "default"
        files = ctx.storage.list_files(pid)
        return [
            {
                "file_path": f.file_path,
                "language": f.language,
                "symbol_count": f.symbol_count,
                "byte_size": f.byte_size,
            }
            for f in files
        ]

    @registry.tool(description="Hierarchical symbol outline for a single file. Much cheaper than reading the file.")
    def get_file_outline(
        file_path: str,
        project_id: str = "",
    ) -> dict[str, Any]:
        """Get symbol tree for a file without reading its contents."""
        pid = project_id or ctx.project_id or "default"
        symbols = ctx.storage.get_symbols_for_file(pid, file_path)

        # If not found, try path variants
        if not symbols:
            for i in range(len(Path(file_path).parts)):
                candidate = str(Path(*Path(file_path).parts[i:]))
                symbols = ctx.storage.get_symbols_for_file(pid, candidate)
                if symbols:
                    break

        outline = []
        for sym in symbols:
            entry: dict[str, Any] = {
                "id": sym.id,
                "name": sym.name,
                "qualified_name": sym.qualified_name,
                "kind": sym.kind,
                "line_start": sym.line_start,
                "line_end": sym.line_end,
                "signature": sym.signature,
            }
            if sym.docstring:
                entry["docstring"] = sym.docstring[:200]
            if sym.summary:
                entry["summary"] = sym.summary
            if sym.parent_symbol_id:
                entry["parent_id"] = sym.parent_symbol_id
            outline.append(entry)

        return {
            "file_path": file_path,
            "symbol_count": len(outline),
            "symbols": outline,
        }

    @registry.tool(description="Get full source for a symbol by ID. O(1) retrieval via byte offsets.")
    def get_symbol(
        symbol_id: str,
        project_id: str = "",
    ) -> dict[str, Any] | str:
        """Retrieve a single symbol with its source code."""
        sym = ctx.storage.get_symbol(symbol_id)
        if sym is None:
            return f"Symbol not found: {symbol_id}"

        # Read source from file
        source = _read_symbol_source(sym, project_id or ctx.project_id)
        result = sym.to_dict()
        if source:
            result["source"] = source
        return result

    @registry.tool(description="Batch-retrieve multiple symbols by ID.")
    def get_symbols(
        symbol_ids: list[str],
        project_id: str = "",
    ) -> list[dict[str, Any]]:
        """Retrieve multiple symbols."""
        symbols = ctx.storage.get_symbols(symbol_ids)
        results = []
        for sym in symbols:
            d = sym.to_dict()
            source = _read_symbol_source(sym, project_id or ctx.project_id)
            if source:
                d["source"] = source
            results.append(d)
        return results

    @registry.tool(description="Hybrid search: name + semantic + graph. Finds symbols by description or name.")
    async def search_symbols(
        query: str,
        project_id: str = "",
        kind: str = "",
        file_path: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search for symbols using hybrid search."""
        pid = project_id or ctx.project_id or "default"
        return await ctx.searcher.search(
            query=query,
            project_id=pid,
            kind=kind or None,
            file_path=file_path or None,
            limit=limit,
        )

    @registry.tool(description="Full-text search across symbol names and signatures.")
    def search_text(
        query: str,
        project_id: str = "",
        file_path: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search symbols by text matching."""
        pid = project_id or ctx.project_id or "default"
        return ctx.searcher.search_text(
            query=query,
            project_id=pid,
            file_path=file_path or None,
            limit=limit,
        )

    def _read_symbol_source(
        sym: Any, project_id: str | None
    ) -> str | None:
        """Read symbol source from file using byte offsets."""
        # Try to find the file on disk
        # Look up project stats for root_path
        pid = project_id or sym.project_id
        project = ctx.storage.get_project_stats(pid)
        if project is None:
            return None

        file_path = Path(project.root_path) / sym.file_path
        if not file_path.exists():
            return None

        try:
            data = file_path.read_bytes()
            return data[sym.byte_start:sym.byte_end].decode(
                "utf-8", errors="replace"
            )
        except (OSError, IndexError):
            return None

    return registry
