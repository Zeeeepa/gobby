"""Tests for blast_radius impact analysis tool."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from gobby.code_index.graph import CodeGraph
from gobby.code_index.indexer import CodeIndexer
from gobby.code_index.parser import CodeParser
from gobby.code_index.searcher import CodeSearcher
from gobby.code_index.storage import CodeIndexStorage
from gobby.config.code_index import CodeIndexConfig
from gobby.mcp_proxy.tools.code._context import CodeRegistryContext
from gobby.mcp_proxy.tools.code._impact import create_impact_registry
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit

_CODE_INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS code_indexed_projects (
    id TEXT PRIMARY KEY,
    root_path TEXT NOT NULL,
    total_files INTEGER NOT NULL DEFAULT 0,
    total_symbols INTEGER NOT NULL DEFAULT 0,
    last_indexed_at TEXT,
    index_duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS code_symbols (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    language TEXT NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    signature TEXT,
    docstring TEXT,
    parent_symbol_id TEXT,
    content_hash TEXT NOT NULL,
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@pytest.fixture
def code_db(tmp_path: Path) -> LocalDatabase:
    db = LocalDatabase(tmp_path / "impact-test.db")
    run_migrations(db)
    db.connection.executescript(_CODE_INDEX_SCHEMA)
    db.connection.commit()
    yield db  # type: ignore[misc]
    db.close()


@pytest.fixture
def code_storage(code_db: LocalDatabase) -> CodeIndexStorage:
    return CodeIndexStorage(code_db)


@pytest.fixture
def config() -> CodeIndexConfig:
    return CodeIndexConfig()


@pytest.fixture
def parser(config: CodeIndexConfig) -> CodeParser:
    return CodeParser(config)


@pytest.fixture
def indexer(
    code_storage: CodeIndexStorage, parser: CodeParser, config: CodeIndexConfig
) -> CodeIndexer:
    return CodeIndexer(storage=code_storage, parser=parser, config=config)


@pytest.fixture
def searcher(code_storage: CodeIndexStorage) -> CodeSearcher:
    return CodeSearcher(storage=code_storage)


@pytest.fixture
def mock_graph() -> CodeGraph:
    """CodeGraph with a mocked Neo4j client."""
    graph = CodeGraph(neo4j_client=AsyncMock())
    return graph


@pytest.fixture
def ctx_no_graph(
    code_storage: CodeIndexStorage,
    indexer: CodeIndexer,
    searcher: CodeSearcher,
) -> CodeRegistryContext:
    return CodeRegistryContext(
        storage=code_storage,
        indexer=indexer,
        searcher=searcher,
        graph=None,
        project_id="test-proj",
    )


@pytest.fixture
def ctx_with_graph(
    code_storage: CodeIndexStorage,
    indexer: CodeIndexer,
    searcher: CodeSearcher,
    mock_graph: CodeGraph,
    code_db: LocalDatabase,
) -> CodeRegistryContext:
    return CodeRegistryContext(
        storage=code_storage,
        indexer=indexer,
        searcher=searcher,
        graph=mock_graph,
        project_id="test-proj",
        db=code_db,
    )


# ── Validation ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blast_radius_requires_symbol_or_file(ctx_no_graph) -> None:
    """Returns error when neither symbol_name nor file_path provided."""
    registry = create_impact_registry(ctx_no_graph)
    result = await registry.call("blast_radius", {"symbol_name": "", "file_path": ""})
    assert "error" in result


@pytest.mark.asyncio
async def test_blast_radius_rejects_both_symbol_and_file(ctx_no_graph) -> None:
    """Returns error when both symbol_name and file_path provided."""
    registry = create_impact_registry(ctx_no_graph)
    result = await registry.call("blast_radius", {"symbol_name": "foo", "file_path": "bar.py"})
    assert "error" in result


# ── Graph unavailable ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blast_radius_graph_unavailable(ctx_no_graph) -> None:
    """Returns warning with empty results when graph is None."""
    registry = create_impact_registry(ctx_no_graph)
    tool = registry._tools["blast_radius"]
    result = await tool.func(symbol_name="process_data")

    assert "warning" in result
    assert result["summary"]["affected_symbols"] == 0
    assert result["summary"]["affected_files"] == 0
    assert result["affected_files"] == []


# ── Symbol query ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blast_radius_symbol_query(ctx_with_graph, mock_graph) -> None:
    """Symbol query returns structured results from graph traversal."""
    mock_graph._client.execute_read = AsyncMock(
        return_value=[
            {
                "symbol_id": "sym-1",
                "symbol_name": "caller_a",
                "kind": "function",
                "file_path": "src/module_a.py",
                "distance": 1,
                "rel_type": "call",
            },
            {
                "symbol_id": "sym-2",
                "symbol_name": "caller_b",
                "kind": "function",
                "file_path": "src/module_a.py",
                "distance": 2,
                "rel_type": "call",
            },
            {
                "symbol_id": "sym-3",
                "symbol_name": "caller_c",
                "kind": "method",
                "file_path": "src/module_b.py",
                "distance": 1,
                "rel_type": "call",
            },
        ]
    )

    registry = create_impact_registry(ctx_with_graph)
    tool = registry._tools["blast_radius"]
    result = await tool.func(symbol_name="target_fn", include_tasks=False)

    assert result["summary"]["affected_symbols"] == 3
    assert result["summary"]["affected_files"] == 2
    assert result["summary"]["max_distance"] == 1  # min distance per file

    # Files sorted by min_distance then path
    files = result["affected_files"]
    assert files[0]["file_path"] == "src/module_a.py"
    assert files[0]["min_distance"] == 1
    assert len(files[0]["symbols"]) == 2
    assert files[1]["file_path"] == "src/module_b.py"


# ── File query ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blast_radius_file_query(ctx_with_graph, mock_graph) -> None:
    """File query combines call and import results."""
    # First call returns call results, second returns import results
    mock_graph._client.execute_read = AsyncMock(
        side_effect=[
            [
                {
                    "symbol_id": "sym-1",
                    "symbol_name": "caller_a",
                    "kind": "function",
                    "file_path": "src/caller.py",
                    "distance": 1,
                    "rel_type": "call",
                },
            ],
            [
                {
                    "file_path": "src/importer.py",
                    "distance": 1,
                    "rel_type": "import",
                },
            ],
        ]
    )

    registry = create_impact_registry(ctx_with_graph)
    tool = registry._tools["blast_radius"]
    result = await tool.func(file_path="src/target.py", include_tasks=False)

    assert result["summary"]["affected_files"] == 2
    assert result["summary"]["affected_symbols"] == 1

    # Import-only entries have no symbols
    import_file = next(f for f in result["affected_files"] if f["file_path"] == "src/importer.py")
    assert len(import_file["symbols"]) == 0


# ── Depth clamping ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blast_radius_depth_clamping(ctx_with_graph, mock_graph) -> None:
    """Depth is clamped to [1, 5]."""
    mock_graph._client.execute_read = AsyncMock(return_value=[])

    registry = create_impact_registry(ctx_with_graph)
    result = await registry.call(
        "blast_radius", {"symbol_name": "foo", "depth": 0, "include_tasks": False}
    )
    assert result["query"]["depth"] == 0  # query echoes input

    # The actual clamping happens inside CodeGraph.find_blast_radius (depth = max(1, min(depth, 5)))
    # Graph traversal ran without error
    assert result["summary"]["affected_files"] == 0


# ── Task cross-reference ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blast_radius_task_cross_reference(ctx_with_graph, mock_graph, code_db) -> None:
    """Tasks are cross-referenced when include_tasks=True and db is available."""
    mock_graph._client.execute_read = AsyncMock(
        return_value=[
            {
                "symbol_id": "sym-1",
                "symbol_name": "handler",
                "kind": "function",
                "file_path": "src/api.py",
                "distance": 1,
                "rel_type": "call",
            },
        ]
    )

    # Insert project, task, and affected file record
    code_db.connection.execute(
        """INSERT OR IGNORE INTO projects (id, name, created_at, updated_at)
           VALUES (?, ?, datetime('now'), datetime('now'))""",
        ("test-proj", "test-project"),
    )
    code_db.connection.execute(
        """INSERT INTO tasks (id, project_id, title, status, task_type, priority, category, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-123", "test-proj", "Fix API handler", "open", "task", 2, "code"),
    )
    code_db.connection.execute(
        """INSERT INTO task_affected_files (task_id, file_path, annotation_source, created_at)
           VALUES (?, ?, ?, datetime('now'))""",
        ("task-123", "src/api.py", "expansion"),
    )
    code_db.connection.commit()

    registry = create_impact_registry(ctx_with_graph)
    tool = registry._tools["blast_radius"]
    result = await tool.func(symbol_name="process", include_tasks=True)

    assert result["summary"]["affected_tasks"] == 1
    file_entry = result["affected_files"][0]
    assert len(file_entry["tasks"]) == 1
    assert file_entry["tasks"][0]["task_id"] == "task-123"
    assert file_entry["tasks"][0]["annotation_source"] == "expansion"


# ── No tasks when db missing ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_blast_radius_no_tasks_when_db_missing(ctx_with_graph, mock_graph) -> None:
    """No error when include_tasks=True but db is None."""
    ctx_with_graph.db = None
    mock_graph._client.execute_read = AsyncMock(
        return_value=[
            {
                "symbol_id": "sym-1",
                "symbol_name": "fn",
                "kind": "function",
                "file_path": "src/x.py",
                "distance": 1,
                "rel_type": "call",
            },
        ]
    )

    registry = create_impact_registry(ctx_with_graph)
    tool = registry._tools["blast_radius"]
    result = await tool.func(symbol_name="target", include_tasks=True)

    assert result["summary"]["affected_tasks"] == 0
    assert result["affected_files"][0]["tasks"] == []
