import asyncio
import json
import logging
import time
from pathlib import Path

from gobby.config.app import MemorySyncConfig
from gobby.memory.manager import MemoryManager
from gobby.storage.database import LocalDatabase

logger = logging.getLogger(__name__)


class MemorySyncManager:
    """
    Manages synchronization of memories between the database and filesystem.

    Supports:
    - JSONL export/import for memories
    - Debounced auto-export on changes
    - Stealth mode (storage in ~/.gobby vs .gobby/)
    """

    def __init__(
        self,
        db: LocalDatabase,
        memory_manager: MemoryManager | None,
        config: MemorySyncConfig,
    ):
        self.db = db
        self.memory_manager = memory_manager
        self.config = config

        # Debounce state
        self._export_task: asyncio.Task | None = None
        self._last_change_time: float = 0
        self._shutdown_requested = False

    def trigger_export(self) -> None:
        """Trigger a debounced export."""
        if not self.config.enabled:
            return

        self._last_change_time = time.time()

        if self._export_task is None or self._export_task.done():
            self._export_task = asyncio.create_task(self._process_export_queue())

    async def shutdown(self) -> None:
        """Gracefully shutdown the export task."""
        self._shutdown_requested = True
        if self._export_task:
            if not self._export_task.done():
                try:
                    await self._export_task
                except asyncio.CancelledError:
                    pass
            self._export_task = None

    async def _process_export_queue(self) -> None:
        """Process export task with debounce."""
        if not self.config.enabled:
            return

        while not self._shutdown_requested:
            # Check if debounce time has passed
            now = time.time()
            elapsed = now - self._last_change_time

            if elapsed >= self.config.export_debounce:
                try:
                    await self.export_to_files()
                    return
                except Exception as e:
                    logger.error(f"Error during memory sync export: {e}")
                    return

            # Wait for remaining debounce time
            wait_time = max(0.1, self.config.export_debounce - elapsed)
            await asyncio.sleep(wait_time)

    def _get_sync_dir(self) -> Path:
        """Get the directory for syncing.

        Returns an absolute path to the sync directory.
        - In stealth mode: ~/.gobby/sync
        - Otherwise: Uses project context if available, falls back to ~/.gobby/sync
        """
        if self.config.stealth:
            return Path("~/.gobby/sync").expanduser().resolve()

        # Try to get project path from project context
        try:
            from gobby.utils.project_context import get_project_context

            project_ctx = get_project_context()
            if project_ctx and project_ctx.get("path"):
                project_path = Path(project_ctx["path"]).expanduser().resolve()
                return project_path / ".gobby" / "sync"
        except Exception:
            pass

        # Fall back to user home directory for stability
        return Path("~/.gobby/sync").expanduser().resolve()

    async def import_from_files(self) -> int:
        """
        Import memories from filesystem.

        Returns:
            Count of imported memories
        """
        if not self.config.enabled:
            return 0

        if not self.memory_manager:
            return 0

        sync_dir = self._get_sync_dir()
        memories_file = sync_dir / "memories.jsonl"
        if not memories_file.exists():
            return 0

        return await asyncio.to_thread(self._import_memories_sync, memories_file)

    async def export_to_files(self) -> int:
        """
        Export memories to filesystem.

        Returns:
            Count of exported memories
        """
        if not self.config.enabled:
            return 0

        if not self.memory_manager:
            return 0

        sync_dir = self._get_sync_dir()
        return await asyncio.to_thread(self._export_to_files_sync, sync_dir)

    def _export_to_files_sync(self, sync_dir: Path) -> int:
        """Synchronous implementation of export."""
        sync_dir.mkdir(parents=True, exist_ok=True)
        memories_file = sync_dir / "memories.jsonl"
        return self._export_memories_sync(memories_file)

    def _import_memories_sync(self, file_path: Path) -> int:
        """Import memories from JSONL file (sync)."""
        if not self.memory_manager:
            return 0

        count = 0
        skipped = 0
        try:
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        content = data.get("content", "")

                        # Skip if memory with identical content already exists
                        if self.memory_manager.content_exists(content):
                            skipped += 1
                            continue

                        # Use storage directly for sync import (skip auto-embedding)
                        self.memory_manager.storage.create_memory(
                            content=content,
                            memory_type=data.get("type", "fact"),
                            tags=data.get("tags", []),
                            importance=data.get("importance", 0.5),
                            source_type=data.get("source", "import"),
                            source_session_id=data.get("source_id"),
                        )
                        count += 1
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in memories file: {line[:50]}...")
                    except Exception as e:
                        logger.debug(f"Skipping memory import: {e}")

        except Exception as e:
            logger.error(f"Failed to import memories: {e}")

        if skipped > 0:
            logger.debug(f"Skipped {skipped} duplicate memories during import")

        return count

    def _export_memories_sync(self, file_path: Path) -> int:
        """Export memories to JSONL file (sync)."""
        if not self.memory_manager:
            return 0

        try:
            memories = self.memory_manager.list_memories()

            with open(file_path, "w", encoding="utf-8") as f:
                for memory in memories:
                    data = {
                        "id": memory.id,
                        "content": memory.content,
                        "type": memory.memory_type,
                        "importance": memory.importance,
                        "tags": memory.tags,
                        "created_at": memory.created_at,
                        "updated_at": memory.updated_at,
                        "source": memory.source_type,
                        "source_id": memory.source_session_id,
                    }
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")

            return len(memories)
        except Exception as e:
            logger.error(f"Failed to export memories: {e}")
            return 0
