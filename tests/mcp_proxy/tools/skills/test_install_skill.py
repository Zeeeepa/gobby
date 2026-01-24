"""Tests for install_skill MCP tool (TDD - written before implementation)."""

import zipfile
from collections.abc import Generator
from pathlib import Path

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.skills import LocalSkillManager

pytestmark = pytest.mark.integration


@pytest.fixture
def db(tmp_path: Path) -> Generator[LocalDatabase]:
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
def skill_dir(tmp_path: Path) -> Path:
    """Create a skill directory with SKILL.md."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill for installation
version: "1.0.0"
---

# Test Skill

This is a test skill.
""")
    return skill_dir


@pytest.fixture
def skill_zip(tmp_path: Path) -> Path:
    """Create a ZIP archive containing a skill."""
    skill_dir = tmp_path / "zip-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
name: zip-skill
description: A skill from a ZIP file
version: "1.0.0"
---

# ZIP Skill

Content from ZIP.
""")

    zip_path = tmp_path / "skill.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(skill_dir / "SKILL.md", "zip-skill/SKILL.md")

    return zip_path


class TestInstallSkillTool:
    """Tests for install_skill MCP tool."""

    @pytest.mark.asyncio
    async def test_install_skill_from_local_path(self, db, storage, skill_dir):
        """Test installing a skill from a local directory path."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(db)
        tool = registry.get_tool("install_skill")

        result = await tool(source=str(skill_dir))

        assert result["success"] is True
        assert result["installed"] is True
        assert result["skill_name"] == "test-skill"
        assert result["source_type"] == "local"

        # Verify skill is in storage
        skill = storage.get_by_name("test-skill")
        assert skill is not None
        assert skill.source_type == "local"

    @pytest.mark.asyncio
    async def test_install_skill_from_local_file(self, db, storage, skill_dir):
        """Test installing a skill from a SKILL.md file path."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(db)
        tool = registry.get_tool("install_skill")

        skill_file = skill_dir / "SKILL.md"
        result = await tool(source=str(skill_file))

        assert result["success"] is True
        assert result["skill_name"] == "test-skill"

    @pytest.mark.asyncio
    async def test_install_skill_from_zip(self, db, storage, skill_zip):
        """Test installing a skill from a ZIP archive."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(db)
        tool = registry.get_tool("install_skill")

        result = await tool(source=str(skill_zip))

        assert result["success"] is True
        assert result["installed"] is True
        assert result["skill_name"] == "zip-skill"
        assert result["source_type"] == "zip"

        # Verify skill is in storage
        skill = storage.get_by_name("zip-skill")
        assert skill is not None

    @pytest.mark.asyncio
    async def test_install_skill_auto_detects_source_type(self, db, storage, skill_dir, skill_zip):
        """Test that install_skill auto-detects the source type."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(db)
        tool = registry.get_tool("install_skill")

        # Local directory
        result1 = await tool(source=str(skill_dir))
        assert result1["source_type"] == "local"

        # ZIP file
        result2 = await tool(source=str(skill_zip))
        assert result2["source_type"] == "zip"

    @pytest.mark.asyncio
    async def test_install_skill_github_url(self, db, storage, mocker):
        """Test installing a skill from a GitHub URL (mocked)."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        # Mock the SkillLoader to avoid actual GitHub clone
        mock_skill = mocker.MagicMock()
        mock_skill.name = "github-skill"
        mock_skill.description = "A skill from GitHub"
        mock_skill.content = "# GitHub Skill"
        mock_skill.source_type = "github"
        mock_skill.source_path = "github:owner/repo"
        mock_skill.source_ref = None
        mock_skill.version = "1.0"
        mock_skill.license = None
        mock_skill.compatibility = None
        mock_skill.allowed_tools = None
        mock_skill.metadata = {}

        mocker.patch(
            "gobby.skills.loader.SkillLoader.load_from_github",
            return_value=mock_skill,
        )

        registry = create_skills_registry(db)
        tool = registry.get_tool("install_skill")

        result = await tool(source="github:owner/repo")

        assert result["success"] is True
        assert result["skill_name"] == "github-skill"
        assert result["source_type"] == "github"

    @pytest.mark.asyncio
    async def test_install_skill_returns_skill_id(self, db, storage, skill_dir):
        """Test that install_skill returns the installed skill's ID."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(db)
        tool = registry.get_tool("install_skill")

        result = await tool(source=str(skill_dir))

        assert result["success"] is True
        assert "skill_id" in result
        assert result["skill_id"] is not None

    @pytest.mark.asyncio
    async def test_install_skill_project_scoped_param_accepted(self, db, storage, skill_dir):
        """Test that project_scoped parameter is accepted (installs globally when False)."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(db)
        tool = registry.get_tool("install_skill")

        # With project_scoped=False (default), skill is installed globally
        result = await tool(source=str(skill_dir), project_scoped=False)

        assert result["success"] is True
        assert result["skill_name"] == "test-skill"
        # Skill should be findable globally
        skill = storage.get_by_name("test-skill")
        assert skill is not None

    @pytest.mark.asyncio
    async def test_install_skill_source_not_found(self, db, tmp_path):
        """Test that install_skill returns error for non-existent source."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(db)
        tool = registry.get_tool("install_skill")

        result = await tool(source=str(tmp_path / "nonexistent"))

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_install_skill_invalid_skill(self, db, tmp_path):
        """Test that install_skill returns error for invalid skill."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        # Create invalid skill
        invalid_dir = tmp_path / "invalid-skill"
        invalid_dir.mkdir()
        (invalid_dir / "SKILL.md").write_text("""---
name: ""
---
Content
""")

        registry = create_skills_registry(db)
        tool = registry.get_tool("install_skill")

        result = await tool(source=str(invalid_dir))

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_install_skill_requires_source(self, db):
        """Test that install_skill requires source parameter."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(db)
        tool = registry.get_tool("install_skill")

        result = await tool()

        assert result["success"] is False
        assert "source" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_install_skill_updates_search_index(self, db, storage, skill_dir):
        """Test that installing a skill updates the search index."""
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        registry = create_skills_registry(db)
        install_tool = registry.get_tool("install_skill")
        search_tool = registry.get_tool("search_skills")

        # Install skill
        await install_tool(source=str(skill_dir))

        # Search should find it
        result = await search_tool(query="test skill")

        assert result["success"] is True
        assert result["count"] > 0
        assert any(r["skill_name"] == "test-skill" for r in result["results"])
