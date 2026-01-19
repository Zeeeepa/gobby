import asyncio
import json
import logging
import time
from pathlib import Path

from gobby.config.app import MemorySyncConfig
from gobby.memory.manager import MemoryManager
from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


class MemorySyncManager:
    """
    Manages synchronization of memories between the database and filesystem.

    Supports:
    - JSONL export/import for memories (to .gobby/memories.jsonl)
    - Debounced auto-export on changes
    """

    def __init__(
        self,
        db: DatabaseProtocol,
        memory_manager: MemoryManager | None,
        config: MemorySyncConfig,
    ):
        self.db = db
        self.memory_manager = memory_manager
        self.config = config
        self.export_path = config.export_path

        # Debounce state
        self._export_task: asyncio.Task[None] | None = None
        self._last_change_time: float = 0
        self._shutdown_requested = False

    def trigger_export(self) -> None:
        """Trigger a debounced export."""
        if not self.config.enabled:
            return

        self._last_change_time = time.time()

        if self._export_task is None or self._export_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._export_task = loop.create_task(self._process_export_queue())
            except RuntimeError:
                # No running event loop (e.g. CLI usage) - run sync immediately
                # We skip the debounce loop and just export
                memories_file = self._get_export_path()
                try:
                    self._export_to_files_sync(memories_file)
                except Exception as e:
                    logger.warning(f"Failed to sync memory export: {e}")

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

    def _get_export_path(self) -> Path:
        """Get the path for the memories.jsonl file.

        Returns the export_path, resolving relative paths against the project context.
        """
        if self.export_path.is_absolute():
            return self.export_path

        # Try to get project path from project context
        try:
            from gobby.utils.project_context import get_project_context

            project_ctx = get_project_context()
            if project_ctx and project_ctx.get("path"):
                project_path = Path(project_ctx["path"]).expanduser().resolve()
                return project_path / self.export_path
        except Exception:
            pass  # Fall back to cwd if project context unavailable

        # Fall back to current working directory
        return Path.cwd() / self.export_path

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

        memories_file = self._get_export_path()
        if not memories_file.exists():
            return 0

        return await asyncio.to_thread(self._import_memories_sync, memories_file)

    def export_sync(self) -> int:
        """
        Export memories synchronously (blocking).

        Used to force a write before the async loop starts.
        """
        if not self.config.enabled:
            return 0

        if not self.memory_manager:
            return 0

        try:
            memories_file = self._get_export_path()
            return self._export_to_files_sync(memories_file)
        except Exception as e:
            logger.warning(f"Failed to sync memory export: {e}")
            return 0

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

        memories_file = self._get_export_path()
        return await asyncio.to_thread(self._export_to_files_sync, memories_file)

    def _export_to_files_sync(self, memories_file: Path) -> int:
        """Synchronous implementation of export."""
        memories_file.parent.mkdir(parents=True, exist_ok=True)
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
