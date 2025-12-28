import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.storage.skills import Skill
from gobby.sync.skills import SkillSyncConfig, SkillSyncManager


@pytest.fixture
def mock_skill_manager():
    sm = MagicMock()
    sm.list_skills = MagicMock(
        return_value=[
            Skill(
                id="s1",
                name="test_skill",
                instructions="do test",
                created_at="2023-01-01T00:00:00Z",
                updated_at="2023-01-01T00:00:00Z",
                project_id=None,
                description="test skill",
                trigger_pattern="test",
                source_session_id=None,
                usage_count=0,
                success_rate=None,
                tags=["tag1"],
            )
        ]
    )
    sm.create_skill = MagicMock()
    sm.update_skill = MagicMock()
    return sm


@pytest.fixture
def sync_config():
    return SkillSyncConfig(enabled=True, stealth=True, export_debounce=0.1)


@pytest.fixture
def sync_manager(mock_skill_manager, sync_config):
    return SkillSyncManager(mock_skill_manager, sync_config)


@pytest.mark.asyncio
async def test_get_sync_dir_stealth(sync_manager):
    sync_manager.config.stealth = True
    path = sync_manager._get_sync_dir()
    assert path == Path("~/.gobby/sync/skills").expanduser()


@pytest.mark.asyncio
async def test_export_to_files(sync_manager, tmp_path):
    # Override _get_sync_dir to use tmp_path
    sync_manager._get_sync_dir = MagicMock(return_value=tmp_path)

    count = await sync_manager.export_to_files()

    # Check skills (Flat file format: <name>.md)
    skill_file = tmp_path / "test_skill.md"
    assert skill_file.exists()
    content = skill_file.read_text()
    assert "name: test_skill" in content
    assert "description: test skill" in content
    assert "trigger_pattern: test" in content
    assert "do test" in content
    assert count == 1


@pytest.mark.asyncio
async def test_import_from_files_legacy(sync_manager, tmp_path):
    """Test importing from legacy flat file format."""
    sync_manager._get_sync_dir = MagicMock(return_value=tmp_path)

    # Create dummy skill file
    skill_file = tmp_path / "imported_skill.md"
    skill_file.write_text("""---
name: imported_skill
description: imported
trigger_pattern: import
tags: [t2]
---
imported instructions
""")

    count = await sync_manager.import_from_files()

    # Verify create_skill called
    sync_manager.skill_manager.create_skill.assert_called()
    s_args = sync_manager.skill_manager.create_skill.call_args[1]
    assert s_args["name"] == "imported_skill"
    assert s_args["instructions"] == "imported instructions"
    assert count == 1


@pytest.mark.asyncio
async def test_import_from_files_claude_format(sync_manager, tmp_path):
    """Test importing from Claude Code plugin format."""
    sync_manager._get_sync_dir = MagicMock(return_value=tmp_path)

    # Create Claude Code format skill
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)

    # SKILL.md with Claude Code format
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("""---
name: my-skill
description: This skill should be used when the user asks to "do something". A helpful skill.
---
Step-by-step instructions here
""")

    # Gobby metadata
    meta_file = skill_dir / ".gobby-meta.json"
    meta_file.write_text(
        json.dumps(
            {
                "id": "sk-abc123",
                "trigger_pattern": "do something|help",
                "tags": ["helper", "test"],
                "usage_count": 5,
            }
        )
    )

    count = await sync_manager.import_from_files()

    # Verify create_skill called with metadata from .gobby-meta.json
    sync_manager.skill_manager.create_skill.assert_called()
    s_args = sync_manager.skill_manager.create_skill.call_args[1]
    assert s_args["name"] == "my-skill"
    assert s_args["instructions"] == "Step-by-step instructions here"
    assert s_args["trigger_pattern"] == "do something|help"
    assert s_args["tags"] == ["helper", "test"]
    # Description should be extracted (without trigger prefix)
    assert "A helpful skill" in s_args["description"]
    assert count == 1


@pytest.mark.asyncio
async def test_trigger_export_debounce(sync_manager):
    sync_manager.export_to_files = AsyncMock(return_value=1)

    sync_manager.trigger_export()
    sync_manager.trigger_export()
    sync_manager.trigger_export()

    # Should be one task running.
    # Wait for debounce
    await asyncio.sleep(0.2)

    assert sync_manager.export_to_files.call_count == 1
