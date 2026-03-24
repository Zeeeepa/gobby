"""Rule definition synchronization from bundled YAML templates."""

import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from gobby.storage.database import DatabaseProtocol
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import RuleDefinitionBody

logger = logging.getLogger(__name__)


def get_bundled_rules_path() -> Path:
    """Get the path to bundled rules directory.

    Returns:
        Path to src/gobby/install/shared/workflows/rules/
    """
    from gobby.paths import get_install_dir

    return get_install_dir() / "shared" / "workflows" / "rules"


def sync_bundled_rules(
    db: DatabaseProtocol,
    rules_path: Path | None = None,
    tag: str = "gobby",
) -> dict[str, Any]:
    """Sync rule YAML files to workflow_definitions table with workflow_type='rule'.

    Rule YAML files use the new format with a top-level `rules:` dict where each
    entry defines a rule with `event` and `effect` fields. File-level fields
    (`group`, `tags`, `sources`) are inherited by all rules in the file.

    Args:
        db: Database connection.
        rules_path: Path to rules directory. Defaults to bundled rules path.
        tag: Tag to apply to synced rules. Defaults to "gobby" for bundled.
             Use "user" for user-created templates.

    Returns:
        Dict with success status and counts.
    """
    if rules_path is None:
        rules_path = get_bundled_rules_path()

    # Repair rows where workflow_type was silently changed from 'rule'
    # (e.g. via PUT /api/workflows/{id} before workflow_type was made immutable).
    # Identifies rules by their definition structure: having both event and effect.
    repaired = db.execute(
        "UPDATE workflow_definitions "
        "SET workflow_type = 'rule', updated_at = datetime('now') "
        "WHERE workflow_type != 'rule' "
        "  AND json_extract(definition_json, '$.event') IS NOT NULL "
        "  AND (json_extract(definition_json, '$.effect') IS NOT NULL "
        "       OR json_extract(definition_json, '$.effects') IS NOT NULL)",
    ).rowcount
    if repaired:
        logger.info("Repaired %d rows with incorrect workflow_type (should be 'rule')", repaired)

    result: dict[str, Any] = {
        "success": True,
        "synced": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
    }

    if not rules_path.exists():
        logger.debug("Rules path not found", extra={"path": str(rules_path)})
        return result

    manager = LocalWorkflowDefinitionManager(db)

    for yaml_file in sorted(rules_path.rglob("*.yaml")):
        # Skip deprecated directory (old group files moved here)
        if "deprecated" in yaml_file.relative_to(rules_path).parts:
            continue
        try:
            raw_content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(raw_content)

            if not isinstance(data, dict):
                logger.warning("Skipping non-dict YAML", extra={"file": str(yaml_file)})
                continue

            # Detect rule YAML format: must have 'rules' dict
            rules_dict = data.get("rules")
            if not isinstance(rules_dict, dict):
                logger.debug("No 'rules' key in YAML, skipping", extra={"file": str(yaml_file)})
                result["skipped"] += 1
                continue

            # File-level defaults
            # Derive group from subdirectory name if not explicitly set
            rel_parts = yaml_file.relative_to(rules_path).parts
            dir_group = rel_parts[0] if len(rel_parts) > 1 else None
            file_group = data.get("group") or dir_group
            file_tags = data.get("tags") or []
            if tag not in file_tags:
                file_tags = [*file_tags, tag]
            file_sources = data.get("sources")

            for rule_name, rule_data in rules_dict.items():
                if not isinstance(rule_data, dict):
                    result["errors"].append(f"Rule '{rule_name}' in {yaml_file.name} is not a dict")
                    continue

                # Name collision prevention: user templates can't shadow gobby templates
                if tag != "gobby":
                    gobby_row = db.fetchone(
                        "SELECT id FROM workflow_definitions "
                        "WHERE name = ? AND source = 'template' AND tags LIKE '%\"gobby\"%' "
                        "AND deleted_at IS NULL",
                        (rule_name,),
                    )
                    if gobby_row:
                        logger.debug(
                            "Skipping user rule that collides with gobby template",
                            extra={"rule": rule_name},
                        )
                        result["skipped"] += 1
                        continue

                try:
                    _sync_single_rule(
                        manager=manager,
                        rule_name=rule_name,
                        rule_data=rule_data,
                        file_group=file_group,
                        file_tags=file_tags,
                        file_sources=file_sources,
                        result=result,
                    )
                except Exception as e:
                    error_msg = f"Failed to sync rule '{rule_name}' from {yaml_file.name}: {e}"
                    logger.warning(error_msg)
                    result["errors"].append(error_msg)

        except Exception as e:
            error_msg = f"Failed to parse rule file '{yaml_file}': {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

    # Orphan cleanup: soft-delete rules whose YAML was removed.
    # Scoped by tag to prevent gobby orphan cleanup from affecting user templates
    # and vice versa.
    tag_filter = f'%"{tag}"%'
    on_disk: set[str] = set()
    for yf in sorted(rules_path.rglob("*.yaml")):
        if "deprecated" in yf.relative_to(rules_path).parts:
            continue
        try:
            d = yaml.safe_load(yf.read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("rules"), dict):
                on_disk.update(d["rules"].keys())
        except Exception as e:
            logger.debug(f"Failed to parse {yf.name} during orphan scan: {e}")

    orphan_rows = db.fetchall(
        "SELECT id, name FROM workflow_definitions "
        "WHERE source = 'template' AND workflow_type = 'rule' "
        "AND tags LIKE ? AND deleted_at IS NULL",
        (tag_filter,),
    )
    result["orphaned"] = 0
    orphaned_names: set[str] = set()
    for row in orphan_rows:
        if row["name"] not in on_disk:
            manager.delete(row["id"])
            orphaned_names.add(row["name"])
            logger.info("Soft-deleted orphaned rule", extra={"rule": row["name"], "tag": tag})
            result["orphaned"] += 1

    # Cascade: soft-delete installed copies of orphaned templates,
    # scoped by tag to prevent cross-tag cascade damage
    result["cascaded"] = 0
    for name in orphaned_names:
        installed_rows = db.fetchall(
            "SELECT id FROM workflow_definitions "
            "WHERE name = ? AND source = 'installed' AND workflow_type = 'rule' "
            "AND tags LIKE ? AND deleted_at IS NULL",
            (name, tag_filter),
        )
        for inst_row in installed_rows:
            manager.delete(inst_row["id"])
            result["cascaded"] += 1
            logger.info("Soft-deleted installed copy of orphaned rule", extra={"rule": name})

    _ensure_tag_on_installed(manager, "rule", tag)

    # Propagate tags from templates to installed copies where they've drifted
    # (fixes bug #9657: create_rule doesn't propagate definition_json tags to row-level tags)
    db.execute(
        "UPDATE workflow_definitions SET tags = ("
        "  SELECT t.tags FROM workflow_definitions t"
        "  WHERE t.name = workflow_definitions.name"
        "    AND t.source = 'template' AND t.deleted_at IS NULL"
        ") WHERE source = 'installed' AND deleted_at IS NULL"
        "  AND workflow_type = 'rule'"
        "  AND tags != ("
        "    SELECT t.tags FROM workflow_definitions t"
        "    WHERE t.name = workflow_definitions.name"
        "      AND t.source = 'template' AND t.deleted_at IS NULL"
        "  )",
    )

    total = result["synced"] + result["updated"] + result["skipped"]
    logger.info(
        "Rule definition sync complete",
        extra={
            "synced": result["synced"],
            "updated": result["updated"],
            "skipped": result["skipped"],
            "orphaned": result["orphaned"],
            "total": total,
        },
    )

    return result


def _ensure_tag_on_installed(
    manager: LocalWorkflowDefinitionManager,
    workflow_type: str,
    tag: str = "gobby",
) -> None:
    """Ensure template/installed rows of a given type have the specified tag.

    Only touches rows that don't already have a different owner tag
    (e.g., won't add 'gobby' to 'user'-tagged rows).
    """
    _OWNER_TAGS = {"gobby", "user"}
    rows = manager.list_all(workflow_type=workflow_type, include_deleted=False)
    for row in rows:
        if row.source in ("template", "installed"):
            tags = row.tags or []
            if tag not in tags:
                # Skip rows that already belong to a different owner
                existing_owners = set(tags) & _OWNER_TAGS
                if existing_owners and tag not in existing_owners:
                    continue
                manager.update(row.id, tags=[*tags, tag])


# Backwards-compatible alias
_ensure_gobby_tag_on_installed = _ensure_tag_on_installed


def _propagate_to_installed(
    manager: LocalWorkflowDefinitionManager,
    rule_name: str,
    definition_json: str,
    tags: list[str] | None = None,
) -> None:
    """Propagate definition_json and tags from a template to its installed copy.

    Preserves the installed copy's enabled state.
    """
    installed_row = manager.db.fetchone(
        "SELECT * FROM workflow_definitions "
        "WHERE name = ? AND source = 'installed' AND deleted_at IS NULL",
        (rule_name,),
    )
    if installed_row:
        from gobby.storage.workflow_definitions import WorkflowDefinitionRow

        installed = WorkflowDefinitionRow.from_row(installed_row)
        updates: dict[str, Any] = {}
        if installed.definition_json != definition_json:
            updates["definition_json"] = definition_json
        if tags is not None and set(tags or []) != set(installed.tags or []):
            updates["tags"] = tags
        if updates:
            manager.update(installed.id, **updates)
            logger.info(
                "Propagated changes to installed copy",
                extra={"rule": rule_name, "fields": list(updates.keys())},
            )


def _resolve_sync_placeholders(definition_json: str) -> str:
    """Replace sync-time placeholders in a rule definition.

    Currently supports:
    - ``{{ gobby_bin }}``: resolved to the absolute path of the ``gobby``
      binary via ``shutil.which``, falling back to
      ``<sys.executable> -m gobby`` when the binary isn't on PATH.

    Called once per rule during sync so the DB always stores a concrete path
    that works regardless of whether ``gobby`` is on the CLI's PATH.
    """
    if "{{ gobby_bin }}" not in definition_json:
        return definition_json

    gobby_bin = shutil.which("gobby")
    if not gobby_bin:
        gobby_bin = f"{sys.executable} -m gobby"
    return definition_json.replace("{{ gobby_bin }}", gobby_bin)


def _sync_single_rule(
    manager: LocalWorkflowDefinitionManager,
    rule_name: str,
    rule_data: dict[str, Any],
    file_group: str | None,
    file_tags: list[str] | None,
    file_sources: list[str] | None,
    result: dict[str, Any],
) -> None:
    """Sync a single rule to workflow_definitions.

    Validates against RuleDefinitionBody, then creates or updates the row.
    """
    # Build the RuleDefinitionBody dict
    body_dict: dict[str, Any] = {
        "event": rule_data.get("event"),
    }
    # Support both singular 'effect' and plural 'effects' in YAML
    if "effects" in rule_data:
        body_dict["effects"] = rule_data["effects"]
    elif "effect" in rule_data:
        body_dict["effects"] = [rule_data["effect"]]
    if rule_data.get("when"):
        body_dict["when"] = rule_data["when"]
    if rule_data.get("match"):
        body_dict["match"] = rule_data["match"]
    # Inherit group from file level, rule level overrides
    group = rule_data.get("group", file_group)
    if group:
        body_dict["group"] = group
    if rule_data.get("agent_scope"):
        body_dict["agent_scope"] = rule_data["agent_scope"]
    if rule_data.get("tools"):
        body_dict["tools"] = rule_data["tools"]

    # Validate with Pydantic
    try:
        RuleDefinitionBody(**body_dict)
    except ValidationError as ve:
        raise ValueError(f"Invalid rule definition: {ve}") from ve

    definition_json = _resolve_sync_placeholders(json.dumps(body_dict))
    priority = rule_data.get("priority", 100)
    description = rule_data.get("description")
    enabled = rule_data.get("enabled", False)

    # Check if rule already exists
    existing = manager.get_by_name(rule_name, include_deleted=True, include_templates=True)

    if existing is not None:
        # Restore soft-deleted templates so they're always available
        if existing.deleted_at is not None:
            if existing.source == "template":
                manager.restore(existing.id)
                manager.update(
                    existing.id,
                    name=rule_name,
                    definition_json=definition_json,
                    workflow_type="rule",
                    project_id=None,
                    description=description,
                    enabled=False,
                    priority=priority,
                    sources=file_sources,
                    tags=file_tags,
                    source="template",
                )
                logger.info(
                    "Restored soft-deleted bundled rule",
                    extra={"rule": rule_name},
                )
                result["updated"] += 1
            else:
                result["skipped"] += 1
            return

        if existing.source == "template":
            def_changed = existing.definition_json != definition_json
            tags_changed = set(file_tags or []) != set(existing.tags or [])
            if not def_changed and not tags_changed:
                result["skipped"] += 1
            else:
                # Preserve user's enabled toggle on updates
                manager.update(
                    existing.id,
                    name=rule_name,
                    definition_json=definition_json,
                    workflow_type="rule",
                    project_id=None,
                    description=description,
                    enabled=existing.enabled,
                    priority=priority,
                    sources=file_sources,
                    tags=file_tags,
                    source="template",
                )
                # Propagate changes to installed copy (preserve enabled)
                _propagate_to_installed(manager, rule_name, definition_json, tags=file_tags)
                result["updated"] += 1
        else:
            # Non-template copy shadows the template row — get_by_name prefers
            # non-template over template. Look up the template row directly and
            # update it if the definition has changed on disk.
            template_row = manager.db.fetchone(
                "SELECT * FROM workflow_definitions WHERE name = ? AND source = 'template' AND deleted_at IS NULL",
                (rule_name,),
            )
            if template_row:
                from gobby.storage.workflow_definitions import WorkflowDefinitionRow

                template = WorkflowDefinitionRow.from_row(template_row)
                if template.deleted_at:
                    manager.restore(template.id)
                    manager.update(
                        template.id,
                        name=rule_name,
                        definition_json=definition_json,
                        workflow_type="rule",
                        project_id=None,
                        description=description,
                        enabled=False,
                        priority=priority,
                        sources=file_sources,
                        tags=file_tags,
                        source="template",
                    )
                    logger.info(
                        "Restored soft-deleted template behind installed copy",
                        extra={"rule": rule_name},
                    )
                    result["updated"] += 1
                else:
                    def_changed = template.definition_json != definition_json
                    tags_changed = set(file_tags or []) != set(template.tags or [])
                    if def_changed or tags_changed:
                        manager.update(
                            template.id,
                            name=rule_name,
                            definition_json=definition_json,
                            workflow_type="rule",
                            project_id=None,
                            description=description,
                            enabled=template.enabled,
                            priority=priority,
                            sources=file_sources,
                            tags=file_tags,
                            source="template",
                        )
                        # Propagate to the installed copy that shadows this template
                        if existing.source == "installed":
                            _propagate_to_installed(
                                manager, rule_name, definition_json, tags=file_tags
                            )
                        result["updated"] += 1
                    else:
                        result["skipped"] += 1
            else:
                # No template row exists — create one
                manager.create(
                    name=rule_name,
                    definition_json=definition_json,
                    workflow_type="rule",
                    project_id=None,
                    description=description,
                    enabled=False,
                    priority=priority,
                    sources=file_sources,
                    tags=file_tags,
                    source="template",
                )
                logger.info(
                    "Created missing template row behind installed copy",
                    extra={"rule": rule_name},
                )
                result["synced"] += 1
        return

    # Create new rule
    manager.create(
        name=rule_name,
        definition_json=definition_json,
        workflow_type="rule",
        project_id=None,
        description=description,
        enabled=enabled,
        priority=priority,
        sources=file_sources,
        tags=file_tags,
        source="template",
    )
    result["synced"] += 1
