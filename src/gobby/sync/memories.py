"""Memory backup utilities for filesystem export.

This module provides JSONL backup functionality for memories. It is NOT a
bidirectional sync mechanism - memories are stored in the database via
MemoryBackendProtocol. This module handles:

- Backup export to .gobby/memories.jsonl for disaster recovery
- One-time migration import from existing JSONL files
- Debounced auto-backup on memory changes

Classes:
    MemoryBackupManager: Main backup manager (formerly MemorySyncManager)
    MemorySyncManager: Backward-compatible alias for MemoryBackupManager
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

__all__ = [
    "MemoryBackupManager",
    "MemorySyncManager",  # Backward compatibility alias
]

# TODO: Rename MemorySyncConfig to MemoryBackupConfig in gobby.config.persistence
# for consistency with MemoryBackupManager naming. Keeping current name for now
# to minimize breaking changes across the codebase.
from gobby.config.persistence import MemorySyncConfig
from gobby.memory.manager import MemoryManager
from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


class MemoryBackupManager:
    """
    Manages backup of memories from the database to filesystem.

    This is a backup/export utility, NOT a sync mechanism. Memories are stored
    in the database (via the configured backend) and this class provides:
    - JSONL backup export (to .gobby/memories.jsonl)
    - One-time migration import from existing JSONL files
    - Debounced auto-backup on changes

    For actual memory storage, see gobby.memory.backends.
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
            pass  # nosec B110 - fall back to cwd if project context unavailable

        # Fall back to current working directory
        return Path.cwd() / self.export_path

    async def import_from_files(self) -> int:
        """
        Import memories from filesystem (one-time migration).

        This is intended for migrating existing JSONL backup files into the
        database. For ongoing memory storage, use the memory backend directly.

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

    def backup_sync(self) -> int:
        """
        Backup memories to filesystem synchronously (blocking).

        Used to force a backup write before the async loop starts.
        This is a one-way export for backup purposes only.
        """
        if not self.config.enabled:
            return 0

        if not self.memory_manager:
            return 0

        try:
            memories_file = self._get_export_path()
            return self._export_to_files_sync(memories_file)
        except Exception as e:
            logger.warning(f"Failed to backup memories: {e}")
            return 0

    # Backward compatibility alias
    export_sync = backup_sync

    async def export_to_files(self) -> int:
        """
        Backup memories to filesystem as JSONL.

        This exports all memories to a JSONL file for backup purposes.
        The file can be used for disaster recovery or migration.

        Returns:
            Count of backed up memories
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

    def _sanitize_content(self, content: str) -> str:
        """Replace user home directories with ~ for privacy.

        Prevents absolute user paths like /Users/josh from being
        committed to version control.
        """
        home = os.path.expanduser("~")
        return content.replace(home, "~")

    def _deduplicate_memories(self, memories: list[Any]) -> list[Any]:
        """Deduplicate memories by normalized content, keeping earliest.

        Args:
            memories: List of memory objects

        Returns:
            List of unique memories (by content), keeping the earliest created_at
        """
        seen_content: dict[str, Any] = {}  # normalized_content -> memory
        for memory in memories:
            normalized = memory.content.strip()
            if normalized not in seen_content:
                seen_content[normalized] = memory
            else:
                # Keep the one with earlier created_at
                existing = seen_content[normalized]
                if memory.created_at < existing.created_at:
                    seen_content[normalized] = memory
        return list(seen_content.values())

    def _export_memories_sync(self, file_path: Path) -> int:
        """Export memories to JSONL file (sync) with deduplication and path sanitization."""
        if not self.memory_manager:
            return 0

        try:
            memories = self.memory_manager.list_memories()

            # Deduplicate by content before export
            unique_memories = self._deduplicate_memories(memories)

            with open(file_path, "w", encoding="utf-8") as f:
                for memory in unique_memories:
                    data = {
                        "id": memory.id,
                        "content": self._sanitize_content(memory.content),
                        "type": memory.memory_type,
                        "importance": memory.importance,
                        "tags": memory.tags,
                        "created_at": memory.created_at,
                        "updated_at": memory.updated_at,
                        "source": memory.source_type,
                        "source_id": memory.source_session_id,
                    }
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")

            return len(unique_memories)
        except Exception as e:
            logger.error(f"Failed to export memories: {e}")
            return 0


# Backward compatibility alias
MemorySyncManager = MemoryBackupManager
