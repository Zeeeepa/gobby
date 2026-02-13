"""Tests for prompt sync module.

Covers: sync_bundled_prompts, migrate_file_overrides_to_db.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.prompts import LocalPromptManager

pytestmark = pytest.mark.unit


@pytest.fixture
def prompt_manager(temp_db: LocalDatabase) -> LocalPromptManager:
    return LocalPromptManager(temp_db)


@pytest.fixture
def prompts_dir(temp_dir: Path) -> Path:
    """Create a temp directory with test prompt files."""
    d = temp_dir / "prompts"

    # expansion/system.md
    (d / "expansion").mkdir(parents=True)
    (d / "expansion" / "system.md").write_text(
        "---\nname: expansion-system\ndescription: System prompt\nversion: '1.1'\n---\n"
        "You are a system prompt.\n",
        encoding="utf-8",
    )

    # validation/criteria.md (no frontmatter)
    (d / "validation").mkdir(parents=True)
    (d / "validation" / "criteria.md").write_text(
        "Validate the task.\n",
        encoding="utf-8",
    )

    return d


class TestSyncBundledPrompts:
    def test_syncs_new_prompts(
        self, temp_db: LocalDatabase, prompts_dir: Path
    ) -> None:
        from gobby.prompts.sync import sync_bundled_prompts

        result = sync_bundled_prompts(temp_db, prompts_dir=prompts_dir)
        assert result["synced"] == 2
        assert result["skipped"] == 0
        assert result["errors"] == []

        manager = LocalPromptManager(temp_db)
        record = manager.get_bundled("expansion/system")
        assert record is not None
        assert record.name == "expansion-system"
        assert record.content == "You are a system prompt."
        assert record.version == "1.1"
        assert record.category == "expansion"

    def test_skips_unchanged_prompts(
        self, temp_db: LocalDatabase, prompts_dir: Path
    ) -> None:
        from gobby.prompts.sync import sync_bundled_prompts

        sync_bundled_prompts(temp_db, prompts_dir=prompts_dir)
        result = sync_bundled_prompts(temp_db, prompts_dir=prompts_dir)
        assert result["synced"] == 0
        assert result["skipped"] == 2

    def test_updates_changed_prompts(
        self, temp_db: LocalDatabase, prompts_dir: Path
    ) -> None:
        from gobby.prompts.sync import sync_bundled_prompts

        sync_bundled_prompts(temp_db, prompts_dir=prompts_dir)

        # Modify the file
        (prompts_dir / "expansion" / "system.md").write_text(
            "---\nname: expansion-system\ndescription: Updated\nversion: '2.0'\n---\n"
            "Updated content.\n",
            encoding="utf-8",
        )

        result = sync_bundled_prompts(temp_db, prompts_dir=prompts_dir)
        assert result["updated"] == 1

        manager = LocalPromptManager(temp_db)
        record = manager.get_bundled("expansion/system")
        assert record is not None
        assert record.content == "Updated content."
        assert record.version == "2.0"

    def test_removes_stale_prompts(
        self, temp_db: LocalDatabase, prompts_dir: Path
    ) -> None:
        from gobby.prompts.sync import sync_bundled_prompts

        sync_bundled_prompts(temp_db, prompts_dir=prompts_dir)

        # Delete a file
        (prompts_dir / "validation" / "criteria.md").unlink()

        result = sync_bundled_prompts(temp_db, prompts_dir=prompts_dir)
        assert result["removed"] == 1

        manager = LocalPromptManager(temp_db)
        assert manager.get_bundled("validation/criteria") is None

    def test_nonexistent_dir_returns_empty(self, temp_db: LocalDatabase) -> None:
        from gobby.prompts.sync import sync_bundled_prompts

        result = sync_bundled_prompts(temp_db, prompts_dir=Path("/nonexistent"))
        assert result["synced"] == 0


class TestMigrateFileOverrides:
    def test_migrates_file_overrides_to_db(
        self, temp_db: LocalDatabase, temp_dir: Path
    ) -> None:
        from gobby.prompts.sync import migrate_file_overrides_to_db

        overrides_dir = temp_dir / "prompts"
        (overrides_dir / "expansion").mkdir(parents=True)
        (overrides_dir / "expansion" / "system.md").write_text(
            "---\nname: custom-expansion\n---\nCustom expansion prompt.\n",
            encoding="utf-8",
        )

        result = migrate_file_overrides_to_db(temp_db, overrides_dir=overrides_dir)
        assert result["migrated"] == 1

        manager = LocalPromptManager(temp_db)
        record = manager.get_prompt("expansion/system")
        assert record is not None
        assert record.tier == "user"
        assert record.content == "Custom expansion prompt."

        # Directory should be renamed
        assert not overrides_dir.exists()
        assert (temp_dir / "prompts.migrated").exists()

    def test_nonexistent_dir_no_op(self, temp_db: LocalDatabase) -> None:
        from gobby.prompts.sync import migrate_file_overrides_to_db

        result = migrate_file_overrides_to_db(
            temp_db, overrides_dir=Path("/nonexistent")
        )
        assert result["migrated"] == 0
