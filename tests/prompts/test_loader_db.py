"""Tests for PromptLoader with database-backed resolution.

Covers: DB-first load, cache behavior, exists, list_templates,
configure_default_loader.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gobby.prompts.loader import PromptLoader, configure_default_loader, get_default_loader
from gobby.storage.database import LocalDatabase
from gobby.storage.prompts import LocalPromptManager

pytestmark = pytest.mark.unit


@pytest.fixture
def prompt_manager(temp_db: LocalDatabase) -> LocalPromptManager:
    return LocalPromptManager(temp_db)


@pytest.fixture
def db_loader(temp_db: LocalDatabase) -> PromptLoader:
    """Create a PromptLoader with DB backing and no file search paths."""
    return PromptLoader(
        db=temp_db,
        defaults_dir=Path("/nonexistent"),
        global_dir=Path("/nonexistent"),
    )


class TestLoaderDbResolution:
    def test_load_from_db(
        self, db_loader: PromptLoader, prompt_manager: LocalPromptManager
    ) -> None:
        prompt_manager.save_prompt(
            path="test/prompt",
            content="DB content",
            tier="bundled",
            description="Test",
        )
        template = db_loader.load("test/prompt")
        assert template.content == "DB content"
        assert template.name == "test/prompt"

    def test_db_tier_precedence(
        self, db_loader: PromptLoader, prompt_manager: LocalPromptManager
    ) -> None:
        prompt_manager.save_prompt(
            path="test/prompt", content="bundled", tier="bundled"
        )
        prompt_manager.save_prompt(
            path="test/prompt", content="user override", tier="user"
        )
        template = db_loader.load("test/prompt")
        assert template.content == "user override"

    def test_cache_hit(
        self, db_loader: PromptLoader, prompt_manager: LocalPromptManager
    ) -> None:
        prompt_manager.save_prompt(
            path="test/prompt", content="original", tier="bundled"
        )
        t1 = db_loader.load("test/prompt")
        # Update in DB
        prompt_manager.save_prompt(
            path="test/prompt", content="updated", tier="bundled"
        )
        # Should still get cached version
        t2 = db_loader.load("test/prompt")
        assert t1.content == t2.content == "original"

        # After clear_cache, should get updated version
        db_loader.clear_cache()
        t3 = db_loader.load("test/prompt")
        assert t3.content == "updated"

    def test_not_found_raises(self, db_loader: PromptLoader) -> None:
        with pytest.raises(FileNotFoundError):
            db_loader.load("nonexistent/prompt")

    def test_exists_checks_db(
        self, db_loader: PromptLoader, prompt_manager: LocalPromptManager
    ) -> None:
        assert db_loader.exists("test/prompt") is False
        prompt_manager.save_prompt(
            path="test/prompt", content="content", tier="bundled"
        )
        assert db_loader.exists("test/prompt") is True

    def test_list_templates_includes_db(
        self, db_loader: PromptLoader, prompt_manager: LocalPromptManager
    ) -> None:
        prompt_manager.save_prompt(
            path="a/one", content="c", tier="bundled", category="a"
        )
        prompt_manager.save_prompt(
            path="b/two", content="c", tier="bundled", category="b"
        )
        templates = db_loader.list_templates()
        assert templates == ["a/one", "b/two"]

    def test_list_templates_with_category(
        self, db_loader: PromptLoader, prompt_manager: LocalPromptManager
    ) -> None:
        prompt_manager.save_prompt(
            path="a/one", content="c", tier="bundled", category="a"
        )
        prompt_manager.save_prompt(
            path="b/two", content="c", tier="bundled", category="b"
        )
        templates = db_loader.list_templates(category="a")
        assert templates == ["a/one"]


class TestConfigureDefaultLoader:
    def test_configure_default_loader(self, temp_db: LocalDatabase) -> None:
        import gobby.prompts.loader as loader_mod

        # Reset module state
        loader_mod._default_loader = None

        manager = LocalPromptManager(temp_db)
        manager.save_prompt(
            path="test/configured", content="configured content", tier="bundled"
        )

        configure_default_loader(temp_db)

        loader = get_default_loader()
        assert loader._db is not None
        template = loader.load("test/configured")
        assert template.content == "configured content"

        # Clean up module state
        loader_mod._default_loader = None
