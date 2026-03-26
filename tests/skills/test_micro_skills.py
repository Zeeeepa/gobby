"""Tests for micro-skills (guardrail skills)."""

from pathlib import Path

import pytest

from gobby.skills.loader import SkillLoader

pytestmark = pytest.mark.unit


class TestSourceControlSkill:
    """Tests for the source-control micro-skill."""

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

    def test_source_control_skill_exists(self, skills_dir: Path) -> None:
        """Verify source-control skill directory exists."""
        skill_dir = skills_dir / "source-control"
        assert skill_dir.exists(), f"Expected skill directory: {skill_dir}"

    def test_source_control_skill_content_mentions_commit_workflow(
        self, skill_loader: SkillLoader, skills_dir: Path
    ) -> None:
        """Verify skill content covers commit workflow."""
        skill_path = skills_dir / "source-control"
        skill = skill_loader.load_skill(skill_path)

        content = skill.content.lower()
        # Should mention commit and close workflow
        assert "commit" in content
        assert "close_task" in content or "close task" in content
