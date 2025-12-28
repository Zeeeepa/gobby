"""
Skill synchronization manager for exporting/importing skills to filesystem.

This module handles:
- Markdown export/import for skills
- Debounced auto-export on changes
- Support for Claude Code SKILL.md format
"""

import asyncio
import json
import logging
import time
from pathlib import Path

import yaml

from gobby.storage.skills import LocalSkillManager, Skill

logger = logging.getLogger(__name__)


class SkillSyncConfig:
    """Configuration for skill synchronization."""

    def __init__(
        self,
        enabled: bool = True,
        export_debounce: float = 2.0,
        stealth: bool = False,
    ):
        self.enabled = enabled
        self.export_debounce = export_debounce
        self.stealth = stealth


class SkillSyncManager:
    """
    Manages synchronization of skills between the database and filesystem.

    Supports:
    - Markdown export/import for skills
    - Debounced auto-export on changes
    - Stealth mode (storage in ~/.gobby vs .gobby/)
    - Claude Code SKILL.md format (directory per skill)
    - Legacy flat file format (skill-name.md)
    """

    def __init__(
        self,
        skill_manager: LocalSkillManager,
        config: SkillSyncConfig | None = None,
    ):
        self.skill_manager = skill_manager
        self.config = config or SkillSyncConfig()

        # Debounce state
        self._export_task: asyncio.Task | None = None
        self._last_change_time: float = 0
        self._shutdown_requested = False
        self._task_lock = asyncio.Lock()

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
            now = time.time()
            elapsed = now - self._last_change_time

            if elapsed >= self.config.export_debounce:
                try:
                    await self.export_to_files()
                    return
                except Exception as e:
                    logger.error(f"Error during skill sync export: {e}")
                    return

            wait_time = max(0.1, self.config.export_debounce - elapsed)
            await asyncio.sleep(wait_time)

    def _get_sync_dir(self) -> Path:
        """Get the directory for syncing.

        Returns an absolute path to the sync directory.
        - In stealth mode: ~/.gobby/sync/skills
        - Otherwise: Uses project context if available, falls back to ~/.gobby/sync/skills
        """
        if self.config.stealth:
            return Path("~/.gobby/sync/skills").expanduser().resolve()

        # Try to get project path from project context
        try:
            from gobby.utils.project_context import get_project_context

            project_ctx = get_project_context()
            if project_ctx and project_ctx.get("path"):
                project_path = Path(project_ctx["path"]).expanduser().resolve()
                return project_path / ".gobby" / "sync" / "skills"
        except Exception:
            pass

        # Fall back to user home directory for stability
        return Path("~/.gobby/sync/skills").expanduser().resolve()

    async def import_from_files(self) -> int:
        """
        Import skills from filesystem.

        Returns:
            Count of imported skills
        """
        if not self.config.enabled:
            return 0

        skills_dir = self._get_sync_dir()
        if not skills_dir.exists():
            return 0

        return await asyncio.to_thread(self._import_skills_sync, skills_dir)

    async def export_to_files(self) -> int:
        """
        Export skills to filesystem.

        Returns:
            Count of exported skills
        """
        if not self.config.enabled:
            return 0

        skills_dir = self._get_sync_dir()
        return await asyncio.to_thread(self._export_skills_sync, skills_dir)

    def _get_skill_by_name(self, name: str) -> Skill | None:
        """Helper to find skill by name."""
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
                match = description.find(". ")
                if match != -1:
                    remaining = description[match + 2 :]
                    if remaining:
                        description = remaining

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
        """Export skills to flat Markdown files (sync)."""
        try:
            skills_dir.mkdir(parents=True, exist_ok=True)
            skills = self.skill_manager.list_skills()

            for skill in skills:
                try:
                    # Sanitize name for filename
                    safe_name = "".join(c for c in skill.name if c.isalnum() or c in "-_").lower()
                    if not safe_name:
                        safe_name = skill.id

                    filename = f"{safe_name}.md"
                    skill_file = skills_dir / filename

                    # Prepare frontmatter
                    frontmatter = {
                        "name": skill.name,
                        "description": skill.description or "",
                        "trigger_pattern": skill.trigger_pattern or "",
                        "tags": skill.tags or [],
                    }

                    content = "---\n"
                    content += yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
                    content += "---\n\n"
                    content += skill.instructions

                    with open(skill_file, "w", encoding="utf-8") as f:
                        f.write(content)

                except Exception as e:
                    logger.error(f"Failed to export skill '{skill.name}': {e}")
                    continue

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
            return f"This skill should be used when the user asks to {triggers}. {base_desc}"
        else:
            return f"This skill should be used when working with {skill.name}. {base_desc}"
