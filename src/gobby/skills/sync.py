"""Skill synchronization for bundled skills.

This module provides sync_bundled_skills() which loads skills from the
bundled install/shared/skills/ directory and syncs them to the database
as templates, following the same pattern as sync_bundled_rules().

Templates are created with source='template' and enabled=False.
install_all_templates() creates installed copies with enabled=True.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gobby.skills.loader import SkillLoader
from gobby.skills.parser import ParsedSkill

if TYPE_CHECKING:
    from gobby.skills.loader import LoadedSkillFile
from gobby.storage.database import DatabaseProtocol
from gobby.storage.skills import LocalSkillManager, Skill, SkillFile

__all__: list[str] = ["sync_bundled_skills", "get_bundled_skills_path"]

logger = logging.getLogger(__name__)


def _loaded_to_skill_files(
    skill_id: str, loaded_files: list[LoadedSkillFile] | None
) -> list[SkillFile]:
    """Convert LoadedSkillFile list from loader to SkillFile list for storage."""
    if not loaded_files:
        return []
    return [
        SkillFile(
            id="",  # set_skill_files generates IDs for new files
            skill_id=skill_id,
            path=lf.path,
            file_type=lf.file_type,
            content=lf.content,
            content_hash=lf.content_hash,
            size_bytes=lf.size_bytes,
        )
        for lf in loaded_files
    ]


def _persist_skill_files(
    storage: LocalSkillManager,
    skill_id: str,
    loaded_files: list[LoadedSkillFile] | None,
) -> None:
    """Convert loaded files and persist to storage."""
    skill_files = _loaded_to_skill_files(skill_id, loaded_files)
    if skill_files:
        storage.set_skill_files(skill_id, skill_files)


def get_bundled_skills_path() -> Path:
    """Get the path to bundled skills directory.

    Returns:
        Path to src/gobby/install/shared/skills/
    """
    from gobby.paths import get_install_dir

    return get_install_dir() / "shared" / "skills"


def _propagate_to_installed(
    storage: LocalSkillManager,
    skill_name: str,
    parsed: ParsedSkill,
) -> None:
    """Propagate content changes from a template to its installed copy.

    Preserves the installed copy's enabled state.
    """
    installed = storage.get_by_name(skill_name, project_id=None, source="installed")
    if not installed:
        return

    needs_update = (
        installed.description != parsed.description
        or installed.content != parsed.content
        or installed.version != parsed.version
        or installed.license != parsed.license
        or installed.compatibility != parsed.compatibility
        or installed.allowed_tools != parsed.allowed_tools
        or installed.metadata != parsed.metadata
        or installed.always_apply != parsed.always_apply
        or installed.injection_format != parsed.injection_format
    )

    if needs_update:
        storage.update_skill(
            skill_id=installed.id,
            description=parsed.description,
            content=parsed.content,
            version=parsed.version,
            license=parsed.license,
            compatibility=parsed.compatibility,
            allowed_tools=parsed.allowed_tools,
            metadata=parsed.metadata,
            always_apply=parsed.always_apply,
            injection_format=parsed.injection_format,
        )
        logger.info(f"Propagated changes to installed copy: {skill_name}")
        # Propagate files to installed copy
        _persist_skill_files(storage, installed.id, parsed.loaded_files)


def _sync_single_skill(
    storage: LocalSkillManager,
    parsed: ParsedSkill,
    result: dict[str, Any],
) -> None:
    """Sync a single parsed skill to the database as a template.

    Follows the same pattern as _sync_single_rule():
    - Creates with source='template', enabled=False
    - Restores soft-deleted templates
    - Preserves user's enabled toggle on updates
    - Propagates content changes to installed copies
    - Skips non-template skills with same name
    """
    # Check if skill already exists (include deleted and templates)
    existing = storage.get_by_name(
        parsed.name, project_id=None, include_deleted=True, include_templates=True
    )

    if existing is not None:
        if existing.source == "template":
            _handle_existing_template(storage, existing, parsed, result)
        else:
            # Non-template (installed) copy shadows the template.
            # Look up the template row directly.
            _handle_installed_shadows_template(storage, existing, parsed, result)
        return

    # No existing skill — create new template
    new_skill = storage.create_skill(
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
        project_id=None,
        enabled=False,
        always_apply=parsed.always_apply,
        injection_format=parsed.injection_format,
        source="template",
    )
    # Persist skill files
    _persist_skill_files(storage, new_skill.id, parsed.loaded_files)
    result["synced"] += 1


def _handle_existing_template(
    storage: LocalSkillManager,
    existing: Skill,
    parsed: ParsedSkill,
    result: dict[str, Any],
) -> None:
    """Handle case where get_by_name returns a template row."""
    # Restore soft-deleted templates
    if existing.deleted_at is not None:
        storage.restore(existing.id)
        storage.update_skill(
            skill_id=existing.id,
            description=parsed.description,
            content=parsed.content,
            version=parsed.version,
            license=parsed.license,
            compatibility=parsed.compatibility,
            allowed_tools=parsed.allowed_tools,
            metadata=parsed.metadata,
            enabled=False,
            always_apply=parsed.always_apply,
            injection_format=parsed.injection_format,
        )
        logger.info(f"Restored soft-deleted bundled skill: {parsed.name}")
        # Sync files for restored template
        _persist_skill_files(storage, existing.id, parsed.loaded_files)
        result["updated"] += 1
        return

    # Check if content changed
    needs_update = (
        existing.description != parsed.description
        or existing.content != parsed.content
        or existing.version != parsed.version
        or existing.license != parsed.license
        or existing.compatibility != parsed.compatibility
        or existing.allowed_tools != parsed.allowed_tools
        or existing.metadata != parsed.metadata
        or existing.always_apply != parsed.always_apply
        or existing.injection_format != parsed.injection_format
    )

    if not needs_update:
        result["skipped"] += 1
        return

    # Update template, preserving user's enabled toggle
    storage.update_skill(
        skill_id=existing.id,
        description=parsed.description,
        content=parsed.content,
        version=parsed.version,
        license=parsed.license,
        compatibility=parsed.compatibility,
        allowed_tools=parsed.allowed_tools,
        metadata=parsed.metadata,
        enabled=existing.enabled,
        always_apply=parsed.always_apply,
        injection_format=parsed.injection_format,
    )
    # Propagate to installed copy
    _propagate_to_installed(storage, parsed.name, parsed)
    # Sync files for template
    _persist_skill_files(storage, existing.id, parsed.loaded_files)
    result["updated"] += 1


def _handle_installed_shadows_template(
    storage: LocalSkillManager,
    existing: Skill,
    parsed: ParsedSkill,
    result: dict[str, Any],
) -> None:
    """Handle case where an installed copy shadows the template.

    get_by_name returned a non-template row. Look up the template row
    directly and update it, or create it if missing.
    """
    template_row = storage.db.fetchone(
        "SELECT * FROM skills WHERE name = ? AND source = 'template' AND project_id IS NULL",
        (parsed.name,),
    )

    if template_row:
        template = Skill.from_row(template_row)
        if template.deleted_at:
            storage.restore(template.id)
            storage.update_skill(
                skill_id=template.id,
                description=parsed.description,
                content=parsed.content,
                version=parsed.version,
                license=parsed.license,
                compatibility=parsed.compatibility,
                allowed_tools=parsed.allowed_tools,
                metadata=parsed.metadata,
                enabled=False,
                always_apply=parsed.always_apply,
                injection_format=parsed.injection_format,
            )
            logger.info(f"Restored soft-deleted template behind installed copy: {parsed.name}")
            _persist_skill_files(storage, template.id, parsed.loaded_files)
            result["updated"] += 1
        else:
            needs_update = (
                template.description != parsed.description
                or template.content != parsed.content
                or template.version != parsed.version
                or template.license != parsed.license
                or template.compatibility != parsed.compatibility
                or template.allowed_tools != parsed.allowed_tools
                or template.metadata != parsed.metadata
                or template.always_apply != parsed.always_apply
                or template.injection_format != parsed.injection_format
            )
            if needs_update:
                storage.update_skill(
                    skill_id=template.id,
                    description=parsed.description,
                    content=parsed.content,
                    version=parsed.version,
                    license=parsed.license,
                    compatibility=parsed.compatibility,
                    allowed_tools=parsed.allowed_tools,
                    metadata=parsed.metadata,
                    enabled=template.enabled,
                    always_apply=parsed.always_apply,
                    injection_format=parsed.injection_format,
                )
                # Propagate to the installed copy
                if existing.source == "installed":
                    _propagate_to_installed(storage, parsed.name, parsed)
                _persist_skill_files(storage, template.id, parsed.loaded_files)
                result["updated"] += 1
            else:
                result["skipped"] += 1
    else:
        # No template row — create one
        new_template = storage.create_skill(
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
            project_id=None,
            enabled=False,
            always_apply=parsed.always_apply,
            injection_format=parsed.injection_format,
            source="template",
        )
        _persist_skill_files(storage, new_template.id, parsed.loaded_files)
        logger.info(f"Created missing template row behind installed copy: {parsed.name}")
        result["synced"] += 1


def sync_bundled_skills(db: DatabaseProtocol) -> dict[str, Any]:
    """Sync bundled skills from install/shared/skills/ to the database.

    Follows the template pattern (like sync_bundled_rules):
    1. Creates skills with source='template', enabled=False
    2. Restores soft-deleted templates
    3. Preserves user's enabled toggle on template updates
    4. Propagates content changes to installed copies
    5. Soft-deletes orphaned templates (SKILL.md removed from disk)

    Args:
        db: Database connection

    Returns:
        Dict with success status and counts
    """
    skills_path = get_bundled_skills_path()

    result: dict[str, Any] = {
        "success": True,
        "synced": 0,
        "updated": 0,
        "skipped": 0,
        "orphaned": 0,
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

    # Track names on disk for orphan cleanup
    on_disk: set[str] = set()

    for parsed in parsed_skills:
        on_disk.add(parsed.name)
        try:
            _sync_single_skill(storage, parsed, result)
        except Exception as e:
            error_msg = f"Failed to sync skill '{parsed.name}': {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

    # Orphan cleanup: soft-delete template skills whose SKILL.md was removed
    orphan_rows = db.fetchall(
        "SELECT id, name FROM skills "
        "WHERE source = 'template' AND project_id IS NULL "
        "AND deleted_at IS NULL",
    )
    orphaned_names: set[str] = set()
    for row in orphan_rows:
        if row["name"] not in on_disk:
            storage.delete_skill(row["id"])
            orphaned_names.add(row["name"])
            logger.info(f"Soft-deleted orphaned bundled skill: {row['name']}")
            result["orphaned"] += 1

    # Cascade: soft-delete global installed copies of orphaned templates
    result["cascaded"] = 0
    for name in orphaned_names:
        installed_rows = db.fetchall(
            "SELECT id FROM skills WHERE name = ? AND source = 'installed' "
            "AND project_id IS NULL AND deleted_at IS NULL",
            (name,),
        )
        for inst_row in installed_rows:
            storage.delete_skill(inst_row["id"])
            logger.info(f"Soft-deleted installed copy of orphaned skill: {name}")
            result["cascaded"] += 1

    total = result["synced"] + result["updated"] + result["skipped"]
    logger.info(
        f"Skill sync complete: {result['synced']} synced, "
        f"{result['updated']} updated, {result['skipped']} skipped, "
        f"{result['orphaned']} orphaned, {total} total"
    )

    return result
