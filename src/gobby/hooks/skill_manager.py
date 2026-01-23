"""HookSkillManager - Skill management for the hook system.

This module provides skill discovery and management for the hook system,
allowing hooks to access and use skills (Agent Skills specification).
"""

from __future__ import annotations

import logging
from pathlib import Path

from gobby.skills.loader import SkillLoader
from gobby.skills.parser import ParsedSkill

logger = logging.getLogger(__name__)


class HookSkillManager:
    """Manage skills for the hook system.

    Provides discovery and access to core skills bundled with Gobby,
    as well as project-specific skills.

    Example usage:
        ```python
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        skills = manager.discover_core_skills()

        # Get a specific skill
        tasks_skill = manager.get_skill_by_name("gobby-tasks")
        ```
    """

    def __init__(self) -> None:
        """Initialize the skill manager."""
        # Path to built-in skills: src/gobby/hooks/ -> src/gobby/install/shared/skills/
        self._base_dir = Path(__file__).parent.parent
        self._core_skills_path = self._base_dir / "install" / "shared" / "skills"

        # Loader for parsing skills (use "filesystem" for bundled core skills)
        self._loader = SkillLoader(default_source_type="filesystem")

        # Cache of discovered skills
        self._core_skills: list[ParsedSkill] | None = None

    def discover_core_skills(self) -> list[ParsedSkill]:
        """Discover built-in skills from install/shared/skills/.

        Returns:
            List of ParsedSkill objects for all valid core skills.
            Invalid skills are logged as warnings and skipped.
        """
        if self._core_skills is not None:
            return self._core_skills

        if not self._core_skills_path.exists():
            logger.warning(f"Core skills path not found: {self._core_skills_path}")
            self._core_skills = []
            return self._core_skills

        # Load all skills from the core directory
        self._core_skills = self._loader.load_directory(
            self._core_skills_path,
            validate=True,
        )

        logger.debug(f"Discovered {len(self._core_skills)} core skills")
        return self._core_skills

    def get_skill_by_name(self, name: str) -> ParsedSkill | None:
        """Get a skill by name.

        Args:
            name: The skill name to look up.

        Returns:
            ParsedSkill if found, None otherwise.
        """
        # Ensure skills are discovered
        skills = self.discover_core_skills()

        for skill in skills:
            if skill.name == name:
                return skill

        return None

    def refresh(self) -> None:
        """Clear the cache and rediscover skills."""
        self._core_skills = None

    def recommend_skills(self, category: str | None = None) -> list[str]:
        """Recommend relevant skills based on task category.

        Maps task categories to relevant core skills that would be helpful
        for that type of work.

        Args:
            category: Task category (e.g., 'code', 'docs', 'test', 'config')

        Returns:
            List of skill names that are relevant for the category
        """
        # Category to skill mappings
        category_skills: dict[str, list[str]] = {
            "code": ["gobby-tasks", "gobby-expand", "gobby-worktrees"],
            "test": ["gobby-tasks", "gobby-expand"],
            "docs": ["gobby-tasks", "gobby-plan"],
            "config": ["gobby-tasks", "gobby-mcp"],
            "refactor": ["gobby-tasks", "gobby-expand", "gobby-worktrees"],
            "planning": ["gobby-tasks", "gobby-plan", "gobby-expand"],
            "research": ["gobby-tasks", "gobby-memory"],
        }

        # Get skills for the category (or empty list if no match)
        recommended = category_skills.get(category or "", [])

        # Always include alwaysApply skills
        skills = self.discover_core_skills()
        always_apply = [s.name for s in skills if s.is_always_apply()]

        # Combine and dedupe while preserving order
        result = list(always_apply)
        for skill_name in recommended:
            if skill_name not in result:
                result.append(skill_name)

        return result
