"""Bundled prompt synchronization on daemon start.

Loads prompt markdown files from install/shared/prompts/ and syncs
them to the DB prompts table with tier='bundled'. Removes stale entries
whose source files no longer exist.

Also provides one-time migration of file-based overrides (~/.gobby/prompts/)
into the database as tier='user'.
"""

import logging
from pathlib import Path
from typing import Any

from gobby.storage.database import DatabaseProtocol
from gobby.storage.prompts import LocalPromptManager

__all__ = [
    "sync_bundled_prompts",
    "migrate_file_overrides_to_db",
    "get_bundled_prompts_path",
]

logger = logging.getLogger(__name__)


def get_bundled_prompts_path() -> Path:
    """Get the path to bundled prompts directory.

    Returns:
        Path to install/shared/prompts/
    """
    from gobby.paths import get_install_dir

    return get_install_dir() / "shared" / "prompts"


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from template content.

    Standalone version of PromptLoader._parse_frontmatter for reuse.

    Args:
        content: Raw file content with optional ---frontmatter---.

    Returns:
        Tuple of (frontmatter dict, body content).
    """
    import re

    import yaml

    frontmatter_pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    match = frontmatter_pattern.match(content)

    if match:
        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
            body = content[match.end() :]
            return frontmatter, body
        except yaml.YAMLError as e:
            logger.warning(f"Failed to parse frontmatter: {e}")
            return {}, content

    return {}, content


def sync_bundled_prompts(
    db: DatabaseProtocol,
    prompts_dir: Path | None = None,
) -> dict[str, Any]:
    """Sync bundled prompts from markdown files to the database.

    For each .md file in the prompts directory:
    1. Parse frontmatter for metadata
    2. Upsert into DB with tier='bundled'
    3. Remove DB entries whose source files no longer exist

    Args:
        db: Database connection.
        prompts_dir: Override prompts directory (for testing).

    Returns:
        Dict with synced/updated/skipped/removed counts.
    """
    if prompts_dir is None:
        prompts_dir = get_bundled_prompts_path()

    result: dict[str, Any] = {
        "success": True,
        "synced": 0,
        "updated": 0,
        "skipped": 0,
        "removed": 0,
        "errors": [],
    }

    if not prompts_dir.exists():
        logger.debug(f"Prompts directory not found: {prompts_dir}")
        return result

    manager = LocalPromptManager(db)
    seen_paths: set[str] = set()

    for md_file in sorted(prompts_dir.rglob("*.md")):
        try:
            raw = md_file.read_text(encoding="utf-8")
            frontmatter, body = _parse_frontmatter(raw)

            # Derive prompt path from relative file path (without .md)
            rel_path = md_file.relative_to(prompts_dir)
            prompt_path = str(rel_path.with_suffix(""))

            seen_paths.add(prompt_path)

            name = frontmatter.get("name", prompt_path)
            description = frontmatter.get("description", "")
            version = str(frontmatter.get("version", "1.0"))
            category = prompt_path.split("/")[0] if "/" in prompt_path else "general"
            variables = frontmatter.get("variables")
            content = body.strip()
            source_file = str(md_file)

            # Check if bundled prompt already exists
            existing = manager.get_bundled(prompt_path)

            if existing:
                # Compare content and version to detect staleness
                if existing.content == content and existing.version == version:
                    result["skipped"] += 1
                    continue

                # Update
                manager.save_prompt(
                    path=prompt_path,
                    content=content,
                    tier="bundled",
                    name=name,
                    description=description,
                    version=version,
                    category=category,
                    variables=variables,
                    source_file=source_file,
                )
                result["updated"] += 1
                logger.debug(f"Updated bundled prompt: {prompt_path}")
            else:
                # Create
                manager.save_prompt(
                    path=prompt_path,
                    content=content,
                    tier="bundled",
                    name=name,
                    description=description,
                    version=version,
                    category=category,
                    variables=variables,
                    source_file=source_file,
                )
                result["synced"] += 1
                logger.debug(f"Synced bundled prompt: {prompt_path}")

        except Exception as e:
            error_msg = f"Failed to process {md_file.name}: {e}"
            logger.warning(error_msg)
            result["errors"].append(error_msg)

    # Remove stale bundled prompts (exist in DB but not on disk)
    existing_paths = manager.list_bundled_paths()
    for stale_path in existing_paths - seen_paths:
        manager.delete_prompt(stale_path, "bundled")
        result["removed"] += 1
        logger.info(f"Removed stale bundled prompt: {stale_path}")

    total = result["synced"] + result["updated"] + result["skipped"]
    if total > 0 or result["removed"] > 0:
        logger.info(
            f"Prompt sync complete: {result['synced']} synced, "
            f"{result['updated']} updated, {result['skipped']} skipped, "
            f"{result['removed']} removed"
        )

    return result


def migrate_file_overrides_to_db(
    db: DatabaseProtocol,
    overrides_dir: Path | None = None,
) -> dict[str, Any]:
    """One-time migration of file-based prompt overrides to DB.

    Reads all .md files from ~/.gobby/prompts/, inserts them as
    tier='user' prompts, then renames the directory to prompts.migrated.

    Args:
        db: Database connection.
        overrides_dir: Override directory (for testing).

    Returns:
        Dict with migration counts.
    """
    if overrides_dir is None:
        overrides_dir = Path.home() / ".gobby" / "prompts"

    result: dict[str, Any] = {
        "migrated": 0,
        "skipped": 0,
        "errors": [],
    }

    if not overrides_dir.exists() or not overrides_dir.is_dir():
        return result

    manager = LocalPromptManager(db)
    md_files = list(overrides_dir.rglob("*.md"))

    if not md_files:
        return result

    for md_file in md_files:
        try:
            raw = md_file.read_text(encoding="utf-8")
            frontmatter, body = _parse_frontmatter(raw)

            rel_path = md_file.relative_to(overrides_dir)
            prompt_path = str(rel_path.with_suffix(""))

            name = frontmatter.get("name", prompt_path)
            description = frontmatter.get("description", "")
            version = str(frontmatter.get("version", "1.0"))
            category = prompt_path.split("/")[0] if "/" in prompt_path else "general"
            variables = frontmatter.get("variables")
            content = body.strip()

            manager.save_prompt(
                path=prompt_path,
                content=content,
                tier="user",
                name=name,
                description=description,
                version=version,
                category=category,
                variables=variables,
                source_file=str(md_file),
            )
            result["migrated"] += 1
            logger.info(f"Migrated file override to DB: {prompt_path}")

        except Exception as e:
            error_msg = f"Failed to migrate {md_file}: {e}"
            logger.warning(error_msg)
            result["errors"].append(error_msg)

    # Rename directory to mark migration complete
    if result["migrated"] > 0 and not result["errors"]:
        migrated_dir = overrides_dir.parent / "prompts.migrated"
        try:
            overrides_dir.rename(migrated_dir)
            logger.info(
                f"Migrated {result['migrated']} prompt overrides to DB, "
                f"renamed {overrides_dir} → {migrated_dir}"
            )
        except OSError as e:
            logger.warning(f"Failed to rename overrides dir: {e}")

    return result
