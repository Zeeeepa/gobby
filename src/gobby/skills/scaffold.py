"""Skill scaffolding and initialization.

Functions for creating new skill directories and initializing
project-level skills configuration. Extracted from src/gobby/cli/skills.py
as part of the Strangler Fig decomposition.
"""

import re
from pathlib import Path
from typing import Any

import yaml

SKILL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

DEFAULT_SKILLS_CONFIG: dict[str, Any] = {
    "version": "1.0",
    "skills": {
        "enabled": True,
        "auto_discover": True,
        "search_paths": ["./skills", "./.gobby/skills"],
    },
}


def validate_skill_name(name: str) -> str | None:
    """Validate a skill name against naming conventions.

    Returns None if valid, or an error message string if invalid.
    """
    if not SKILL_NAME_PATTERN.match(name):
        return (
            f"Invalid skill name '{name}'. "
            "Name must be lowercase letters, digits, and hyphens only. "
            "Must start with a letter and cannot have leading/trailing or consecutive hyphens."
        )
    return None


def scaffold_skill(name: str, base_path: Path, description: str | None = None) -> Path:
    """Create a new skill directory structure with a SKILL.md template.

    Args:
        name: Skill name (must pass validate_skill_name).
        base_path: Parent directory where the skill directory will be created.
        description: Optional description; defaults to 'Description for {name}'.

    Returns:
        Path to the created skill directory.

    Raises:
        ValueError: If name is invalid.
        FileExistsError: If the skill directory already exists.
    """
    error = validate_skill_name(name)
    if error:
        raise ValueError(error)

    skill_dir = base_path / name

    if skill_dir.exists():
        raise FileExistsError(f"Directory already exists: {name}")

    if description is None:
        description = f"Description for {name}"

    # Create directory structure
    skill_dir.mkdir(parents=True)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "assets").mkdir()
    (skill_dir / "references").mkdir()

    # Create SKILL.md with template
    skill_template = f"""---
name: {name}
description: {description}
version: "1.0.0"
metadata:
  skillport:
    category: general
    tags: []
    alwaysApply: false
  gobby:
    triggers: []
---

# {name.replace("-", " ").title()}

## Overview

{description}

## Instructions

Add your skill instructions here.

## Examples

Provide usage examples here.
"""

    (skill_dir / "SKILL.md").write_text(skill_template, encoding="utf-8")

    return skill_dir


def init_skills_directory(base_path: Path) -> dict[str, bool]:
    """Initialize the skills directory and config for a project.

    Args:
        base_path: Project root directory (where .gobby/ lives).

    Returns:
        Dict with 'dir_created' and 'config_created' booleans.
    """
    skills_dir = base_path / ".gobby" / "skills"
    config_file = skills_dir / "config.yaml"

    # Create .gobby directory if needed
    gobby_dir = base_path / ".gobby"
    if not gobby_dir.exists():
        gobby_dir.mkdir(parents=True)

    dir_created = False
    if not skills_dir.exists():
        skills_dir.mkdir(parents=True)
        dir_created = True

    config_created = False
    if not config_file.exists():
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(DEFAULT_SKILLS_CONFIG, f, default_flow_style=False)
        config_created = True

    return {"dir_created": dir_created, "config_created": config_created}
