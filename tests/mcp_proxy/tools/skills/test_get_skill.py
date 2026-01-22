"""Tests for get_skill MCP tool (TDD - written before implementation)."""

import asyncio
from pathlib import Path

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.skills import LocalSkillManager


@pytest.fixture
def db(tmp_path: Path) -> LocalDatabase:
    """Create a fresh database with migrations applied."""
    db_path = tmp_path / "test.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    return database


@pytest.fixture
def storage(db: LocalDatabase) -> LocalSkillManager:
    """Create a LocalSkillManager for storage operations."""
    return LocalSkillManager(db)


@pytest.fixture
def populated_db(db: LocalDatabase, storage: LocalSkillManager) -> LocalDatabase:
    """Create database with test skills."""
    storage.create_skill(
        name="git-commit",
        description="Generate conventional commit messages",
        content="# Git Commit Helper\n\nThis skill helps you write commit messages.\n\n## Usage\n\n...",
        version="1.0.0",
        license="MIT",
        compatibility="Claude 3.5+",
        allowed_tools=["Bash", "Read"],
        metadata={
            "skillport": {
                "category": "git",
                "tags": ["git", "commits"],
                "alwaysApply": False,
            }
        },
        enabled=True,
    )
    storage.create_skill(
        name="minimal-skill",
        description="A minimal skill",
        content="# Minimal\n\nContent",
        enabled=True,
    )
    return db


@pytest.mark.integration
class TestGetSkillTool:
    """Tests for get_skill MCP tool."""

    def test_get_skill_by_name(self, populated_db):
        """Test getting a skill by name returns full content."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("get_skill")

        result = asyncio.run(tool(name="git-commit"))

        assert result["success"] is True
        assert result["skill"]["name"] == "git-commit"
        assert "Git Commit Helper" in result["skill"]["content"]

    def test_get_skill_returns_full_content(self, populated_db):
        """Test that get_skill returns full content field."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("get_skill")

        result = asyncio.run(tool(name="git-commit"))

        assert result["success"] is True
        skill = result["skill"]

        # Full content should be present
        assert "content" in skill
        assert len(skill["content"]) > 50  # Not truncated

    def test_get_skill_returns_all_fields(self, populated_db):
        """Test that get_skill returns all skill fields."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("get_skill")

        result = asyncio.run(tool(name="git-commit"))

        assert result["success"] is True
        skill = result["skill"]

        # All fields should be present
        assert skill["id"] is not None
        assert skill["name"] == "git-commit"
        assert skill["description"] == "Generate conventional commit messages"
        assert skill["version"] == "1.0.0"
        assert skill["license"] == "MIT"
        assert skill["compatibility"] == "Claude 3.5+"
        assert skill["allowed_tools"] == ["Bash", "Read"]
        assert skill["enabled"] is True

    def test_get_skill_returns_metadata(self, populated_db):
        """Test that get_skill returns metadata including skillport."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("get_skill")

        result = asyncio.run(tool(name="git-commit"))

        assert result["success"] is True
        skill = result["skill"]

        # Metadata should be present
        assert "metadata" in skill
        assert skill["metadata"]["skillport"]["category"] == "git"
        assert "git" in skill["metadata"]["skillport"]["tags"]

    def test_get_skill_not_found(self, populated_db):
        """Test that get_skill returns error for non-existent skill."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("get_skill")

        result = asyncio.run(tool(name="nonexistent"))

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_get_skill_by_id(self, populated_db, storage):
        """Test getting a skill by ID."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        # Get the actual skill ID
        skill = storage.get_by_name("git-commit")

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("get_skill")

        result = asyncio.run(tool(skill_id=skill.id))

        assert result["success"] is True
        assert result["skill"]["name"] == "git-commit"

    def test_get_skill_prefers_id_over_name(self, populated_db, storage):
        """Test that skill_id takes precedence over name."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        # Get the actual skill ID for minimal-skill
        skill = storage.get_by_name("minimal-skill")

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("get_skill")

        # Pass both id and name - id should win
        result = asyncio.run(tool(skill_id=skill.id, name="git-commit"))

        assert result["success"] is True
        assert result["skill"]["name"] == "minimal-skill"

    def test_get_skill_requires_identifier(self, populated_db):
        """Test that get_skill requires either name or skill_id."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("get_skill")

        result = asyncio.run(tool())

        assert result["success"] is False
        assert "name or skill_id" in result["error"].lower()

    def test_get_skill_minimal_fields(self, populated_db):
        """Test getting a skill with minimal fields set."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("get_skill")

        result = asyncio.run(tool(name="minimal-skill"))

        assert result["success"] is True
        skill = result["skill"]

        # Should still have the fields even if None
        assert skill["name"] == "minimal-skill"
        assert skill["version"] is None
        assert skill["license"] is None
        assert skill["compatibility"] is None
        assert skill["allowed_tools"] is None
