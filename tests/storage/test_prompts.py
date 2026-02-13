"""Tests for prompt storage module (three-tier prompt registry).

Covers: table creation via migration, save_prompt with all tiers,
get_prompt by path with tier precedence (project > user > bundled),
list_prompts with deduplication, delete_prompt, reset_to_bundled,
get_bundled, unique constraint enforcement.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.prompts import LocalPromptManager, PromptRecord

pytestmark = pytest.mark.unit


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def prompt_manager(temp_db: LocalDatabase) -> LocalPromptManager:
    """Create a LocalPromptManager backed by the temp database."""
    return LocalPromptManager(temp_db)


@pytest.fixture
def project_id(temp_db: LocalDatabase) -> str:
    """Create a test project and return its ID."""
    pid = str(uuid.uuid4())
    temp_db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        (pid, f"test-project-{pid[:8]}"),
    )
    return pid


# =============================================================================
# Table existence
# =============================================================================


class TestPromptsTableExists:
    def test_prompts_table_created_by_migration(self, temp_db: LocalDatabase) -> None:
        """The prompts table should exist after migrations run."""
        row = temp_db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='prompts'"
        )
        assert row is not None
        assert row["name"] == "prompts"

    def test_unique_constraint_exists(self, temp_db: LocalDatabase) -> None:
        """UNIQUE(path, tier, project_id) should be enforced."""
        now = "2025-01-01T00:00:00"
        temp_db.execute(
            """INSERT INTO prompts (id, path, category, content, tier, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("id1", "test/prompt", "test", "content", "bundled", now, now),
        )
        with pytest.raises(sqlite3.IntegrityError):
            temp_db.execute(
                """INSERT INTO prompts (id, path, category, content, tier, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("id2", "test/prompt", "test", "content2", "bundled", now, now),
            )


# =============================================================================
# save_prompt
# =============================================================================


class TestSavePrompt:
    def test_save_bundled_prompt(self, prompt_manager: LocalPromptManager) -> None:
        record = prompt_manager.save_prompt(
            path="expansion/system",
            content="You are a system prompt.",
            tier="bundled",
            name="expansion-system",
            description="System prompt for expansion",
        )
        assert record.path == "expansion/system"
        assert record.tier == "bundled"
        assert record.content == "You are a system prompt."
        assert record.category == "expansion"

    def test_save_user_prompt(self, prompt_manager: LocalPromptManager) -> None:
        record = prompt_manager.save_prompt(
            path="expansion/system",
            content="Custom content",
            tier="user",
        )
        assert record.tier == "user"
        assert record.content == "Custom content"

    def test_save_project_prompt(
        self, prompt_manager: LocalPromptManager, project_id: str
    ) -> None:
        record = prompt_manager.save_prompt(
            path="expansion/system",
            content="Project content",
            tier="project",
            project_id=project_id,
        )
        assert record.tier == "project"
        assert record.project_id == project_id

    def test_save_project_without_project_id_raises(
        self, prompt_manager: LocalPromptManager
    ) -> None:
        with pytest.raises(ValueError, match="project_id is required"):
            prompt_manager.save_prompt(
                path="test/prompt",
                content="content",
                tier="project",
            )

    def test_save_invalid_tier_raises(self, prompt_manager: LocalPromptManager) -> None:
        with pytest.raises(ValueError, match="Invalid tier"):
            prompt_manager.save_prompt(
                path="test/prompt",
                content="content",
                tier="invalid",
            )

    def test_upsert_updates_existing(self, prompt_manager: LocalPromptManager) -> None:
        r1 = prompt_manager.save_prompt(
            path="test/prompt", content="v1", tier="bundled"
        )
        r2 = prompt_manager.save_prompt(
            path="test/prompt", content="v2", tier="bundled"
        )
        assert r1.id == r2.id
        assert r2.content == "v2"

    def test_category_derived_from_path(self, prompt_manager: LocalPromptManager) -> None:
        record = prompt_manager.save_prompt(
            path="validation/criteria", content="content", tier="bundled"
        )
        assert record.category == "validation"

    def test_category_general_for_flat_path(self, prompt_manager: LocalPromptManager) -> None:
        record = prompt_manager.save_prompt(
            path="standalone", content="content", tier="bundled"
        )
        assert record.category == "general"

    def test_variables_serialized(self, prompt_manager: LocalPromptManager) -> None:
        variables = {"task_type": {"type": "str", "default": "task"}}
        record = prompt_manager.save_prompt(
            path="test/vars", content="content", tier="bundled", variables=variables
        )
        assert record.variables == variables


# =============================================================================
# get_prompt (tier precedence)
# =============================================================================


class TestGetPrompt:
    def test_get_bundled(self, prompt_manager: LocalPromptManager) -> None:
        prompt_manager.save_prompt(
            path="test/prompt", content="bundled", tier="bundled"
        )
        record = prompt_manager.get_prompt("test/prompt")
        assert record is not None
        assert record.content == "bundled"

    def test_user_overrides_bundled(self, prompt_manager: LocalPromptManager) -> None:
        prompt_manager.save_prompt(
            path="test/prompt", content="bundled", tier="bundled"
        )
        prompt_manager.save_prompt(
            path="test/prompt", content="user override", tier="user"
        )
        record = prompt_manager.get_prompt("test/prompt")
        assert record is not None
        assert record.content == "user override"
        assert record.tier == "user"

    def test_project_overrides_user(
        self, prompt_manager: LocalPromptManager, project_id: str
    ) -> None:
        prompt_manager.save_prompt(
            path="test/prompt", content="bundled", tier="bundled"
        )
        prompt_manager.save_prompt(
            path="test/prompt", content="user", tier="user"
        )
        prompt_manager.save_prompt(
            path="test/prompt",
            content="project",
            tier="project",
            project_id=project_id,
        )
        record = prompt_manager.get_prompt("test/prompt", project_id=project_id)
        assert record is not None
        assert record.content == "project"
        assert record.tier == "project"

    def test_nonexistent_returns_none(self, prompt_manager: LocalPromptManager) -> None:
        assert prompt_manager.get_prompt("nonexistent") is None


# =============================================================================
# get_bundled
# =============================================================================


class TestGetBundled:
    def test_returns_bundled_tier(self, prompt_manager: LocalPromptManager) -> None:
        prompt_manager.save_prompt(
            path="test/prompt", content="bundled content", tier="bundled"
        )
        prompt_manager.save_prompt(
            path="test/prompt", content="user content", tier="user"
        )
        bundled = prompt_manager.get_bundled("test/prompt")
        assert bundled is not None
        assert bundled.content == "bundled content"
        assert bundled.tier == "bundled"

    def test_returns_none_if_no_bundled(self, prompt_manager: LocalPromptManager) -> None:
        prompt_manager.save_prompt(
            path="test/prompt", content="user only", tier="user"
        )
        assert prompt_manager.get_bundled("test/prompt") is None


# =============================================================================
# list_prompts
# =============================================================================


class TestListPrompts:
    def test_list_all_deduplicated(self, prompt_manager: LocalPromptManager) -> None:
        prompt_manager.save_prompt(
            path="a/prompt", content="bundled", tier="bundled"
        )
        prompt_manager.save_prompt(
            path="a/prompt", content="user override", tier="user"
        )
        prompt_manager.save_prompt(
            path="b/prompt", content="bundled", tier="bundled"
        )
        results = prompt_manager.list_prompts()
        assert len(results) == 2
        paths = [r.path for r in results]
        assert paths == ["a/prompt", "b/prompt"]
        # user should win over bundled for a/prompt
        a_record = next(r for r in results if r.path == "a/prompt")
        assert a_record.tier == "user"

    def test_list_by_tier(self, prompt_manager: LocalPromptManager) -> None:
        prompt_manager.save_prompt(
            path="test/prompt", content="bundled", tier="bundled"
        )
        prompt_manager.save_prompt(
            path="test/prompt", content="user", tier="user"
        )
        bundled = prompt_manager.list_prompts(tier="bundled")
        assert len(bundled) == 1
        assert bundled[0].tier == "bundled"

    def test_list_by_category(self, prompt_manager: LocalPromptManager) -> None:
        prompt_manager.save_prompt(
            path="expansion/system", content="c1", tier="bundled"
        )
        prompt_manager.save_prompt(
            path="validation/criteria", content="c2", tier="bundled"
        )
        results = prompt_manager.list_prompts(category="expansion")
        assert len(results) == 1
        assert results[0].path == "expansion/system"


# =============================================================================
# delete_prompt
# =============================================================================


class TestDeletePrompt:
    def test_delete_existing(self, prompt_manager: LocalPromptManager) -> None:
        prompt_manager.save_prompt(
            path="test/prompt", content="content", tier="user"
        )
        assert prompt_manager.delete_prompt("test/prompt", "user") is True
        assert prompt_manager.get_prompt("test/prompt") is None

    def test_delete_nonexistent(self, prompt_manager: LocalPromptManager) -> None:
        assert prompt_manager.delete_prompt("nonexistent", "user") is False


# =============================================================================
# reset_to_bundled
# =============================================================================


class TestResetToBundled:
    def test_reset_removes_user_override(self, prompt_manager: LocalPromptManager) -> None:
        prompt_manager.save_prompt(
            path="test/prompt", content="bundled", tier="bundled"
        )
        prompt_manager.save_prompt(
            path="test/prompt", content="user", tier="user"
        )
        assert prompt_manager.reset_to_bundled("test/prompt") is True
        record = prompt_manager.get_prompt("test/prompt")
        assert record is not None
        assert record.tier == "bundled"

    def test_reset_with_project(
        self, prompt_manager: LocalPromptManager, project_id: str
    ) -> None:
        prompt_manager.save_prompt(
            path="test/prompt", content="bundled", tier="bundled"
        )
        prompt_manager.save_prompt(
            path="test/prompt", content="user", tier="user"
        )
        prompt_manager.save_prompt(
            path="test/prompt",
            content="project",
            tier="project",
            project_id=project_id,
        )
        assert prompt_manager.reset_to_bundled("test/prompt", project_id=project_id) is True
        record = prompt_manager.get_prompt("test/prompt", project_id=project_id)
        assert record is not None
        assert record.tier == "bundled"


# =============================================================================
# to_template conversion
# =============================================================================


class TestToTemplate:
    def test_converts_to_prompt_template(self, prompt_manager: LocalPromptManager) -> None:
        variables = {"mode": {"type": "str", "default": "auto", "required": False}}
        record = prompt_manager.save_prompt(
            path="test/prompt",
            content="Hello {{ mode }}",
            tier="bundled",
            description="Test prompt",
            version="2.0",
            variables=variables,
        )
        template = record.to_template()
        assert template.name == "test/prompt"
        assert template.description == "Test prompt"
        assert template.version == "2.0"
        assert template.content == "Hello {{ mode }}"
        assert "mode" in template.variables
        assert template.variables["mode"].default == "auto"


# =============================================================================
# list_bundled_paths
# =============================================================================


class TestListBundledPaths:
    def test_returns_bundled_paths(self, prompt_manager: LocalPromptManager) -> None:
        prompt_manager.save_prompt(path="a/one", content="c", tier="bundled")
        prompt_manager.save_prompt(path="b/two", content="c", tier="bundled")
        prompt_manager.save_prompt(path="a/one", content="c", tier="user")
        paths = prompt_manager.list_bundled_paths()
        assert paths == {"a/one", "b/two"}
