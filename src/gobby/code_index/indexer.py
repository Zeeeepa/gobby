"""Code indexer orchestrator.

Coordinates: parse -> store -> embed -> graph
for individual files and full directories.
"""

from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gobby.code_index.chunker import chunk_file_content
from gobby.code_index.graph import CodeGraph
from gobby.code_index.hasher import file_content_hash
from gobby.code_index.languages import detect_language, get_extensions_map
from gobby.code_index.models import (
    IndexedFile,
    IndexedProject,
    IndexResult,
    Symbol,
)
from gobby.code_index.parser import CodeParser
from gobby.code_index.security import should_exclude
from gobby.code_index.storage import CodeIndexStorage
from gobby.config.code_index import CodeIndexConfig

logger = logging.getLogger(__name__)


def _get_git_files(root: Path) -> set[str] | None:
    """Get git-visible files (tracked + untracked-but-not-ignored).

    Returns relative paths, or None if not a git repo / git unavailable.
    """
    try:
        # Tracked files
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None

        files: set[str] = set()
        for line in result.stdout.strip().splitlines():
            if line:
                files.add(line)

        # Untracked but not ignored
        result2 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result2.returncode == 0:
            for line in result2.stdout.strip().splitlines():
                if line:
                    files.add(line)

        return files
    except (OSError, subprocess.TimeoutExpired):
        return None


class CodeIndexer:
    """Orchestrates code indexing: parse -> store -> embed -> graph."""

    def __init__(
        self,
        storage: CodeIndexStorage,
        parser: CodeParser,
        vector_store: Any | None = None,
        embed_fn: Callable[..., Any] | None = None,
        graph: CodeGraph | None = None,
        config: CodeIndexConfig | None = None,
    ) -> None:
        self._storage = storage
        self._parser = parser
        self._vector_store = vector_store
        self._embed_fn = embed_fn
        self._graph = graph
        self._config = config or CodeIndexConfig()
        # Cache collections known to be missing to avoid repeated failed HTTP roundtrips
        self._missing_collections: set[str] = set()

    @property
    def storage(self) -> CodeIndexStorage:
        return self._storage

    @property
    def graph(self) -> CodeGraph | None:
        return self._graph

    @property
    def config(self) -> CodeIndexConfig:
        return self._config

    async def index_directory(
        self,
        root_path: str,
        project_id: str,
        incremental: bool = True,
    ) -> IndexResult:
        """Index all supported files in a directory.

        Args:
            root_path: Absolute path to directory root.
            project_id: Project identifier.
            incremental: If True, skip unchanged files.

        Returns:
            IndexResult with counts and timing.
        """
        start = time.monotonic()
        result = IndexResult(project_id=project_id)
        root = Path(root_path).resolve()

        if not root.is_dir():
            result.errors.append(f"Not a directory: {root_path}")
            return result

        ext_map = get_extensions_map()
        supported_extensions = set(ext_map.keys())
        content_extensions = set(self._config.content_extensions)
        all_extensions = supported_extensions | content_extensions

        # Collect candidate files using git-aware discovery
        git_files = _get_git_files(root)
        candidates: list[Path] = []
        content_only_candidates: list[Path] = []

        if git_files is not None:
            # Git-aware: only index files git knows about
            for rel_path in git_files:
                path = root / rel_path
                if not path.is_file():
                    continue
                suffix = path.suffix.lower()
                if suffix not in all_extensions:
                    continue
                if should_exclude(path, self._config.exclude_patterns):
                    continue
                if suffix in supported_extensions:
                    candidates.append(path)
                else:
                    content_only_candidates.append(path)
        else:
            # Fallback: rglob for non-git repos
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                suffix = path.suffix.lower()
                if suffix not in all_extensions:
                    continue
                if should_exclude(path, self._config.exclude_patterns):
                    continue
                if suffix in supported_extensions:
                    candidates.append(path)
                else:
                    content_only_candidates.append(path)

        # Build hash map for incremental check
        current_hashes: dict[str, str] = {}
        if incremental:
            for path in candidates:
                try:
                    rel = str(path.resolve().relative_to(root))
                    current_hashes[rel] = file_content_hash(path)
                except (OSError, ValueError):
                    pass

            stale = set(self._storage.get_stale_files(project_id, current_hashes))
        else:
            stale = None  # Index everything

        # Clean up orphan files no longer in candidates (e.g., newly excluded dirs)
        if incremental and current_hashes:
            try:
                orphans = self._storage.get_orphan_files(project_id, set(current_hashes.keys()))
                for orphan_path in orphans:
                    await self._delete_file_data(project_id, orphan_path)
                if orphans:
                    logger.info(f"Cleaned up {len(orphans)} orphan indexed files")
            except Exception as e:
                logger.debug(f"Orphan cleanup failed: {e}")

        # Index each file (symbols + content chunks)
        for path in candidates:
            try:
                rel = str(path.resolve().relative_to(root))
            except ValueError:
                continue

            if incremental and stale is not None and rel not in stale:
                result.files_skipped += 1
                continue

            symbols = await self.index_file(str(path), project_id, root_path)
            if symbols is not None:
                result.files_indexed += 1
                result.symbols_found += len(symbols)
            else:
                result.files_skipped += 1

        # Index content-only files (no AST parsing, just content chunks)
        for path in content_only_candidates:
            try:
                rel = str(path.resolve().relative_to(root))
            except ValueError:
                continue
            await self._index_content_only(path, project_id, root_path)

        # Update project stats
        elapsed_ms = int((time.monotonic() - start) * 1000)
        result.duration_ms = elapsed_ms

        total_files = self._storage.count_files(project_id)
        total_symbols = self._storage.count_symbols(project_id)

        self._storage.upsert_project_stats(
            IndexedProject(
                id=project_id,
                root_path=root_path,
                total_files=total_files,
                total_symbols=total_symbols,
                last_indexed_at=datetime.now(UTC).isoformat(),
                index_duration_ms=elapsed_ms,
            )
        )

        logger.info(
            f"Indexed {result.files_indexed} files ({result.files_skipped} skipped), "
            f"{result.symbols_found} symbols in {elapsed_ms}ms"
        )
        return result

    async def _delete_file_data(self, project_id: str, file_path: str) -> None:
        """Remove all data for a file from SQLite, Qdrant, and Neo4j."""
        self._storage.delete_symbols_for_file(project_id, file_path)
        self._storage.delete_file(project_id, file_path)
        self._storage.delete_content_chunks_for_file(project_id, file_path)
        self._storage.delete_imports_for_file(project_id, file_path)
        self._storage.delete_calls_for_file(project_id, file_path)

        if self._graph is not None and self._graph.available:
            await self._graph.delete_file(file_path=file_path, project_id=project_id)

        if self._vector_store is not None:
            collection = f"{self._config.qdrant_collection_prefix}{project_id}"
            if collection not in self._missing_collections:
                try:
                    await self._vector_store.delete(
                        filters={"file_path": file_path, "project_id": project_id},
                        collection_name=collection,
                    )
                except Exception as e:
                    err_str = str(e).lower()
                    if "not found" in err_str or "doesn't exist" in err_str:
                        self._missing_collections.add(collection)
                        logger.debug(
                            f"Qdrant collection {collection} not found, "
                            f"skipping future deletes this run"
                        )
                    else:
                        logger.debug(f"Vector delete failed for {file_path}: {e}")

    async def index_file(
        self,
        file_path: str,
        project_id: str,
        root_path: str,
    ) -> list[Symbol] | None:
        """Index a single file. Returns symbols or None if skipped."""
        parse_result = self._parser.parse_file(file_path, project_id, root_path)

        root = Path(root_path).resolve()
        path = Path(file_path).resolve()
        try:
            rel_path = str(path.relative_to(root))
        except ValueError:
            rel_path = str(path)

        # Always clear old data first before re-indexing to prevent ghosts
        await self._delete_file_data(project_id, rel_path)

        if parse_result is None:
            return None

        symbols = parse_result.symbols
        if not symbols:
            return []

        # Store symbols
        self._storage.upsert_symbols(symbols)

        language = detect_language(file_path) or "unknown"
        try:
            h = file_content_hash(file_path)
            size = path.stat().st_size
        except OSError:
            h = ""
            size = 0

        self._storage.upsert_file(
            IndexedFile(
                id=IndexedFile.make_id(project_id, rel_path),
                project_id=project_id,
                file_path=rel_path,
                language=language,
                content_hash=h,
                symbol_count=len(symbols),
                byte_size=size,
            )
        )

        # Store import/call relations in SQLite (for daemon sync worker)
        self._storage.upsert_imports(project_id, rel_path, parse_result.imports)
        self._storage.upsert_calls(project_id, rel_path, parse_result.calls)

        # Index content chunks for full-text content search
        try:
            source = path.read_bytes()
            chunks = chunk_file_content(
                source=source,
                rel_path=rel_path,
                project_id=project_id,
                language=language,
            )
            if chunks:
                self._storage.upsert_content_chunks(chunks)
        except Exception as e:
            logger.debug(f"Content chunk indexing failed for {file_path}: {e}")

        file_id = IndexedFile.make_id(project_id, rel_path)

        # Embed symbols (async, non-blocking on failure)
        if self._vector_store is not None and self._embed_fn is not None:
            try:
                count = await self._embed_symbols(symbols, project_id)
                if count > 0:
                    self._storage.mark_vectors_synced(file_id)
            except Exception as e:
                logger.debug(f"Embedding failed for {file_path}: {e}")

        # Add graph relationships (async, non-blocking on failure)
        if self._graph is not None and self._graph.available:
            try:
                count = await self._add_graph_data(project_id, rel_path, parse_result, symbols)
                if count > 0:
                    self._storage.mark_graph_synced(file_id)
            except Exception as e:
                logger.debug(f"Graph update failed for {file_path}: {e}")

        return symbols

    async def index_changed_files(
        self,
        project_id: str,
        root_path: str,
        file_paths: list[str],
    ) -> IndexResult:
        """Index specific changed files (e.g., from git post-commit)."""
        start = time.monotonic()
        result = IndexResult(project_id=project_id)

        for fp in file_paths:
            # Resolve relative to root
            abs_path = Path(root_path) / fp if not Path(fp).is_absolute() else Path(fp)
            if not abs_path.exists():
                # File was deleted — clean up everywhere
                await self._delete_file_data(project_id, fp)
                continue

            symbols = await self.index_file(str(abs_path), project_id, root_path)
            if symbols is not None:
                result.files_indexed += 1
                result.symbols_found += len(symbols)

        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result

    async def _index_content_only(self, path: Path, project_id: str, root_path: str) -> None:
        """Index a non-tree-sitter file for content search only."""
        root = Path(root_path).resolve()
        resolved = path.resolve()
        try:
            rel_path = str(resolved.relative_to(root))
        except ValueError:
            return

        try:
            size = path.stat().st_size
            if size == 0 or size > self._config.max_file_size_bytes:
                return
        except OSError:
            return

        try:
            source = path.read_bytes()
            # Skip binary files
            if b"\x00" in source[:8192]:
                return
        except OSError:
            return

        # Clear old chunks
        self._storage.delete_content_chunks_for_file(project_id, rel_path)

        chunks = chunk_file_content(
            source=source,
            rel_path=rel_path,
            project_id=project_id,
            language=path.suffix.lstrip(".") or None,
        )
        if chunks:
            self._storage.upsert_content_chunks(chunks)

    async def invalidate(self, project_id: str) -> None:
        """Clear all index data for a project."""
        self._storage.delete_symbols_for_project(project_id)
        self._storage.delete_files_for_project(project_id)
        self._storage.delete_content_chunks_for_project(project_id)

        # Clear graph
        if self._graph is not None:
            await self._graph.clear_project(project_id)

        # Clear vectors
        if self._vector_store is not None:
            collection = f"{self._config.qdrant_collection_prefix}{project_id}"
            try:
                await self._vector_store.delete_collection(collection)
            except Exception as e:
                logger.debug(f"Vector collection delete failed: {e}")

        logger.info(f"Invalidated code index for project {project_id}")

    async def _embed_symbols(self, symbols: list[Symbol], project_id: str) -> int:
        """Embed symbol text into Qdrant. Returns count embedded."""
        if not symbols or self._embed_fn is None or self._vector_store is None:
            return 0

        # Build text for embedding: name + signature + docstring
        texts = []
        ids = []
        for sym in symbols:
            parts = [sym.qualified_name]
            if sym.signature:
                parts.append(sym.signature)
            if sym.docstring:
                parts.append(sym.docstring[:200])
            texts.append(" ".join(parts))
            ids.append(sym.id)

        # Generate embeddings
        try:
            embeddings = []
            for text in texts:
                emb = await self._embed_fn(text)
                if emb is not None:
                    embeddings.append(emb)
                else:
                    embeddings.append(None)
        except Exception as e:
            logger.debug(f"Embedding generation failed: {e}")
            return 0

        # Upsert to Qdrant
        collection = f"{self._config.qdrant_collection_prefix}{project_id}"
        count = 0
        try:
            items = []
            for i, emb in enumerate(embeddings):
                if emb is not None:
                    items.append(
                        (
                            ids[i],
                            emb,
                            {
                                "name": symbols[i].name,
                                "kind": symbols[i].kind,
                                "file_path": symbols[i].file_path,
                                "project_id": project_id,
                            },
                        )
                    )

            if items:
                await self._vector_store.batch_upsert(
                    items=items,
                    collection_name=collection,
                )
                count = len(items)
                # Collection exists now — clear from missing cache
                self._missing_collections.discard(collection)
        except Exception as e:
            logger.debug(f"Vector upsert failed: {e}")

        return count

    async def _add_graph_data(
        self,
        project_id: str,
        rel_path: str,
        parse_result: Any,
        symbols: list[Symbol],
    ) -> int:
        """Add parsed relationships to Neo4j graph."""
        if self._graph is None:
            return 0

        imports = [
            {
                "source_file": imp.source_file,
                "target_module": imp.target_module,
            }
            for imp in parse_result.imports
        ]

        calls = [
            {
                "caller_symbol_id": call.caller_symbol_id,
                "callee_name": call.callee_name,
                "file_path": call.file_path,
                "line": call.line,
            }
            for call in parse_result.calls
        ]

        contains = [{"id": sym.id, "name": sym.name, "kind": sym.kind} for sym in symbols]

        return await self._graph.add_relationships(
            project_id=project_id,
            file_path=rel_path,
            imports=imports,
            calls=calls,
            contains=contains,
        )
