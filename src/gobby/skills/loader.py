"""SkillLoader - Load skills from filesystem.

This module provides the SkillLoader class for loading skills from:
- Single SKILL.md files
- Directories containing SKILL.md files
- Recursively from a root directory
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from gobby.skills.parser import ParsedSkill, SkillParseError, parse_skill_file
from gobby.skills.validator import SkillValidator
from gobby.storage.skills import SkillSourceType

logger = logging.getLogger(__name__)


class SkillLoadError(Exception):
    """Error loading a skill from the filesystem."""

    def __init__(self, message: str, path: str | Path | None = None):
        self.path = str(path) if path else None
        super().__init__(f"{message}" + (f": {path}" if path else ""))


class SkillLoader:
    """Load skills from the filesystem.

    This class handles loading skills from:
    - Single SKILL.md files
    - Directories containing SKILL.md
    - Recursively from a skills root directory

    Example usage:
        ```python
        from gobby.skills.loader import SkillLoader

        loader = SkillLoader()

        # Load a single skill
        skill = loader.load_skill("path/to/SKILL.md")

        # Load from a skill directory
        skill = loader.load_skill("path/to/skill-name/")

        # Load all skills from a directory
        skills = loader.load_directory("path/to/skills/")
        ```
    """

    def __init__(
        self,
        default_source_type: SkillSourceType = "local",
    ):
        """Initialize the loader.

        Args:
            default_source_type: Default source type for loaded skills
        """
        self._default_source_type = default_source_type
        self._validator = SkillValidator()

    def load_skill(
        self,
        path: str | Path,
        validate: bool = True,
        check_dir_name: bool = True,
    ) -> ParsedSkill:
        """Load a skill from a file or directory.

        Args:
            path: Path to SKILL.md file or directory containing SKILL.md
            validate: Whether to validate the skill
            check_dir_name: Whether to check that directory name matches skill name

        Returns:
            ParsedSkill loaded from the path

        Raises:
            SkillLoadError: If skill cannot be loaded
        """
        path = Path(path)

        if not path.exists():
            raise SkillLoadError("Path not found", path)

        # Determine the actual SKILL.md path
        if path.is_file():
            skill_file = path
            is_directory_load = False
        else:
            skill_file = path / "SKILL.md"
            if not skill_file.exists():
                raise SkillLoadError("SKILL.md not found in directory", path)
            is_directory_load = True

        # Parse the skill file
        try:
            skill = parse_skill_file(skill_file)
        except SkillParseError as e:
            raise SkillLoadError(f"Failed to parse skill: {e}", skill_file) from e

        # Check directory name matches skill name (when loading from directory)
        if is_directory_load and check_dir_name:
            dir_name = path.name
            if skill.name != dir_name:
                raise SkillLoadError(
                    f"Directory name mismatch: directory '{dir_name}' "
                    f"does not match skill name '{skill.name}'",
                    path,
                )

        # Validate the skill
        if validate:
            result = self._validator.validate(skill)
            if not result.valid:
                errors = "; ".join(result.errors)
                raise SkillLoadError(
                    f"Skill validation failed: {errors}",
                    skill_file,
                )

        # Set source tracking
        skill.source_path = str(skill_file)
        skill.source_type = self._default_source_type

        return skill

    def load_directory(
        self,
        path: str | Path,
        validate: bool = True,
    ) -> list[ParsedSkill]:
        """Load all skills from a directory.

        Scans for subdirectories containing SKILL.md files and loads them.
        Non-skill directories and files are ignored.

        Args:
            path: Path to directory containing skill subdirectories
            validate: Whether to validate loaded skills

        Returns:
            List of ParsedSkill objects

        Raises:
            SkillLoadError: If directory not found
        """
        path = Path(path)

        if not path.exists():
            raise SkillLoadError("Directory not found", path)

        if not path.is_dir():
            raise SkillLoadError("Path is not a directory", path)

        skills: list[ParsedSkill] = []

        for item in path.iterdir():
            if not item.is_dir():
                continue

            skill_file = item / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                skill = self.load_skill(item, validate=validate)
                skills.append(skill)
            except SkillLoadError as e:
                logger.warning(f"Skipping invalid skill: {e}")
                continue

        return skills

    def scan_skills(
        self,
        path: str | Path,
    ) -> list[Path]:
        """Scan a directory for skill directories.

        Finds all subdirectories containing SKILL.md without loading them.

        Args:
            path: Path to scan

        Returns:
            List of paths to skill directories
        """
        path = Path(path)

        if not path.exists() or not path.is_dir():
            return []

        skill_dirs: list[Path] = []

        for item in path.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                skill_dirs.append(item)

        return skill_dirs
