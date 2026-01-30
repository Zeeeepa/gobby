"""Skill synchronization for bundled skills.

This module provides sync_bundled_skills() which loads skills from the
bundled install/shared/skills/ directory and syncs them to the database.
"""

import logging
from pathlib import Path
from typing import Any

from gobby.skills.loader import SkillLoader
from gobby.storage.database import DatabaseProtocol
from gobby.storage.skills import LocalSkillManager

__all__ = ["sync_bundled_skills", "get_bundled_skills_path"]

logger = logging.getLogger(__name__)


def get_bundled_skills_path() -> Path:
    """Get the path to bundled skills directory.

    Returns:
        Path to src/gobby/install/shared/skills/
    """
    from gobby.paths import get_install_dir

    return get_install_dir() / "shared" / "skills"


def sync_bundled_skills(db: DatabaseProtocol) -> dict[str, Any]:
    """Sync bundled skills from install/shared/skills/ to the database.

    This function:
    1. Loads all skills from the bundled skills directory
    2. For each skill, checks if it already exists in the database
    3. If not, creates it with source_type='filesystem' and project_id=None (global)
    4. If exists, skips it (idempotent)

    Args:
        db: Database connection

    Returns:
        Dict with success status and counts:
        - success: bool
        - synced: int - number of skills added
        - skipped: int - number of skills already present
        - errors: list[str] - any error messages
    """
    skills_path = get_bundled_skills_path()

    result: dict[str, Any] = {
        "success": True,
        "synced": 0,
        "skipped": 0,
        "errors": [],
    }

    if not skills_path.exists():
        logger.warning(f"Bundled skills path not found: {skills_path}")
        result["errors"].append(f"Skills path not found: {skills_path}")
        return result

    # Load skills using SkillLoader with 'filesystem' source type
    loader = SkillLoader(default_source_type="filesystem")
    storage = LocalSkillManager(db)

    try:
        # validate=False for bundled skills since they're trusted and may have
        # version formats like "2.0" instead of strict semver "2.0.0"
        parsed_skills = loader.load_directory(skills_path, validate=False)
    except Exception as e:
        logger.error(f"Failed to load bundled skills: {e}")
        result["success"] = False
        result["errors"].append(f"Failed to load skills: {e}")
        return result

    for parsed in parsed_skills:
        try:
            # Check if skill already exists (global scope)
            existing = storage.get_by_name(parsed.name, project_id=None)

            if existing is not None:
                logger.debug(f"Skill '{parsed.name}' already exists, skipping")
                result["skipped"] += 1
                continue

            # Create the skill in the database
            storage.create_skill(
                name=parsed.name,
                description=parsed.description,
                content=parsed.content,
                version=parsed.version,
                license=parsed.license,
                compatibility=parsed.compatibility,
                allowed_tools=parsed.allowed_tools,
                metadata=parsed.metadata,
                source_path=parsed.source_path,
                source_type="filesystem",
                source_ref=None,
                project_id=None,  # Global scope
                enabled=True,
                always_apply=parsed.always_apply,
                injection_format=parsed.injection_format,
            )

            logger.info(f"Synced bundled skill: {parsed.name}")
            result["synced"] += 1

        except Exception as e:
            error_msg = f"Failed to sync skill '{parsed.name}': {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

    total = result["synced"] + result["skipped"]
    logger.info(
        f"Skill sync complete: {result['synced']} synced, {result['skipped']} skipped, {total} total"
    )

    return result
