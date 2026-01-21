"""Tests for gobby-skills MCP registry factory (TDD - written before implementation)."""

import pytest
from pathlib import Path

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations


@pytest.fixture
def db(tmp_path: Path) -> LocalDatabase:
    """Create a fresh database with migrations applied."""
    db_path = tmp_path / "test.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    return database


class TestCreateSkillsRegistry:
    """Tests for create_skills_registry factory function."""

    def test_create_skills_registry_returns_registry(self, db):
        """Test that create_skills_registry returns an InternalToolRegistry."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry
        from gobby.mcp_proxy.tools.internal import InternalToolRegistry

        registry = create_skills_registry(db)

        assert isinstance(registry, InternalToolRegistry)

    def test_skills_registry_has_correct_name(self, db):
        """Test that registry has server name 'gobby-skills'."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(db)

        assert registry.name == "gobby-skills"

    def test_skills_registry_has_description(self, db):
        """Test that registry has a description."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(db)

        assert registry.description is not None
        assert len(registry.description) > 0

    def test_skills_registry_class_is_custom(self, db):
        """Test that SkillsToolRegistry extends InternalToolRegistry."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry, SkillsToolRegistry

        registry = create_skills_registry(db)

        assert isinstance(registry, SkillsToolRegistry)

    def test_skills_registry_has_get_tool_method(self, db):
        """Test that registry has get_tool method for testing."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(db)

        # get_tool should be callable
        assert hasattr(registry, "get_tool")
        assert callable(registry.get_tool)

    def test_create_skills_registry_accepts_project_id(self, db):
        """Test that factory accepts optional project_id parameter."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        # Should not raise
        registry = create_skills_registry(db, project_id="test-project")

        assert registry is not None


class TestSkillsToolRegistry:
    """Tests for SkillsToolRegistry class."""

    def test_registry_class_exported(self):
        """Test that SkillsToolRegistry is exported from module."""
        from gobby.mcp_proxy.tools.skills import SkillsToolRegistry

        assert SkillsToolRegistry is not None

    def test_registry_inherits_from_internal_registry(self, db):
        """Test that SkillsToolRegistry inherits correctly."""
        from gobby.mcp_proxy.tools.skills import SkillsToolRegistry
        from gobby.mcp_proxy.tools.internal import InternalToolRegistry

        assert issubclass(SkillsToolRegistry, InternalToolRegistry)
