"""Neo4j call/import graph operations for code symbols.

Wraps existing Neo4jClient with code-specific node types and relationships.
All methods return empty results if Neo4j is not available.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CodeGraph:
    """Code-specific graph operations wrapping Neo4jClient."""

    def __init__(self, neo4j_client: Any | None = None) -> None:
        self._client: Any = neo4j_client

    @property
    def available(self) -> bool:
        return self._client is not None

    async def add_relationships(
        self,
        project_id: str,
        file_path: str,
        imports: list[dict[str, Any]] | None = None,
        calls: list[dict[str, Any]] | None = None,
        contains: list[dict[str, Any]] | None = None,
    ) -> int:
        """Add import/call/contains relationships to the graph.

        Returns count of relationships added.
        """
        if not self.available:
            return 0

        count = 0
        try:
            # Add import relationships
            for imp in imports or []:
                await self._client.execute_write(
                    """MERGE (f:CodeFile {path: $source, project: $project})
                       MERGE (m:CodeModule {name: $target, project: $project})
                       MERGE (f)-[:IMPORTS]->(m)""",
                    {
                        "source": imp.get("source_file", ""),
                        "target": imp.get("target_module", ""),
                        "project": project_id,
                    },
                )
                count += 1

            # Add call relationships
            for call in calls or []:
                await self._client.execute_write(
                    """MERGE (caller:CodeSymbol {id: $caller_id, project: $project})
                       MERGE (callee:CodeSymbol {name: $callee_name, project: $project})
                       MERGE (caller)-[:CALLS {file: $file, line: $line}]->(callee)""",
                    {
                        "caller_id": call.get("caller_symbol_id", ""),
                        "callee_name": call.get("callee_name", ""),
                        "file": call.get("file_path", ""),
                        "line": call.get("line", 0),
                        "project": project_id,
                    },
                )
                count += 1

            # Add contains relationships (file contains symbol)
            for cont in contains or []:
                await self._client.execute_write(
                    """MERGE (f:CodeFile {path: $file, project: $project})
                       MERGE (s:CodeSymbol {id: $symbol_id, project: $project})
                       SET s.name = $name, s.kind = $kind
                       MERGE (f)-[:DEFINES]->(s)""",
                    {
                        "file": file_path,
                        "symbol_id": cont.get("id", ""),
                        "name": cont.get("name", ""),
                        "kind": cont.get("kind", ""),
                        "project": project_id,
                    },
                )
                count += 1

        except Exception as e:
            logger.warning(f"Graph relationship add failed: {e}")

        return count

    async def find_callers(
        self, symbol_name: str, project_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Find symbols that call the given symbol name."""
        if not self.available:
            return []

        try:
            result = await self._client.execute_read(
                """MATCH (caller:CodeSymbol)-[r:CALLS]->(callee:CodeSymbol {name: $name, project: $project})
                   RETURN caller.id AS caller_id, caller.name AS caller_name,
                          r.file AS file, r.line AS line
                   LIMIT $limit""",
                {"name": symbol_name, "project": project_id, "limit": limit},
            )
            return [dict(record) for record in result]
        except Exception as e:
            logger.debug(f"find_callers failed: {e}")
            return []

    async def find_usages(
        self, symbol_name: str, project_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Find all usages of a symbol (callers + imports)."""
        if not self.available:
            return []

        try:
            result = await self._client.execute_read(
                """MATCH (n)-[r]->(target {name: $name, project: $project})
                   WHERE type(r) IN ['CALLS', 'IMPORTS']
                   RETURN n.id AS source_id, n.name AS source_name,
                          type(r) AS rel_type, r.file AS file, r.line AS line
                   LIMIT $limit""",
                {"name": symbol_name, "project": project_id, "limit": limit},
            )
            return [dict(record) for record in result]
        except Exception as e:
            logger.debug(f"find_usages failed: {e}")
            return []

    async def get_imports(self, file_path: str, project_id: str) -> list[dict[str, Any]]:
        """Get import graph for a file."""
        if not self.available:
            return []

        try:
            result = await self._client.execute_read(
                """MATCH (f:CodeFile {path: $path, project: $project})-[:IMPORTS]->(m:CodeModule)
                   RETURN m.name AS module_name""",
                {"path": file_path, "project": project_id},
            )
            return [dict(record) for record in result]
        except Exception as e:
            logger.debug(f"get_imports failed: {e}")
            return []

    async def get_import_chain(
        self, module: str, project_id: str, depth: int = 3
    ) -> list[dict[str, Any]]:
        """Get transitive import chain for a module."""
        if not self.available:
            return []

        try:
            result = await self._client.execute_read(
                """MATCH path = (f:CodeFile)-[:IMPORTS*1..$depth]->(m:CodeModule {name: $module, project: $project})
                   UNWIND nodes(path) AS n
                   RETURN DISTINCT n.name AS name, n.path AS path, labels(n)[0] AS type""",
                {"module": module, "project": project_id, "depth": depth},
            )
            return [dict(record) for record in result]
        except Exception as e:
            logger.debug(f"get_import_chain failed: {e}")
            return []

    async def find_blast_radius(
        self,
        symbol_name: str | None,
        file_path: str | None,
        project_id: str,
        depth: int = 3,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Find the transitive blast radius of changing a symbol or file.

        Walks the call/import graph backwards to find all affected code.
        Returns list of dicts with: symbol_id, symbol_name, kind, file_path,
        distance, rel_type ('call' or 'import').
        """
        if not self.available:
            return []

        if bool(symbol_name) == bool(file_path):
            raise ValueError("Exactly one of symbol_name or file_path must be provided")

        depth = max(1, min(depth, 5))
        results: list[dict[str, Any]] = []

        try:
            if symbol_name:
                # Walk CALLS backwards from the target symbol
                records = await self._client.execute_read(
                    f"""MATCH path = (affected:CodeSymbol)-[:CALLS*1..{depth}]->(
                           target:CodeSymbol {{name: $name, project: $project}})
                       WITH affected, min(length(path)) AS distance
                       OPTIONAL MATCH (file:CodeFile)-[:DEFINES]->(affected)
                       RETURN DISTINCT affected.id AS symbol_id,
                              affected.name AS symbol_name,
                              affected.kind AS kind, file.path AS file_path,
                              distance, 'call' AS rel_type
                       ORDER BY distance ASC, affected.name ASC
                       LIMIT $limit""",
                    {
                        "name": symbol_name,
                        "project": project_id,
                        "limit": limit,
                    },
                )
                results.extend(dict(r) for r in records)
            else:
                # Walk CALLS backwards from all symbols defined in the file
                call_records = await self._client.execute_read(
                    f"""MATCH (tf:CodeFile {{path: $path, project: $project}})
                           -[:DEFINES]->(target_sym:CodeSymbol)
                       MATCH path = (affected:CodeSymbol)-[:CALLS*1..{depth}]->(target_sym)
                       WITH affected, min(length(path)) AS distance
                       OPTIONAL MATCH (file:CodeFile)-[:DEFINES]->(affected)
                       RETURN DISTINCT affected.id AS symbol_id,
                              affected.name AS symbol_name,
                              affected.kind AS kind, file.path AS file_path,
                              distance, 'call' AS rel_type
                       ORDER BY distance ASC, affected.name ASC
                       LIMIT $limit""",
                    {
                        "path": file_path,
                        "project": project_id,
                        "limit": limit,
                    },
                )
                results.extend(dict(r) for r in call_records)

                # Walk IMPORTS backwards from modules this file imports
                import_records = await self._client.execute_read(
                    f"""MATCH (tf:CodeFile {{path: $path, project: $project}})
                           -[:IMPORTS]->(m:CodeModule)
                       MATCH path = (importer:CodeFile)-[:IMPORTS*1..{depth}]->(m)
                       WHERE importer.path <> $path
                       WITH importer, min(length(path)) AS distance
                       RETURN DISTINCT importer.path AS file_path,
                              distance, 'import' AS rel_type
                       ORDER BY distance ASC
                       LIMIT $limit""",
                    {
                        "path": file_path,
                        "project": project_id,
                        "limit": limit,
                    },
                )
                results.extend(dict(r) for r in import_records)

        except Exception as e:
            logger.debug(f"find_blast_radius failed: {e}")

        return results

    # ── Visualization queries ──────────────────────────────────────

    async def get_file_graph(self, project_id: str, limit: int = 200) -> dict[str, Any]:
        """Get file-level overview graph for visualization.

        Returns CodeFile nodes connected by shared CodeModule imports,
        resolved to file-to-file edges.  Total nodes are capped at
        ``limit * 8`` to prevent 3D renderer crashes.
        """
        if not self.available:
            return {"nodes": [], "links": []}

        max_nodes = limit * 8
        link_limit = limit * 3

        try:
            # Get files and their import relationships via shared modules
            file_records = await self._client.execute_read(
                """MATCH (f:CodeFile {project: $project})
                   OPTIONAL MATCH (f)-[:DEFINES]->(s:CodeSymbol)
                   WITH f, count(DISTINCT s) AS sym_count
                   OPTIONAL MATCH (f)-[:IMPORTS]->(m)
                   WITH f, sym_count, count(m) AS imp_count
                   RETURN f.path AS id, f.path AS name, 'file' AS type,
                          f.path AS file_path, sym_count AS symbol_count
                   ORDER BY imp_count DESC, sym_count DESC, f.path
                   LIMIT $limit""",
                {"project": project_id, "limit": limit},
            )
            nodes = [dict(r) for r in file_records]
            node_ids = {n["id"] for n in nodes}

            # Get direct file→module IMPORTS edges
            import_records = await self._client.execute_read(
                """MATCH (f:CodeFile {project: $project})-[:IMPORTS]->(m:CodeModule {project: $project})
                   WHERE f.path IN $file_paths
                   RETURN f.path AS source, m.name AS target, 'IMPORTS' AS type
                   LIMIT $link_limit""",
                {
                    "project": project_id,
                    "file_paths": list(node_ids),
                    "link_limit": link_limit,
                },
            )

            links: list[dict[str, Any]] = []
            module_ids: set[str] = set()

            for r in import_records:
                rec = dict(r)
                links.append(rec)
                mid = rec["target"]
                if mid not in node_ids and mid not in module_ids:
                    if len(nodes) >= max_nodes:
                        continue
                    module_ids.add(mid)
                    nodes.append(
                        {
                            "id": mid,
                            "name": mid,
                            "type": "module",
                        }
                    )

            # Also get file→symbol DEFINES edges
            defines_records = await self._client.execute_read(
                """MATCH (f:CodeFile {project: $project})-[:DEFINES]->(s:CodeSymbol {project: $project})
                   WHERE f.path IN $file_paths
                   RETURN f.path AS source, s.id AS target, 'DEFINES' AS type,
                          s.name AS symbol_name, s.kind AS symbol_kind
                   LIMIT $link_limit""",
                {
                    "project": project_id,
                    "file_paths": list(node_ids),
                    "link_limit": link_limit,
                },
            )

            for r in defines_records:
                rec = dict(r)
                sid = rec["target"]
                links.append(
                    {
                        "source": rec["source"],
                        "target": sid,
                        "type": "DEFINES",
                    }
                )
                if sid not in node_ids and len(nodes) < max_nodes:
                    nodes.append(
                        {
                            "id": sid,
                            "name": rec.get("symbol_name", sid),
                            "type": rec.get("symbol_kind") or "function",
                            "kind": rec.get("symbol_kind"),
                            "file_path": rec["source"],
                        }
                    )

            # Add CALLS edges between symbols
            sym_ids = [n["id"] for n in nodes if n["type"] != "file" and n["type"] != "module"]
            if sym_ids:
                call_records = await self._client.execute_read(
                    """MATCH (s:CodeSymbol {project: $project})-[r:CALLS]->(t:CodeSymbol {project: $project})
                       WHERE s.id IN $sym_ids AND t.id IN $sym_ids
                       RETURN s.id AS source, t.id AS target, 'CALLS' AS type
                       LIMIT $link_limit""",
                    {
                        "project": project_id,
                        "sym_ids": sym_ids,
                        "link_limit": link_limit,
                    },
                )
                for r in call_records:
                    links.append(dict(r))

            return {"nodes": nodes, "links": links}
        except Exception as e:
            logger.debug(f"get_file_graph failed: {e}")
            return {"nodes": [], "links": []}

    async def get_file_symbols(self, file_path: str, project_id: str) -> dict[str, Any]:
        """Expand a file: its symbols + their call edges.

        Returns nodes for the file's symbols and links for DEFINES + CALLS.
        """
        if not self.available:
            return {"nodes": [], "links": []}

        try:
            # Get symbols defined in this file
            sym_records = await self._client.execute_read(
                """MATCH (f:CodeFile {path: $path, project: $project})
                          -[:DEFINES]->(s:CodeSymbol)
                   RETURN s.id AS id, s.name AS name, s.kind AS type,
                          $path AS file_path, s.kind AS kind""",
                {"path": file_path, "project": project_id},
            )
            nodes: list[dict[str, Any]] = [dict(r) for r in sym_records]
            sym_ids = {n["id"] for n in nodes}

            links: list[dict[str, Any]] = []

            # Add DEFINES edges (file -> symbol)
            for node in nodes:
                links.append(
                    {
                        "source": file_path,
                        "target": node["id"],
                        "type": "DEFINES",
                    }
                )

            # Add CALLS edges between these symbols and others
            if sym_ids:
                call_records = await self._client.execute_read(
                    """MATCH (s:CodeSymbol {project: $project})-[r:CALLS]->(t:CodeSymbol {project: $project})
                       WHERE s.id IN $sym_ids OR t.id IN $sym_ids
                       RETURN s.id AS source, t.id AS target, 'CALLS' AS type,
                              r.line AS line""",
                    {"project": project_id, "sym_ids": list(sym_ids)},
                )
                # Include callee nodes that aren't in our set yet
                for r in call_records:
                    rec = dict(r)
                    links.append(rec)
                    for field in ("source", "target"):
                        nid = rec[field]
                        if nid not in sym_ids:
                            sym_ids.add(nid)
                            nodes.append(
                                {
                                    "id": nid,
                                    "name": nid.split(":")[-1] if ":" in nid else nid,
                                    "type": "function",
                                    "kind": "function",
                                }
                            )

            return {"nodes": nodes, "links": links}
        except Exception as e:
            logger.debug(f"get_file_symbols failed: {e}")
            return {"nodes": [], "links": []}

    async def get_symbol_neighbors(
        self, symbol_id: str, project_id: str, limit: int = 50
    ) -> dict[str, Any]:
        """Expand a symbol: bidirectional callers and callees.

        Returns neighbor nodes and CALLS links.
        """
        if not self.available:
            return {"nodes": [], "links": []}

        try:
            records = await self._client.execute_read(
                """MATCH (s:CodeSymbol {id: $id, project: $project})-[r:CALLS]-(neighbor:CodeSymbol)
                   OPTIONAL MATCH (f:CodeFile)-[:DEFINES]->(neighbor)
                   RETURN neighbor.id AS id, neighbor.name AS name,
                          neighbor.kind AS kind,
                          CASE WHEN startNode(r) = s THEN 'outgoing' ELSE 'incoming' END AS direction,
                          f.path AS file_path, r.line AS line
                   LIMIT $limit""",
                {"id": symbol_id, "project": project_id, "limit": limit},
            )

            nodes: list[dict[str, Any]] = []
            links: list[dict[str, Any]] = []
            seen = set()

            for r in records:
                rec = dict(r)
                nid = rec["id"]
                if nid not in seen:
                    seen.add(nid)
                    nodes.append(
                        {
                            "id": nid,
                            "name": rec["name"],
                            "type": rec["kind"] or "function",
                            "kind": rec["kind"],
                            "file_path": rec["file_path"],
                        }
                    )

                if rec["direction"] == "outgoing":
                    links.append(
                        {
                            "source": symbol_id,
                            "target": nid,
                            "type": "CALLS",
                            "line": rec["line"],
                        }
                    )
                else:
                    links.append(
                        {
                            "source": nid,
                            "target": symbol_id,
                            "type": "CALLS",
                            "line": rec["line"],
                        }
                    )

            return {"nodes": nodes, "links": links}
        except Exception as e:
            logger.debug(f"get_symbol_neighbors failed: {e}")
            return {"nodes": [], "links": []}

    async def get_blast_radius_graph(
        self,
        symbol_name: str | None,
        file_path: str | None,
        project_id: str,
        depth: int = 3,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get blast radius as visualization-ready graph data.

        Wraps find_blast_radius and returns {nodes, links} with distance
        metadata for heat-map coloring.
        """
        results = await self.find_blast_radius(
            symbol_name=symbol_name,
            file_path=file_path,
            project_id=project_id,
            depth=depth,
            limit=limit,
        )

        nodes: list[dict[str, Any]] = []
        links: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # Add the center node
        center_id = symbol_name or file_path
        if not center_id:
            raise ValueError("Either symbol_name or file_path must be provided")
        center_type = "function" if symbol_name else "file"
        nodes.append(
            {
                "id": center_id,
                "name": center_id,
                "type": center_type,
                "blast_distance": 0,
            }
        )
        seen_ids.add(center_id)

        for r in results:
            nid = r.get("symbol_id") or r.get("file_path", "")
            if not nid or nid in seen_ids:
                continue
            seen_ids.add(nid)

            nodes.append(
                {
                    "id": nid,
                    "name": r.get("symbol_name") or r.get("file_path", ""),
                    "type": r.get("kind")
                    or ("file" if r.get("rel_type") == "import" else "function"),
                    "kind": r.get("kind"),
                    "file_path": r.get("file_path"),
                    "blast_distance": r.get("distance", 1),
                }
            )
            links.append(
                {
                    "source": nid,
                    "target": center_id,
                    "type": "CALLS" if r.get("rel_type") == "call" else "IMPORTS",
                    "distance": r.get("distance", 1),
                }
            )

        return {"nodes": nodes, "links": links, "center": center_id}

    async def clear_project(self, project_id: str) -> None:
        """Remove all graph data for a project."""
        if not self.available:
            return

        try:
            await self._client.execute_write(
                """MATCH (n {project: $project})
                   WHERE n:CodeFile OR n:CodeSymbol OR n:CodeModule
                   DETACH DELETE n""",
                {"project": project_id},
            )
        except Exception as e:
            logger.warning(f"Graph clear_project failed: {e}")

    async def delete_file(self, file_path: str, project_id: str) -> None:
        """Remove all graph data for a specific file."""
        if not self.available:
            return

        try:
            # Delete the CodeFile node itself (cascades to relationships)
            # Delete CodeSymbols defined in this file
            await self._client.execute_write(
                """
                MATCH (f:CodeFile {path: $file_path, project: $project})
                OPTIONAL MATCH (f)-[:DEFINES]->(s:CodeSymbol)
                DETACH DELETE f, s
                """,
                {"file_path": file_path, "project": project_id},
            )
            # Also clean up any orphaned CodeModule nodes
            await self._client.execute_write(
                """
                MATCH (m:CodeModule {project: $project})
                WHERE NOT (m)<-[:IMPORTS]-()
                DETACH DELETE m
                """,
                {"project": project_id},
            )
        except Exception as e:
            logger.warning(f"Graph delete_file failed: {e}")
