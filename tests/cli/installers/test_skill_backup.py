"""Tests for skill backup logic during installation."""

from pathlib import Path

import pytest

from gobby.cli.installers.shared import backup_gobby_skills

pytestmark = pytest.mark.unit

class TestBackupGobbySkills:
    """Tests for backup_gobby_skills function."""

    @pytest.fixture
    def skills_dir(self, tmp_path: Path) -> Path:
        """Create a mock .claude/skills directory."""
        skills = tmp_path / ".claude" / "skills"
        skills.mkdir(parents=True)
        return skills

    def test_backup_function_exists(self) -> None:
        """Verify backup_gobby_skills function can be imported."""
        from gobby.cli.installers.shared import backup_gobby_skills

        assert callable(backup_gobby_skills)

    def test_backup_moves_gobby_skill_dirs(self, tmp_path: Path, skills_dir: Path) -> None:
        """Verify gobby-prefixed skill directories are moved to backup."""
        # Create some gobby skills
        (skills_dir / "gobby-tasks").mkdir()
        (skills_dir / "gobby-tasks" / "SKILL.md").write_text("# gobby-tasks")
        (skills_dir / "gobby-workflows").mkdir()
        (skills_dir / "gobby-workflows" / "SKILL.md").write_text("# gobby-workflows")

        # Create a non-gobby skill (should NOT be moved)
        (skills_dir / "my-custom-skill").mkdir()
        (skills_dir / "my-custom-skill" / "SKILL.md").write_text("# my-custom-skill")

        result = backup_gobby_skills(skills_dir)

        # Check results
        assert result["success"] is True
        assert result["backed_up"] == 2  # gobby-tasks and gobby-workflows

        # Verify backup directory exists
        backup_dir = tmp_path / ".claude" / "skills.backup"
        assert backup_dir.exists()
        assert (backup_dir / "gobby-tasks").exists()
        assert (backup_dir / "gobby-workflows").exists()

        # Verify gobby skills are gone from original location
        assert not (skills_dir / "gobby-tasks").exists()
        assert not (skills_dir / "gobby-workflows").exists()

        # Verify non-gobby skill is still there
        assert (skills_dir / "my-custom-skill").exists()

    def test_backup_does_nothing_if_no_gobby_skills(self, skills_dir: Path) -> None:
        """Verify nothing happens if no gobby skills exist."""
        # Create only non-gobby skills
        (skills_dir / "my-custom-skill").mkdir()
        (skills_dir / "my-custom-skill" / "SKILL.md").write_text("# custom")

        result = backup_gobby_skills(skills_dir)

        assert result["success"] is True
        assert result["backed_up"] == 0
        # No backup directory should be created
        backup_dir = skills_dir.parent / "skills.backup"
        assert not backup_dir.exists()

    def test_backup_does_nothing_if_skills_dir_missing(self, tmp_path: Path) -> None:
        """Verify graceful handling of missing skills directory."""
        nonexistent = tmp_path / ".claude" / "skills"

        result = backup_gobby_skills(nonexistent)

        assert result["success"] is True
        assert result["backed_up"] == 0
        assert result.get("skipped") == "skills directory does not exist"

    def test_backup_handles_existing_backup_dir(self, tmp_path: Path, skills_dir: Path) -> None:
        """Verify backup works even if backup dir already exists."""
        # Create existing backup dir with old content
        backup_dir = tmp_path / ".claude" / "skills.backup"
        backup_dir.mkdir(parents=True)
        (backup_dir / "gobby-old").mkdir()

        # Create new gobby skill
        (skills_dir / "gobby-tasks").mkdir()
        (skills_dir / "gobby-tasks" / "SKILL.md").write_text("# new")

        result = backup_gobby_skills(skills_dir)

        assert result["success"] is True
        assert result["backed_up"] == 1
        # Both old and new should exist in backup
        assert (backup_dir / "gobby-old").exists()
        assert (backup_dir / "gobby-tasks").exists()
