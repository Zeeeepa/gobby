"""Tests for micro-skills (guardrail skills)."""

from pathlib import Path

import pytest

from gobby.skills.loader import SkillLoader


class TestStartingSessionsSkill:
    """Tests for the starting-sessions micro-skill."""

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

    def test_starting_sessions_skill_exists(self, skills_dir: Path) -> None:
        """Verify starting-sessions skill directory exists."""
        skill_dir = skills_dir / "starting-sessions"
        assert skill_dir.exists(), f"Expected skill directory: {skill_dir}"
        assert (skill_dir / "SKILL.md").exists(), "Missing SKILL.md"

    def test_starting_sessions_skill_loadable(
        self, skill_loader: SkillLoader, skills_dir: Path
    ) -> None:
        """Verify skill can be loaded by SkillLoader."""
        skill_path = skills_dir / "starting-sessions"
        skill = skill_loader.load_skill(skill_path)

        assert skill is not None
        assert skill.name == "starting-sessions"
        assert len(skill.description) > 0
        assert len(skill.content) > 0

    def test_starting_sessions_skill_has_valid_metadata(
        self, skill_loader: SkillLoader, skills_dir: Path
    ) -> None:
        """Verify skill has required metadata."""
        skill_path = skills_dir / "starting-sessions"
        skill = skill_loader.load_skill(skill_path)

        # Check metadata
        assert skill.name == "starting-sessions"
        assert "session" in skill.description.lower()

    def test_starting_sessions_skill_content_mentions_key_steps(
        self, skill_loader: SkillLoader, skills_dir: Path
    ) -> None:
        """Verify skill content covers the startup checklist."""
        skill_path = skills_dir / "starting-sessions"
        skill = skill_loader.load_skill(skill_path)

        content = skill.content.lower()
        # Should mention key startup steps
        assert "list_mcp_servers" in content
        assert "list_skills" in content or "skill" in content
        assert "session_id" in content or "session" in content


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
