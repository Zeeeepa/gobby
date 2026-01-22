"""Tests for search_skills MCP tool (TDD - written before implementation)."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.skills import LocalSkillManager

pytestmark = pytest.mark.integration


@pytest.fixture
def db(tmp_path: Path) -> Iterator[LocalDatabase]:
    """Create a fresh database with migrations applied."""
    db_path = tmp_path / "test.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    yield database
    database.close()


@pytest.fixture
def storage(db: LocalDatabase) -> LocalSkillManager:
    """Create a LocalSkillManager for storage operations."""
    return LocalSkillManager(db)


@pytest.fixture
def populated_db(db: LocalDatabase, storage: LocalSkillManager) -> LocalDatabase:
    """Create database with test skills for search."""
    storage.create_skill(
        name="git-commit",
        description="Generate conventional commit messages for git repositories",
        content="# Git Commit Helper\n\nHelps write good commit messages.",
        metadata={"skillport": {"category": "git", "tags": ["git", "commits", "version-control"]}},
        enabled=True,
    )
    storage.create_skill(
        name="git-rebase",
        description="Interactive git rebase assistant",
        content="# Git Rebase\n\nHelps with rebasing branches.",
        metadata={"skillport": {"category": "git", "tags": ["git", "rebase"]}},
        enabled=True,
    )
    storage.create_skill(
        name="code-review",
        description="AI-powered code review for pull requests",
        content="# Code Review\n\nReviews code quality.",
        metadata={"skillport": {"category": "code-quality", "tags": ["review", "quality", "pr"]}},
        enabled=True,
    )
    storage.create_skill(
        name="python-typing",
        description="Add type hints to Python code",
        content="# Python Typing\n\nAdds type annotations.",
        metadata={"skillport": {"category": "python", "tags": ["python", "typing", "quality"]}},
        enabled=True,
    )
    return db


class TestSearchSkillsTool:
    """Tests for search_skills MCP tool."""

    def test_search_skills_returns_results(self, populated_db):
        """Test that search_skills returns matching results."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("search_skills")

        result = asyncio.run(tool(query="git commit"))

        assert result["success"] is True
        assert result["count"] > 0
        assert len(result["results"]) > 0

    def test_search_skills_returns_scores(self, populated_db):
        """Test that search results include relevance scores."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("search_skills")

        result = asyncio.run(tool(query="git"))

        assert result["success"] is True
        for res in result["results"]:
            assert "score" in res
            assert isinstance(res["score"], (int, float))
            assert res["score"] >= 0

    def test_search_skills_ranked_by_relevance(self, populated_db):
        """Test that results are ranked by relevance."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("search_skills")

        result = asyncio.run(tool(query="git commit message"))

        assert result["success"] is True
        # Results should be sorted by score descending
        scores = [r["score"] for r in result["results"]]
        assert scores == sorted(scores, reverse=True)

    def test_search_skills_respects_top_k(self, populated_db):
        """Test that search respects top_k limit."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("search_skills")

        result = asyncio.run(tool(query="git", top_k=1))

        assert result["success"] is True
        assert result["count"] <= 1

    def test_search_skills_filters_by_category(self, populated_db):
        """Test that search filters by category."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("search_skills")

        result = asyncio.run(tool(query="code", category="code-quality"))

        assert result["success"] is True
        for res in result["results"]:
            assert res["category"] == "code-quality"

    def test_search_skills_filters_by_tags_any(self, populated_db):
        """Test that search filters by any of the specified tags."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("search_skills")

        result = asyncio.run(tool(query="code", tags_any=["quality", "typing"]))

        assert result["success"] is True
        # All results should have at least one of the tags
        for res in result["results"]:
            assert any(tag in res["tags"] for tag in ["quality", "typing"])

    def test_search_skills_filters_by_tags_all(self, populated_db):
        """Test that search filters by all of the specified tags."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("search_skills")

        result = asyncio.run(tool(query="git", tags_all=["git", "commits"]))

        assert result["success"] is True
        # All results should have all the tags
        for res in result["results"]:
            assert "git" in res["tags"]
            assert "commits" in res["tags"]

    def test_search_skills_empty_query(self, populated_db):
        """Test search with empty query returns error."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("search_skills")

        result = asyncio.run(tool(query=""))

        assert result["success"] is False
        assert "query" in result["error"].lower()

    def test_search_skills_no_matches(self, populated_db):
        """Test search with no matches returns empty results."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("search_skills")

        result = asyncio.run(tool(query="nonexistent gibberish xyz"))

        assert result["success"] is True
        assert result["count"] == 0
        assert result["results"] == []

    def test_search_skills_returns_skill_metadata(self, populated_db):
        """Test that search results include skill metadata."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("search_skills")

        result = asyncio.run(tool(query="git commit"))

        assert result["success"] is True
        assert len(result["results"]) > 0

        res = result["results"][0]
        assert "skill_id" in res
        assert "skill_name" in res
        assert "description" in res
        assert "category" in res
        assert "tags" in res

    def test_search_skills_combined_filters(self, populated_db):
        """Test search with multiple filters."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(populated_db)
        tool = registry.get_tool("search_skills")

        result = asyncio.run(tool(
            query="code quality",
            category="python",
            tags_any=["typing"],
        ))

        assert result["success"] is True
        for res in result["results"]:
            assert res["category"] == "python"
            assert "typing" in res["tags"]
