"""
Tests for hub.py MCP tools module.

Tests the hub query tools that provide cross-project queries
against the hub database.
"""

import asyncio
from pathlib import Path

import pytest

from gobby.mcp_proxy.tools.hub import create_hub_registry
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit


@pytest.fixture
def temp_hub_db(tmp_path: Path) -> Path:
    """Create a temporary hub database with schema."""
    db_path = tmp_path / "gobby-hub.db"
    db = LocalDatabase(db_path)
    run_migrations(db)
    return db_path


@pytest.fixture
def hub_registry(temp_hub_db: Path):
    """Create a hub registry with a temp database."""
    return create_hub_registry(hub_db_path=temp_hub_db)


@pytest.fixture
def populated_hub_db(temp_hub_db: Path) -> Path:
    """Create a hub database with test data."""
    db = LocalDatabase(temp_hub_db)

    # Insert test projects first (required for foreign keys)
    db.execute(
        """
        INSERT INTO projects (id, name, repo_path, github_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        ("project-alpha", "Project Alpha", "/path/alpha", None),
    )
    db.execute(
        """
        INSERT INTO projects (id, name, repo_path, github_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        ("project-beta", "Project Beta", "/path/beta", None),
    )

    # Insert test tasks
    db.execute(
        """
        INSERT INTO tasks (id, project_id, title, status, task_type, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        ("task-1", "project-alpha", "Task 1", "open", "task", 1),
    )
    db.execute(
        """
        INSERT INTO tasks (id, project_id, title, status, task_type, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        ("task-2", "project-alpha", "Task 2", "closed", "task", 2),
    )
    db.execute(
        """
        INSERT INTO tasks (id, project_id, title, status, task_type, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        ("task-3", "project-beta", "Task 3", "in_progress", "feature", 1),
    )

    # Insert test sessions with correct columns
    db.execute(
        """
        INSERT INTO sessions (id, project_id, external_id, source, machine_id, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        ("sess-1", "project-alpha", "ext-1", "claude", "machine-1", "active"),
    )
    db.execute(
        """
        INSERT INTO sessions (id, project_id, external_id, source, machine_id, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        ("sess-2", "project-beta", "ext-2", "gemini", "machine-1", "ended"),
    )
    db.execute(
        """
        INSERT INTO sessions (id, project_id, external_id, source, machine_id, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        ("sess-3", "project-alpha", "ext-3", "claude", "machine-2", "ended"),
    )

    return temp_hub_db


class TestListAllProjects:
    """Tests for list_all_projects tool."""

    def test_list_all_projects_returns_unique_list(self, populated_hub_db: Path) -> None:
        """Test that list_all_projects returns unique project list."""
        registry = create_hub_registry(hub_db_path=populated_hub_db)
        tool = registry.get_tool("list_all_projects")

        result = asyncio.run(tool())

        assert "error" not in result
        assert result["project_count"] == 2
        project_ids = [p["project_id"] for p in result["projects"]]
        assert "project-alpha" in project_ids
        assert "project-beta" in project_ids

    def test_list_all_projects_includes_counts(self, populated_hub_db: Path) -> None:
        """Test that list_all_projects includes task and session counts."""
        registry = create_hub_registry(hub_db_path=populated_hub_db)
        tool = registry.get_tool("list_all_projects")

        result = asyncio.run(tool())

        assert "error" not in result
        alpha = next(p for p in result["projects"] if p["project_id"] == "project-alpha")
        beta = next(p for p in result["projects"] if p["project_id"] == "project-beta")

        assert alpha["task_count"] == 2
        assert alpha["session_count"] == 2
        assert beta["task_count"] == 1
        assert beta["session_count"] == 1

    def test_list_all_projects_empty_database(self, temp_hub_db: Path) -> None:
        """Test list_all_projects handles empty database gracefully."""
        registry = create_hub_registry(hub_db_path=temp_hub_db)
        tool = registry.get_tool("list_all_projects")

        result = asyncio.run(tool())

        assert "error" not in result
        assert result["project_count"] == 0
        assert result["projects"] == []

    def test_list_all_projects_missing_database(self, tmp_path: Path) -> None:
        """Test list_all_projects handles missing database."""
        nonexistent = tmp_path / "nonexistent.db"
        registry = create_hub_registry(hub_db_path=nonexistent)
        tool = registry.get_tool("list_all_projects")

        result = asyncio.run(tool())

        assert "error" in result
        assert "not found" in result["error"]


class TestListCrossProjectTasks:
    """Tests for list_cross_project_tasks tool."""

    def test_list_cross_project_tasks_all(self, populated_hub_db: Path) -> None:
        """Test list_cross_project_tasks returns all tasks."""
        registry = create_hub_registry(hub_db_path=populated_hub_db)
        tool = registry.get_tool("list_cross_project_tasks")

        result = asyncio.run(tool())

        assert "error" not in result
        assert result["count"] == 3

    def test_list_cross_project_tasks_with_status_filter(self, populated_hub_db: Path) -> None:
        """Test list_cross_project_tasks with status filter."""
        registry = create_hub_registry(hub_db_path=populated_hub_db)
        tool = registry.get_tool("list_cross_project_tasks")

        result = asyncio.run(tool(status="open"))

        assert "error" not in result
        assert result["count"] == 1
        assert result["tasks"][0]["status"] == "open"

    def test_list_cross_project_tasks_with_limit(self, populated_hub_db: Path) -> None:
        """Test list_cross_project_tasks respects limit."""
        registry = create_hub_registry(hub_db_path=populated_hub_db)
        tool = registry.get_tool("list_cross_project_tasks")

        result = asyncio.run(tool(limit=2))

        assert "error" not in result
        assert result["count"] == 2

    def test_list_cross_project_tasks_empty_database(self, temp_hub_db: Path) -> None:
        """Test list_cross_project_tasks handles empty database."""
        registry = create_hub_registry(hub_db_path=temp_hub_db)
        tool = registry.get_tool("list_cross_project_tasks")

        result = asyncio.run(tool())

        assert "error" not in result
        assert result["count"] == 0
        assert result["tasks"] == []


class TestListCrossProjectSessions:
    """Tests for list_cross_project_sessions tool."""

    def test_list_cross_project_sessions_all(self, populated_hub_db: Path) -> None:
        """Test list_cross_project_sessions returns all sessions."""
        registry = create_hub_registry(hub_db_path=populated_hub_db)
        tool = registry.get_tool("list_cross_project_sessions")

        result = asyncio.run(tool())

        assert "error" not in result
        assert result["count"] == 3
        # Verify session has correct fields
        session = result["sessions"][0]
        assert "source" in session  # Not cli_type
        assert "created_at" in session

    def test_list_cross_project_sessions_respects_limit(self, populated_hub_db: Path) -> None:
        """Test list_cross_project_sessions respects limit parameter."""
        registry = create_hub_registry(hub_db_path=populated_hub_db)
        tool = registry.get_tool("list_cross_project_sessions")

        result = asyncio.run(tool(limit=1))

        assert "error" not in result
        assert result["count"] == 1

    def test_list_cross_project_sessions_empty_database(self, temp_hub_db: Path) -> None:
        """Test list_cross_project_sessions handles empty database."""
        registry = create_hub_registry(hub_db_path=temp_hub_db)
        tool = registry.get_tool("list_cross_project_sessions")

        result = asyncio.run(tool())

        assert "error" not in result
        assert result["count"] == 0
        assert result["sessions"] == []


class TestHubStats:
    """Tests for hub_stats tool."""

    def test_hub_stats_returns_correct_counts(self, populated_hub_db: Path) -> None:
        """Test hub_stats returns correct aggregate counts."""
        registry = create_hub_registry(hub_db_path=populated_hub_db)
        tool = registry.get_tool("hub_stats")

        result = asyncio.run(tool())

        assert "error" not in result
        stats = result["stats"]
        assert stats["project_count"] == 2
        assert stats["tasks"]["total"] == 3
        assert stats["sessions"]["total"] == 3

    def test_hub_stats_includes_status_breakdown(self, populated_hub_db: Path) -> None:
        """Test hub_stats includes breakdown by status."""
        registry = create_hub_registry(hub_db_path=populated_hub_db)
        tool = registry.get_tool("hub_stats")

        result = asyncio.run(tool())

        assert "error" not in result
        stats = result["stats"]
        assert stats["tasks"]["by_status"]["open"] == 1
        assert stats["tasks"]["by_status"]["closed"] == 1
        assert stats["tasks"]["by_status"]["in_progress"] == 1

    def test_hub_stats_empty_database(self, temp_hub_db: Path) -> None:
        """Test hub_stats handles empty database gracefully."""
        registry = create_hub_registry(hub_db_path=temp_hub_db)
        tool = registry.get_tool("hub_stats")

        result = asyncio.run(tool())

        assert "error" not in result
        stats = result["stats"]
        assert stats["project_count"] == 0
        assert stats["tasks"]["total"] == 0
        assert stats["sessions"]["total"] == 0

    def test_hub_stats_missing_database(self, tmp_path: Path) -> None:
        """Test hub_stats handles missing database."""
        nonexistent = tmp_path / "nonexistent.db"
        registry = create_hub_registry(hub_db_path=nonexistent)
        tool = registry.get_tool("hub_stats")

        result = asyncio.run(tool())

        assert "error" in result
        assert "not found" in result["error"]
