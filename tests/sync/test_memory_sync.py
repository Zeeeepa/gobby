import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.config.app import MemorySyncConfig
from gobby.storage.memories import Memory
from gobby.storage.skills import Skill
from gobby.sync.memories import MemorySyncManager


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_memory_manager():
    mm = MagicMock()
    mm.list_memories = MagicMock(
        return_value=[
            Memory(
                id="m1",
                content="test memory",
                memory_type="fact",
                importance=0.5,
                created_at="2023-01-01T00:00:00Z",
                updated_at="2023-01-01T00:00:00Z",
                access_count=0,
                last_accessed_at=None,
                tags=[],
                project_id="p1",
                source_type="user",
                source_session_id=None,
            )
        ]
    )
    mm.remember = MagicMock()
    mm.content_exists = MagicMock(return_value=False)  # For dedup checks during import
    return mm


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
    sm.learn_skill = MagicMock()
    return sm


@pytest.fixture
def sync_config():
    return MemorySyncConfig(enabled=True, stealth=True, export_debounce=0.1)


@pytest.fixture
def sync_manager(mock_db, mock_memory_manager, mock_skill_manager, sync_config):
    return MemorySyncManager(mock_db, mock_memory_manager, mock_skill_manager, sync_config)


@pytest.mark.asyncio
async def test_get_sync_dir_stealth(sync_manager):
    sync_manager.config.stealth = True
    path = sync_manager._get_sync_dir()
    assert path == Path("~/.gobby/sync").expanduser()


@pytest.mark.asyncio
async def test_get_sync_dir_project(sync_manager):
    sync_manager.config.stealth = False
    with patch("pathlib.Path.cwd", return_value=Path("/tmp/project")):
        path = sync_manager._get_sync_dir()
        assert path == Path("/tmp/project") / ".gobby" / "sync"


@pytest.mark.asyncio
async def test_export_to_files(sync_manager, tmp_path):
    # Override _get_sync_dir and _get_skills_dir to use tmp_path
    sync_manager._get_sync_dir = MagicMock(return_value=tmp_path)
    sync_manager._get_skills_dir = MagicMock(return_value=tmp_path / "skills")

    await sync_manager.export_to_files()

    # Check memories.jsonl
    mem_file = tmp_path / "memories.jsonl"
    assert mem_file.exists()
    lines = mem_file.read_text().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["content"] == "test memory"

    # Check skills (Flat file format: skills/<name>.md)
    skill_file = tmp_path / "skills" / "test_skill.md"
    assert skill_file.exists()
    content = skill_file.read_text()
    assert "name: test_skill" in content
    assert "description: test skill" in content
    assert "trigger_pattern: test" in content
    assert "do test" in content


@pytest.mark.asyncio
async def test_import_from_files_legacy(sync_manager, tmp_path):
    """Test importing from legacy flat file format."""
    sync_manager._get_sync_dir = MagicMock(return_value=tmp_path)
    sync_manager._get_skills_dir = MagicMock(return_value=tmp_path / "skills")

    # Create dummy files
    mem_file = tmp_path / "memories.jsonl"
    mem_file.write_text(
        json.dumps({"content": "imported memory", "type": "fact", "importance": 0.8}) + "\n"
    )

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(exist_ok=True)
    skill_file = skills_dir / "imported_skill.md"
    skill_file.write_text("""---
name: imported_skill
description: imported
trigger_pattern: import
tags: [t2]
---
imported instructions
""")

    await sync_manager.import_from_files()

    # Verify remember called
    sync_manager.memory_manager.remember.assert_called()
    call_args = sync_manager.memory_manager.remember.call_args[1]
    assert call_args["content"] == "imported memory"
    assert call_args["memory_type"] == "fact"
    assert call_args["importance"] == 0.8

    # Verify create_skill called
    sync_manager.skill_manager.create_skill.assert_called()
    s_args = sync_manager.skill_manager.create_skill.call_args[1]
    assert s_args["name"] == "imported_skill"
    assert s_args["instructions"] == "imported instructions"


@pytest.mark.asyncio
async def test_import_from_files_claude_format(sync_manager, tmp_path):
    """Test importing from Claude Code plugin format."""
    sync_manager._get_sync_dir = MagicMock(return_value=tmp_path)
    sync_manager._get_skills_dir = MagicMock(return_value=tmp_path / "skills")

    # Create Claude Code format skill
    skill_dir = tmp_path / "skills" / "my-skill"
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

    await sync_manager.import_from_files()

    # Verify create_skill called with metadata from .gobby-meta.json
    sync_manager.skill_manager.create_skill.assert_called()
    s_args = sync_manager.skill_manager.create_skill.call_args[1]
    assert s_args["name"] == "my-skill"
    assert s_args["instructions"] == "Step-by-step instructions here"
    assert s_args["trigger_pattern"] == "do something|help"
    assert s_args["tags"] == ["helper", "test"]
    # Description should be extracted (without trigger prefix)
    assert "A helpful skill" in s_args["description"]


@pytest.mark.asyncio
async def test_trigger_export_debounce(sync_manager):
    sync_manager.export_to_files = AsyncMock()

    sync_manager.trigger_export()
    sync_manager.trigger_export()
    sync_manager.trigger_export()

    # Should be one task running.
    # Wait for debounce
    await asyncio.sleep(0.2)

    assert sync_manager.export_to_files.call_count == 1
