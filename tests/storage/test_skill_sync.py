"""Tests for bundled skill synchronization on daemon startup."""

from pathlib import Path

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.skills import LocalSkillManager

pytestmark = pytest.mark.unit

class TestSyncBundledSkills:
    """Test sync_bundled_skills function."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> LocalDatabase:
        """Create a test database."""
        db_path = tmp_path / "test.db"
        db = LocalDatabase(db_path)
        # Run migrations to create skills table
        from gobby.storage.migrations import run_migrations

        run_migrations(db)
        return db

    @pytest.fixture
    def skill_manager(self, db: LocalDatabase) -> LocalSkillManager:
        """Create a skill manager."""
        return LocalSkillManager(db)

    def test_sync_bundled_skills_imports_successfully(self) -> None:
        """Verify sync_bundled_skills can be imported."""
        from gobby.skills.sync import sync_bundled_skills

        assert callable(sync_bundled_skills)

    def test_sync_bundled_skills_creates_skills_in_db(
        self, db: LocalDatabase, skill_manager: LocalSkillManager
    ) -> None:
        """Verify bundled skills are synced to database."""
        from gobby.skills.sync import sync_bundled_skills

        # Initially no skills
        skills_before = skill_manager.list_skills(include_global=True)
        assert len(skills_before) == 0

        # Sync bundled skills
        result = sync_bundled_skills(db)

        # Should have synced skills
        assert result["success"] is True
        assert result["synced"] > 0

        # Verify skills now exist in database
        skills_after = skill_manager.list_skills(include_global=True)
        assert len(skills_after) > 0

    def test_sync_bundled_skills_includes_core_skills(
        self, db: LocalDatabase, skill_manager: LocalSkillManager
    ) -> None:
        """Verify specific core skills are synced."""
        from gobby.skills.sync import sync_bundled_skills

        sync_bundled_skills(db)

        # Check for known core skills
        gobby_tasks = skill_manager.get_by_name("gobby-tasks")
        assert gobby_tasks is not None
        assert gobby_tasks.name == "gobby-tasks"
        assert len(gobby_tasks.content) > 0

        gobby_workflows = skill_manager.get_by_name("gobby-workflows")
        assert gobby_workflows is not None

    def test_sync_bundled_skills_is_idempotent(
        self, db: LocalDatabase, skill_manager: LocalSkillManager
    ) -> None:
        """Verify syncing twice doesn't create duplicates."""
        from gobby.skills.sync import sync_bundled_skills

        # First sync
        sync_bundled_skills(db)
        count1 = len(skill_manager.list_skills(include_global=True))

        # Second sync
        result2 = sync_bundled_skills(db)
        count2 = len(skill_manager.list_skills(include_global=True))

        # Same count - no duplicates
        assert count1 == count2
        assert result2["skipped"] > 0 or result2["synced"] == 0

    def test_sync_bundled_skills_sets_source_type_filesystem(
        self, db: LocalDatabase, skill_manager: LocalSkillManager
    ) -> None:
        """Verify synced skills have source_type='filesystem'."""
        from gobby.skills.sync import sync_bundled_skills

        sync_bundled_skills(db)

        skill = skill_manager.get_by_name("gobby-tasks")
        assert skill is not None
        assert skill.source_type == "filesystem"

    def test_sync_bundled_skills_skills_are_global(
        self, db: LocalDatabase, skill_manager: LocalSkillManager
    ) -> None:
        """Verify synced skills have project_id=None (global scope)."""
        from gobby.skills.sync import sync_bundled_skills

        sync_bundled_skills(db)

        skill = skill_manager.get_by_name("gobby-tasks")
        assert skill is not None
        assert skill.project_id is None
