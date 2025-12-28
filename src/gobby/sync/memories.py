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

        # Import Skills from .claude/skills/ (Claude Code native format)
        if self.skill_manager:
            skills_dir = Path(".claude/skills").absolute()
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

        # Export Memories (JSONL) to sync_dir
        if self.memory_manager:
            memories_file = sync_dir / "memories.jsonl"
            count = self._export_memories_sync(memories_file)
            result["memories"] = count

        # Export Skills to .claude/skills/ (Claude Code native format)
        # Skills always go to .claude/skills/ for Claude Code discovery
        if self.skill_manager:
            skills_dir = Path(".claude/skills").absolute()
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
        """Import skills from Markdown files (sync).

        Supports both formats:
        - Claude Code format: skills/<name>/SKILL.md (directory per skill)
        - Legacy format: skills/<name>.md (flat files)
        """
        if not self.skill_manager:
            return 0

        count = 0
        try:
            # First, try Claude Code format (directory per skill with SKILL.md)
            for skill_subdir in skills_dir.iterdir():
                if not skill_subdir.is_dir():
                    continue
                if skill_subdir.name.startswith("."):
                    continue

                skill_file = skill_subdir / "SKILL.md"
                if skill_file.exists():
                    # Load Gobby metadata if available
                    meta = {}
                    meta_file = skill_subdir / ".gobby-meta.json"
                    if meta_file.exists():
                        try:
                            with open(meta_file) as f:
                                meta = json.load(f)
                        except Exception:
                            pass

                    if self._import_skill_file(skill_file, meta):
                        count += 1

            # Then, try legacy flat file format (*.md files directly in skills/)
            for md_file in skills_dir.glob("*.md"):
                if md_file.name.startswith("."):
                    continue

                if self._import_skill_file(md_file, {}):
                    count += 1

        except Exception as e:
            logger.error(f"Failed to import skills: {e}")

        return count

    def _import_skill_file(self, skill_file: Path, meta: dict) -> bool:
        """Import a single skill file. Returns True if imported."""
        if not self.skill_manager:
            return False

        try:
            content = skill_file.read_text()
        except Exception as e:
            logger.warning(f"Failed to read skill file {skill_file}: {e}")
            return False

        # Parse frontmatter
        if not content.startswith("---"):
            return False

        try:
            parts = content.split("---", 2)
            if len(parts) < 3:
                return False

            frontmatter = yaml.safe_load(parts[1])
            body = parts[2].strip()

            name = frontmatter.get("name")
            if not name:
                return False

            # Get tags from meta or frontmatter
            tags = meta.get("tags") or frontmatter.get("tags")
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]
            elif not isinstance(tags, list):
                tags = []

            # Get trigger_pattern from meta or frontmatter
            trigger_pattern = meta.get("trigger_pattern") or frontmatter.get("trigger_pattern")

            # Extract description (strip trigger phrase prefix if present)
            description = frontmatter.get("description", "")
            if description.startswith("This skill should be used when"):
                # Try to extract the base description after the trigger phrases
                if ". " in description:
                    description = description.split(". ", 1)[-1]

            existing = self._get_skill_by_name(name)

            if existing:
                self.skill_manager.update_skill(
                    skill_id=existing.id,
                    instructions=body,
                    description=description,
                    tags=tags,
                    trigger_pattern=trigger_pattern,
                )
            else:
                self.skill_manager.create_skill(
                    name=name,
                    instructions=body,
                    description=description,
                    tags=tags,
                    trigger_pattern=trigger_pattern,
                )
            return True

        except Exception as e:
            logger.warning(f"Failed to parse skill file {skill_file}: {e}")
            return False

    def _export_skills_sync(self, skills_dir: Path) -> int:
        """Export skills to Claude Code native format (sync).

        Creates skills in the format expected by Claude Code:
        - .claude/skills/<skill-name>/SKILL.md (one directory per skill)

        The SKILL.md format uses Claude Code's frontmatter convention:
        - name: Skill name
        - description: Third-person trigger description

        Claude Code automatically discovers skills in .claude/skills/.
        """
        if not self.skill_manager:
            return 0

        try:
            skills_dir.mkdir(parents=True, exist_ok=True)
            skills = self.skill_manager.list_skills()

            for skill in skills:
                # Create directory per skill (Claude Code format)
                safe_name = "".join(c for c in skill.name if c.isalnum() or c in "-_").lower()
                if not safe_name:
                    safe_name = skill.id
                skill_dir = skills_dir / safe_name
                skill_dir.mkdir(parents=True, exist_ok=True)

                # Build Claude Code compatible description with trigger phrases
                description = self._build_trigger_description(skill)

                # Claude Code frontmatter format (name + description only)
                frontmatter = {
                    "name": skill.name,
                    "description": description,
                }

                content = "---\n"
                content += yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
                content += "---\n\n"
                content += skill.instructions

                # Write to SKILL.md (Claude Code convention)
                skill_file = skill_dir / "SKILL.md"
                with open(skill_file, "w") as f:
                    f.write(content)

                # Also write metadata for Gobby's internal use
                meta_file = skill_dir / ".gobby-meta.json"
                meta = {
                    "id": skill.id,
                    "trigger_pattern": skill.trigger_pattern or "",
                    "tags": skill.tags or [],
                    "usage_count": skill.usage_count,
                }
                with open(meta_file, "w") as f:
                    json.dump(meta, f, indent=2)

            return len(skills)
        except Exception as e:
            logger.error(f"Failed to export skills: {e}")
            return 0

    def _build_trigger_description(self, skill: Skill) -> str:
        """Build Claude Code compatible trigger description.

        Converts trigger_pattern regex to natural language trigger phrases.
        Format: 'This skill should be used when the user asks to "phrase1", "phrase2"...'
        """
        base_desc = skill.description or f"Provides guidance for {skill.name}"

        # Extract trigger phrases from pattern
        trigger_phrases = []
        if skill.trigger_pattern:
            # Split by | and clean up regex patterns
            parts = skill.trigger_pattern.split("|")
            for part in parts:
                # Remove common regex chars and convert to readable phrase
                phrase = part.strip()
                phrase = phrase.replace(".*", " ")
                phrase = phrase.replace("\\s+", " ")
                phrase = phrase.replace("\\b", "")
                phrase = phrase.replace("^", "").replace("$", "")
                phrase = phrase.strip()
                if phrase and len(phrase) > 1:
                    trigger_phrases.append(f'"{phrase}"')

        if trigger_phrases:
            triggers = ", ".join(trigger_phrases[:5])  # Limit to 5 phrases
            return f'This skill should be used when the user asks to {triggers}. {base_desc}'
        else:
            return f'This skill should be used when working with {skill.name}. {base_desc}'
