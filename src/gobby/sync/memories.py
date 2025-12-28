import asyncio
import json
import logging
import time
from pathlib import Path

import yaml

from gobby.config.app import MemorySyncConfig
from gobby.memory.manager import MemoryManager
from gobby.storage.database import LocalDatabase
from gobby.storage.skills import LocalSkillManager, Skill

logger = logging.getLogger(__name__)


class MemorySyncManager:
    """
    Manages synchronization of memories and skills between the database and filesystem.

    Supports:
    - JSONL export/import for memories
    - Markdown export/import for skills
    - Debounced auto-export on changes
    - Stealth mode (storage in ~/.gobby vs .gobby/)
    """

    def __init__(
        self,
        db: LocalDatabase,
        memory_manager: MemoryManager | None,
        skill_manager: LocalSkillManager | None,
        config: MemorySyncConfig,
    ):
        self.db = db
        self.memory_manager = memory_manager
        self.skill_manager = skill_manager
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

    async def import_from_files(self) -> dict[str, int]:
        """
        Import memories and skills from filesystem.

        Returns:
            Dict with counts of imported items
        """
        if not self.config.enabled:
            return {"memories": 0, "skills": 0}

        sync_dir = self._get_sync_dir()
        if not sync_dir.exists():
            return {"memories": 0, "skills": 0}

        result = {"memories": 0, "skills": 0}

        # Import Memories (JSONL)
        # Run in thread executor to avoid blocking loop with file IO/sync DB ops
        if self.memory_manager:
            memories_file = sync_dir / "memories.jsonl"
            if memories_file.exists():
                count = await asyncio.to_thread(self._import_memories_sync, memories_file)
                result["memories"] = count

        # Import Skills (Markdown)
        if self.skill_manager:
            skills_dir = sync_dir / "skills"
            if skills_dir.exists():
                count = await asyncio.to_thread(self._import_skills_sync, skills_dir)
                result["skills"] = count

        return result

    async def export_to_files(self) -> dict[str, int]:
        """
        Export memories and skills to filesystem.

        Returns:
            Dict with counts of exported items
        """
        if not self.config.enabled:
            return {"memories": 0, "skills": 0}

        sync_dir = self._get_sync_dir()

        # IO operations in thread
        return await asyncio.to_thread(self._export_to_files_sync, sync_dir)

    def _export_to_files_sync(self, sync_dir: Path) -> dict[str, int]:
        """Synchronous implementation of export."""
        sync_dir.mkdir(parents=True, exist_ok=True)
        result = {"memories": 0, "skills": 0}

        # Export Memories (JSONL)
        if self.memory_manager:
            memories_file = sync_dir / "memories.jsonl"
            count = self._export_memories_sync(memories_file)
            result["memories"] = count

        # Export Skills (Markdown)
        if self.skill_manager:
            skills_dir = sync_dir / "skills"
            count = self._export_skills_sync(skills_dir)
            result["skills"] = count

        logger.info(f"Memory sync export complete: {result}")
        return result

    def _get_sync_dir(self) -> Path:
        """Get synchronization directory based on config."""
        if self.config.stealth:
            return Path("~/.gobby/sync").expanduser()
        else:
            return Path(".gobby").absolute()

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

                        self.memory_manager.remember(
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

            with open(file_path, "w") as f:
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
                    f.write(json.dumps(data) + "\n")

            return len(memories)
        except Exception as e:
            logger.error(f"Failed to export memories: {e}")
            return 0

    def _get_skill_by_name(self, name: str) -> Skill | None:
        """Helper to find skill by name."""
        if not self.skill_manager:
            return None
        # list_skills returns exact or partial matches depending on implementation
        # LocalSkillManager.list_skills uses 'LIKE %name%'
        candidates = self.skill_manager.list_skills(name_like=name)
        for skill in candidates:
            if skill.name == name:
                return skill
        return None

    def _import_skills_sync(self, skills_dir: Path) -> int:
        """Import skills from Markdown files (sync)."""
        if not self.skill_manager:
            return 0

        count = 0
        try:
            for md_file in skills_dir.glob("*.md"):
                if md_file.name.startswith("."):
                    continue

                try:
                    content = md_file.read_text()
                except Exception as e:
                    logger.warning(f"Failed to read skill file {md_file}: {e}")
                    continue

                # Parse frontmatter
                if content.startswith("---"):
                    try:
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            frontmatter = yaml.safe_load(parts[1])
                            body = parts[2].strip()

                            name = frontmatter.get("name")
                            if not name:
                                continue

                            # Process tags to ensure it's a list
                            tags = frontmatter.get("tags")
                            if isinstance(tags, str):
                                # Handle comma-separated string if user wrote it that way
                                tags = [t.strip() for t in tags.split(",")]
                            elif not isinstance(tags, list):
                                tags = []

                            existing = self._get_skill_by_name(name)

                            if existing:
                                self.skill_manager.update_skill(
                                    skill_id=existing.id,
                                    instructions=body,
                                    description=frontmatter.get("description", ""),
                                    tags=tags,
                                    trigger_pattern=frontmatter.get("trigger_pattern"),
                                )
                            else:
                                self.skill_manager.create_skill(
                                    name=name,
                                    instructions=body,
                                    description=frontmatter.get("description", ""),
                                    tags=tags,
                                    trigger_pattern=frontmatter.get("trigger_pattern"),
                                )
                            count += 1
                    except Exception as e:
                        logger.warning(f"Failed to parse skill file {md_file}: {e}")

        except Exception as e:
            logger.error(f"Failed to import skills: {e}")

        return count

    def _export_skills_sync(self, skills_dir: Path) -> int:
        """Export skills to Markdown files (sync)."""
        if not self.skill_manager:
            return 0

        try:
            skills_dir.mkdir(parents=True, exist_ok=True)
            skills = self.skill_manager.list_skills()

            for skill in skills:
                safe_name = "".join(c for c in skill.name if c.isalnum() or c in "-_").lower()
                filename = skills_dir / f"{safe_name}.md"

                frontmatter = {
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description or "",
                    "trigger_pattern": skill.trigger_pattern or "",
                    "tags": skill.tags or [],
                }

                content = "---\n"
                content += yaml.dump(frontmatter)
                content += "---\n\n"
                content += skill.instructions

                with open(filename, "w") as f:
                    f.write(content)

            return len(skills)
        except Exception as e:
            logger.error(f"Failed to export skills: {e}")
            return 0
