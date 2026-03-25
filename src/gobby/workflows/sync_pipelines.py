"""Pipeline definition synchronization from bundled YAML templates."""

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from gobby.storage.database import DatabaseProtocol
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import PipelineDefinition, WorkflowDefinition
from gobby.workflows.sync_rules import ensure_tag_on_installed, propagate_to_installed

logger = logging.getLogger(__name__)

VALID_WORKFLOW_TYPES = {"rule", "variable", "agent", "pipeline"}


def get_bundled_pipelines_path() -> Path:
    """Get the path to bundled pipelines directory."""
    from gobby.paths import get_install_dir

    return get_install_dir() / "shared" / "workflows" / "pipelines"


def sync_bundled_pipelines(db: DatabaseProtocol) -> dict[str, Any]:
    """Sync bundled pipeline definitions from install/shared/workflows/pipelines/ to the database.

    This function:
    1. Walks all .yaml files in the bundled pipelines directory
    2. Parses each and validates it has a 'name' field
    3. Creates new records or updates changed content (idempotent)
    4. All records are created with source='template' and project_id=None

    Args:
        db: Database connection

    Returns:
        Dict with success status and counts
    """
    workflows_path = get_bundled_pipelines_path()

    result: dict[str, Any] = {
        "success": True,
        "synced": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
    }

    if not workflows_path.exists():
        logger.warning("Bundled workflows path not found", extra={"path": str(workflows_path)})
        result["errors"].append(f"Workflows path not found: {workflows_path}")
        return result

    manager = LocalWorkflowDefinitionManager(db)
    parsed_names: set[str] = set()  # Collect names during main loop for orphan scan

    for yaml_file in sorted(workflows_path.glob("*.yaml")):
        try:
            raw_content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(raw_content)

            if not isinstance(data, dict):
                logger.warning("Skipping non-dict YAML file", extra={"workflow": str(yaml_file)})
                continue

            if "name" not in data:
                logger.warning(
                    "Skipping YAML without 'name' field", extra={"workflow": str(yaml_file)}
                )
                continue

            # Validate against Pydantic schema before any DB operations
            schema_cls = (
                PipelineDefinition if data.get("type") == "pipeline" else WorkflowDefinition
            )
            try:
                schema_cls(**data)
            except ValidationError as ve:
                logger.warning(
                    "Skipping invalid workflow",
                    extra={"workflow": str(yaml_file), "error": str(ve)},
                )
                continue

            name = data["name"]
            parsed_names.add(name)
            definition_json = json.dumps(data)

            # Derive metadata from the YAML content
            yaml_type = data.get("type", "")
            workflow_type = yaml_type if yaml_type in VALID_WORKFLOW_TYPES else "pipeline"
            description = data.get("description", "")
            version = str(data.get("version", "1.0"))
            enabled = bool(data.get("enabled", False))
            priority = data.get("priority", 100)
            sources_list = data.get("sources")

            # Check if workflow already exists (global scope, including soft-deleted)
            existing = manager.get_by_name(name, include_deleted=True, include_templates=True)

            if existing is not None:
                # If soft-deleted template, restore it so templates are always available
                if existing.deleted_at is not None:
                    if existing.source == "template":
                        manager.restore(existing.id)
                        manager.update(
                            existing.id,
                            name=name,
                            definition_json=definition_json,
                            workflow_type=workflow_type,
                            project_id=None,
                            description=description,
                            version=version,
                            enabled=False,
                            priority=priority,
                            sources=sources_list,
                            source="template",
                            tags=["gobby"],
                        )
                        logger.info(
                            "Restored soft-deleted bundled workflow",
                            extra={"workflow": name},
                        )
                        result["updated"] += 1
                    else:
                        logger.debug(
                            "Non-template workflow is soft-deleted, skipping sync",
                            extra={"workflow": name},
                        )
                        result["skipped"] += 1
                    continue

                if existing.source == "template":
                    # Compare definition_json content to detect changes
                    if existing.definition_json == definition_json:
                        logger.debug(
                            "Workflow already up to date, skipping", extra={"workflow": name}
                        )
                        result["skipped"] += 1
                    else:
                        # Atomic in-place update (preserves id and user's enabled toggle)
                        manager.update(
                            existing.id,
                            name=name,
                            definition_json=definition_json,
                            workflow_type=workflow_type,
                            project_id=None,
                            description=description,
                            version=version,
                            enabled=existing.enabled,
                            priority=priority,
                            sources=sources_list,
                            source="template",
                            tags=["gobby"],
                        )
                        # Propagate definition changes to installed copy
                        propagate_to_installed(manager, name, definition_json)
                        logger.info("Updated bundled workflow definition", extra={"workflow": name})
                        result["updated"] += 1
                else:
                    # Non-template workflow with same name shadows the template.
                    # Look up the actual template row and update it if changed,
                    # then propagate to the installed copy.
                    template_row = manager.db.fetchone(
                        "SELECT * FROM workflow_definitions "
                        "WHERE name = ? AND source = 'template' AND deleted_at IS NULL",
                        (name,),
                    )
                    if template_row:
                        from gobby.storage.workflow_definitions import WorkflowDefinitionRow

                        tpl = WorkflowDefinitionRow.from_row(template_row)
                        if tpl.definition_json != definition_json:
                            manager.update(
                                tpl.id,
                                definition_json=definition_json,
                                description=description,
                                version=version,
                                enabled=tpl.enabled,
                                priority=priority,
                                sources=sources_list,
                                source="template",
                                tags=["gobby"],
                            )
                            propagate_to_installed(manager, name, definition_json)
                            logger.info(
                                "Updated shadowed workflow template and propagated",
                                extra={"workflow": name},
                            )
                            result["updated"] += 1
                        else:
                            result["skipped"] += 1
                    else:
                        logger.debug(
                            "Workflow exists with non-template source, no template to update",
                            extra={"workflow": name, "source": existing.source},
                        )
                        result["skipped"] += 1
                continue

            # Create the workflow definition in the database
            manager.create(
                name=name,
                definition_json=definition_json,
                workflow_type=workflow_type,
                project_id=None,
                description=description,
                version=version,
                enabled=enabled,
                priority=priority,
                sources=sources_list,
                source="template",
                tags=["gobby"],
            )
            logger.info("Synced bundled workflow definition", extra={"workflow": name})
            result["synced"] += 1

        except Exception as e:
            error_msg = f"Failed to sync workflow definition '{yaml_file}': {e}"
            logger.error(
                "Failed to sync workflow definition",
                extra={"workflow": str(yaml_file), "error": str(e)},
            )
            result["errors"].append(error_msg)

    # Orphan cleanup: soft-delete template workflows whose YAML was removed.
    # Scoped by gobby tag to prevent cross-tag cascade damage.
    # Uses parsed_names collected during the main loop above (no re-parsing).
    tag_filter = '%"gobby"%'

    valid_types_sql = ", ".join(f"'{t}'" for t in VALID_WORKFLOW_TYPES)
    orphan_rows = db.fetchall(
        "SELECT id, name FROM workflow_definitions "
        f"WHERE source = 'template' AND workflow_type IN ({valid_types_sql}) "
        "AND tags LIKE ? AND deleted_at IS NULL",
        (tag_filter,),
    )
    result["orphaned"] = 0
    orphaned_names: set[str] = set()
    for row in orphan_rows:
        if row["name"] not in parsed_names:
            manager.delete(row["id"])
            orphaned_names.add(row["name"])
            logger.info("Soft-deleted orphaned bundled workflow", extra={"workflow": row["name"]})
            result["orphaned"] += 1

    # Cascade: soft-delete installed copies of orphaned templates,
    # scoped by tag to prevent cross-tag cascade damage
    result["cascaded"] = 0
    for name in orphaned_names:
        installed_rows = db.fetchall(
            "SELECT id FROM workflow_definitions "
            "WHERE name = ? AND source = 'installed' "
            f"AND workflow_type IN ({valid_types_sql}) "
            "AND tags LIKE ? AND deleted_at IS NULL",
            (name, tag_filter),
        )
        for inst_row in installed_rows:
            manager.delete(inst_row["id"])
            result["cascaded"] += 1
            logger.info(
                "Soft-deleted installed copy of orphaned workflow", extra={"workflow": name}
            )

    ensure_tag_on_installed(manager, "workflow")
    ensure_tag_on_installed(manager, "pipeline")

    total = result["synced"] + result["updated"] + result["skipped"]
    logger.info(
        "Workflow definition sync complete",
        extra={
            "synced": result["synced"],
            "updated": result["updated"],
            "skipped": result["skipped"],
            "orphaned": result["orphaned"],
            "total": total,
        },
    )

    return result
