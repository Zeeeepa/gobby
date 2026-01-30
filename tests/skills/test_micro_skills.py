"""Tests for micro-skills (guardrail skills)."""

from pathlib import Path

import pytest

from gobby.skills.loader import SkillLoader

pytestmark = pytest.mark.unit


class TestClaimingTasksSkill:
    """Tests for the claiming-tasks micro-skill."""

    @pytest.fixture
    def skill_loader(self) -> SkillLoader:
        """Create a skill loader."""
        return SkillLoader(default_source_type="filesystem")

    @pytest.fixture
    def skills_dir(self) -> Path:
        """Path to bundled skills directory."""
        return (
            Path(__file__).parent.parent.parent / "src" / "gobby" / "install" / "shared" / "skills"
        )

    def test_claiming_tasks_skill_exists(self, skills_dir: Path) -> None:
        """Verify claiming-tasks skill directory exists."""
        skill_dir = skills_dir / "claiming-tasks"
        assert skill_dir.exists(), f"Expected skill directory: {skill_dir}"

    def test_claiming_tasks_skill_loadable(
        self, skill_loader: SkillLoader, skills_dir: Path
    ) -> None:
        """Verify skill can be loaded by SkillLoader."""
        skill_path = skills_dir / "claiming-tasks"
        skill = skill_loader.load_skill(skill_path)

        assert skill is not None
        assert skill.name == "claiming-tasks"
        assert "task" in skill.description.lower()


class TestDiscoveringToolsSkill:
    """Tests for the discovering-tools micro-skill."""

    @pytest.fixture
    def skill_loader(self) -> SkillLoader:
        """Create a skill loader."""
        return SkillLoader(default_source_type="filesystem")

    @pytest.fixture
    def skills_dir(self) -> Path:
        """Path to bundled skills directory."""
        return (
            Path(__file__).parent.parent.parent / "src" / "gobby" / "install" / "shared" / "skills"
        )

    def test_discovering_tools_skill_exists(self, skills_dir: Path) -> None:
        """Verify discovering-tools skill directory exists."""
        skill_dir = skills_dir / "discovering-tools"
        assert skill_dir.exists(), f"Expected skill directory: {skill_dir}"

    def test_discovering_tools_skill_content_mentions_progressive_disclosure(
        self, skill_loader: SkillLoader, skills_dir: Path
    ) -> None:
        """Verify skill content covers progressive disclosure."""
        skill_path = skills_dir / "discovering-tools"
        skill = skill_loader.load_skill(skill_path)

        content = skill.content.lower()
        # Should mention progressive disclosure pattern
        assert "list_tools" in content
        assert "get_tool_schema" in content


class TestCommittingChangesSkill:
    """Tests for the committing-changes micro-skill."""

    @pytest.fixture
    def skill_loader(self) -> SkillLoader:
        """Create a skill loader."""
        return SkillLoader(default_source_type="filesystem")

    @pytest.fixture
    def skills_dir(self) -> Path:
        """Path to bundled skills directory."""
        return (
            Path(__file__).parent.parent.parent / "src" / "gobby" / "install" / "shared" / "skills"
        )

    def test_committing_changes_skill_exists(self, skills_dir: Path) -> None:
        """Verify committing-changes skill directory exists."""
        skill_dir = skills_dir / "committing-changes"
        assert skill_dir.exists(), f"Expected skill directory: {skill_dir}"

    def test_committing_changes_skill_content_mentions_commit_workflow(
        self, skill_loader: SkillLoader, skills_dir: Path
    ) -> None:
        """Verify skill content covers commit workflow."""
        skill_path = skills_dir / "committing-changes"
        skill = skill_loader.load_skill(skill_path)

        content = skill.content.lower()
        # Should mention commit and close workflow
        assert "commit" in content
        assert "close_task" in content or "close task" in content
