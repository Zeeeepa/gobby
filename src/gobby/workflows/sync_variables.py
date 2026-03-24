"""Variable definition synchronization from bundled YAML templates."""

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from gobby.storage.database import DatabaseProtocol
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.sync_rules import _ensure_tag_on_installed, _propagate_to_installed

logger = logging.getLogger(__name__)


def get_bundled_variables_path() -> Path:
    """Get the path to bundled variables directory.

    Returns:
        Path to src/gobby/install/shared/workflows/variables/
    """
    from gobby.paths import get_install_dir

    return get_install_dir() / "shared" / "workflows" / "variables"


def sync_bundled_variables(
    db: DatabaseProtocol,
    variables_path: Path | None = None,
    tag: str = "gobby",
) -> dict[str, Any]:
    """Sync variable definitions from YAML files to the database.

    Variable YAML files use a ``variables:`` dict where each key is the variable
    name and the value contains ``value`` and optional ``description``.  File-level
    ``tags`` are inherited by all variables in the file.

    Args:
        db: Database connection.
        variables_path: Path to variables directory. Defaults to bundled path.
        tag: Tag to apply. Defaults to "gobby" for bundled, "user" for user-created.

    Returns:
        Dict with success status and counts.
    """
    if variables_path is None:
        variables_path = get_bundled_variables_path()

    result: dict[str, Any] = {
        "success": True,
        "synced": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
    }

    if not variables_path.exists():
        logger.debug("Variables path not found", extra={"path": str(variables_path)})
        return result

    manager = LocalWorkflowDefinitionManager(db)

    for yaml_file in sorted(variables_path.glob("*.yaml")):
        try:
            raw_content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(raw_content)

            if not isinstance(data, dict):
                logger.warning("Skipping non-dict YAML", extra={"file": str(yaml_file)})
                continue

            variables_dict = data.get("variables")
            if not isinstance(variables_dict, dict):
                logger.debug("No 'variables' key in YAML, skipping", extra={"file": str(yaml_file)})
                result["skipped"] += 1
                continue

            file_tags = data.get("tags") or []
            if tag not in file_tags:
                file_tags = [*file_tags, tag]

            for var_name, var_data in variables_dict.items():
                if not isinstance(var_data, dict):
                    result["errors"].append(
                        f"Variable '{var_name}' in {yaml_file.name} is not a dict"
                    )
                    continue

                try:
                    _sync_single_variable(
                        manager=manager,
                        var_name=var_name,
                        var_data=var_data,
                        file_tags=file_tags,
                        result=result,
                    )
                except Exception as e:
                    error_msg = f"Failed to sync variable '{var_name}' from {yaml_file.name}: {e}"
                    logger.warning(error_msg)
                    result["errors"].append(error_msg)

        except Exception as e:
            error_msg = f"Failed to parse variable file '{yaml_file}': {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

    # Orphan cleanup: collect all variable names from disk, soft-delete DB rows
    # whose names are no longer present on disk.
    # Scoped by gobby tag to prevent cross-tag cascade damage.
    tag_filter = '%"gobby"%'
    on_disk: set[str] = set()
    for yf in sorted(variables_path.glob("*.yaml")):
        try:
            d = yaml.safe_load(yf.read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("variables"), dict):
                on_disk.update(d["variables"].keys())
        except Exception:
            pass

    orphan_rows = db.fetchall(
        "SELECT id, name FROM workflow_definitions "
        "WHERE source = 'template' AND workflow_type = 'variable' "
        "AND tags LIKE ? AND deleted_at IS NULL",
        (tag_filter,),
    )
    result["orphaned"] = 0
    orphaned_names: set[str] = set()
    for row in orphan_rows:
        if row["name"] not in on_disk:
            manager.delete(row["id"])
            orphaned_names.add(row["name"])
            logger.info("Soft-deleted orphaned bundled variable", extra={"variable": row["name"]})
            result["orphaned"] += 1

    # Cascade: soft-delete installed copies of orphaned templates,
    # scoped by tag to prevent cross-tag cascade damage
    result["cascaded"] = 0
    for name in orphaned_names:
        installed_rows = db.fetchall(
            "SELECT id FROM workflow_definitions "
            "WHERE name = ? AND source = 'installed' AND workflow_type = 'variable' "
            "AND tags LIKE ? AND deleted_at IS NULL",
            (name, tag_filter),
        )
        for inst_row in installed_rows:
            manager.delete(inst_row["id"])
            result["cascaded"] += 1
            logger.info(
                "Soft-deleted installed copy of orphaned variable", extra={"variable": name}
            )

    _ensure_tag_on_installed(manager, "variable")

    total = result["synced"] + result["updated"] + result["skipped"]
    logger.info(
        "Variable definition sync complete",
        extra={
            "synced": result["synced"],
            "updated": result["updated"],
            "skipped": result["skipped"],
            "orphaned": result["orphaned"],
            "total": total,
        },
    )

    return result


def _sync_single_variable(
    manager: LocalWorkflowDefinitionManager,
    var_name: str,
    var_data: dict[str, Any],
    file_tags: list[str] | None,
    result: dict[str, Any],
) -> None:
    """Sync a single variable to workflow_definitions.

    Validates against VariableDefinitionBody, then creates or updates the row.
    """
    from gobby.workflows.definitions import VariableDefinitionBody

    body_dict: dict[str, Any] = {
        "variable": var_name,
        "value": var_data.get("value"),
    }
    if var_data.get("description"):
        body_dict["description"] = var_data["description"]

    try:
        VariableDefinitionBody(**body_dict)
    except ValidationError as ve:
        raise ValueError(f"Invalid variable definition: {ve}") from ve

    definition_json = json.dumps(body_dict)
    description = var_data.get("description")

    existing = manager.get_by_name(var_name, include_deleted=True, include_templates=True)

    if existing is not None:
        if existing.deleted_at is not None:
            if existing.source == "template":
                manager.restore(existing.id)
                manager.update(
                    existing.id,
                    name=var_name,
                    definition_json=definition_json,
                    workflow_type="variable",
                    project_id=None,
                    description=description,
                    enabled=True,
                    priority=100,
                    source="template",
                    tags=file_tags,
                )
                logger.info("Restored soft-deleted bundled variable", extra={"variable": var_name})
                result["updated"] += 1
            else:
                result["skipped"] += 1
            return

        if existing.source == "template":
            if existing.definition_json == definition_json:
                result["skipped"] += 1
            else:
                manager.update(
                    existing.id,
                    name=var_name,
                    definition_json=definition_json,
                    workflow_type="variable",
                    project_id=None,
                    description=description,
                    enabled=existing.enabled,
                    priority=100,
                    source="template",
                    tags=file_tags,
                )
                _propagate_to_installed(manager, var_name, definition_json)
                result["updated"] += 1
        else:
            template_row = manager.db.fetchone(
                "SELECT * FROM workflow_definitions WHERE name = ? AND source = 'template'",
                (var_name,),
            )
            if template_row:
                from gobby.storage.workflow_definitions import WorkflowDefinitionRow

                template = WorkflowDefinitionRow.from_row(template_row)
                if template.deleted_at:
                    manager.restore(template.id)
                    manager.update(
                        template.id,
                        name=var_name,
                        definition_json=definition_json,
                        workflow_type="variable",
                        project_id=None,
                        description=description,
                        enabled=True,
                        priority=100,
                        source="template",
                        tags=file_tags,
                    )
                    result["updated"] += 1
                elif template.definition_json != definition_json:
                    manager.update(
                        template.id,
                        name=var_name,
                        definition_json=definition_json,
                        workflow_type="variable",
                        project_id=None,
                        description=description,
                        enabled=template.enabled,
                        priority=100,
                        source="template",
                        tags=file_tags,
                    )
                    if existing.source == "installed":
                        _propagate_to_installed(manager, var_name, definition_json)
                    result["updated"] += 1
                else:
                    result["skipped"] += 1
            else:
                manager.create(
                    name=var_name,
                    definition_json=definition_json,
                    workflow_type="variable",
                    project_id=None,
                    description=description,
                    enabled=True,
                    priority=100,
                    source="template",
                    tags=file_tags,
                )
                result["synced"] += 1
        return

    manager.create(
        name=var_name,
        definition_json=definition_json,
        workflow_type="variable",
        project_id=None,
        description=description,
        enabled=True,
        priority=100,
        source="template",
        tags=file_tags,
    )
    result["synced"] += 1
