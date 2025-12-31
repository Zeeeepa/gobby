import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.config.app import MemorySyncConfig
from gobby.storage.memories import Memory
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
    # storage.create_memory is used for sync import (skips auto-embedding)
    mm.storage = MagicMock()
    mm.storage.create_memory = MagicMock()
    return mm


@pytest.fixture
def sync_config():
    return MemorySyncConfig(enabled=True, stealth=True, export_debounce=0.1)


@pytest.fixture
def sync_manager(mock_db, mock_memory_manager, sync_config):
    return MemorySyncManager(mock_db, mock_memory_manager, sync_config)


@pytest.mark.asyncio
async def test_get_sync_dir_stealth(sync_manager):
    sync_manager.config.stealth = True
    path = sync_manager._get_sync_dir()
    assert path == Path("~/.gobby/sync").expanduser()


@pytest.mark.asyncio
async def test_get_sync_dir_project(sync_manager):
    sync_manager.config.stealth = False
    mock_context = {"path": "/tmp/project"}
    with patch("gobby.utils.project_context.get_project_context", return_value=mock_context):
        path = sync_manager._get_sync_dir()
        # Compare resolved paths (handles macOS /tmp -> /private/tmp symlink)
        expected = (Path("/tmp/project") / ".gobby" / "sync").resolve()
        assert path == expected


@pytest.mark.asyncio
async def test_export_to_files(sync_manager, tmp_path):
    # Override _get_sync_dir to use tmp_path
    sync_manager._get_sync_dir = MagicMock(return_value=tmp_path)

    count = await sync_manager.export_to_files()

    # Check memories.jsonl
    mem_file = tmp_path / "memories.jsonl"
    assert mem_file.exists()
    lines = mem_file.read_text().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["content"] == "test memory"
    assert count == 1


@pytest.mark.asyncio
async def test_import_from_files(sync_manager, tmp_path):
    """Test importing memories from JSONL file."""
    sync_manager._get_sync_dir = MagicMock(return_value=tmp_path)

    # Create dummy memory file
    mem_file = tmp_path / "memories.jsonl"
    mem_file.write_text(
        json.dumps({"content": "imported memory", "type": "fact", "importance": 0.8}) + "\n"
    )

    count = await sync_manager.import_from_files()

    # Verify storage.create_memory called (sync import bypasses auto-embedding)
    sync_manager.memory_manager.storage.create_memory.assert_called()
    call_args = sync_manager.memory_manager.storage.create_memory.call_args[1]
    assert call_args["content"] == "imported memory"
    assert call_args["memory_type"] == "fact"
    assert call_args["importance"] == 0.8
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
