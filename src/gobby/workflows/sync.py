"""Workflow definition synchronization for bundled workflows.

This module provides sync_bundled_workflows() which loads workflow definitions
from the bundled install/shared/workflows/ directory and syncs them to the database.
"""

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from gobby.storage.database import DatabaseProtocol
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import PipelineDefinition, RuleDefinitionBody, WorkflowDefinition

__all__ = ["get_bundled_rules_path", "get_bundled_workflows_path", "sync_bundled_rules", "sync_bundled_workflows"]

logger = logging.getLogger(__name__)


def get_bundled_rules_path() -> Path:
    """Get the path to bundled rules directory.

    Returns:
        Path to src/gobby/install/shared/rules/
    """
    from gobby.paths import get_install_dir

    return get_install_dir() / "shared" / "rules"


def get_bundled_workflows_path() -> Path:
    """Get the path to bundled workflows directory.

    Returns:
        Path to src/gobby/install/shared/workflows/
    """
    from gobby.paths import get_install_dir

    return get_install_dir() / "shared" / "workflows"


def sync_bundled_workflows(db: DatabaseProtocol) -> dict[str, Any]:
    """Sync bundled workflow definitions from install/shared/workflows/ to the database.

    This function:
    1. Walks all .yaml files in the bundled workflows directory (skips deprecated/)
    2. Parses each and validates it has a 'name' field
    3. Creates new records or updates changed content (idempotent)
    4. All records are created with source='bundled' and project_id=None

    Args:
        db: Database connection

    Returns:
        Dict with success status and counts
    """
    workflows_path = get_bundled_workflows_path()

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
            definition_json = json.dumps(data)

            # Derive metadata from the YAML content
            yaml_type = data.get("type", "")
            workflow_type = "pipeline" if yaml_type == "pipeline" else "workflow"
            description = data.get("description", "")
            version = str(data.get("version", "1.0"))
            enabled = bool(data.get("enabled", False))
            priority = data.get("priority", 100)
            sources_list = data.get("sources")

            # Check if workflow already exists (global scope, including soft-deleted)
            existing = manager.get_by_name(name, include_deleted=True)

            if existing is not None:
                # If user soft-deleted it, respect their intent — skip sync
                if existing.deleted_at is not None:
                    logger.debug(
                        "Workflow is soft-deleted, skipping sync",
                        extra={"workflow": name},
                    )
                    result["skipped"] += 1
                    continue

                if existing.source == "bundled":
                    # Compare definition_json content to detect changes
                    if existing.definition_json == definition_json:
                        logger.debug(
                            "Workflow already up to date, skipping", extra={"workflow": name}
                        )
                        result["skipped"] += 1
                    else:
                        # Atomic in-place update (preserves id, avoids data loss)
                        manager.update(
                            existing.id,
                            name=name,
                            definition_json=definition_json,
                            workflow_type=workflow_type,
                            project_id=None,
                            description=description,
                            version=version,
                            enabled=enabled,
                            priority=priority,
                            sources=sources_list,
                            source="bundled",
                        )
                        logger.info("Updated bundled workflow definition", extra={"workflow": name})
                        result["updated"] += 1
                else:
                    # Non-bundled workflow with same name exists — don't overwrite
                    logger.debug(
                        "Workflow exists with non-bundled source, skipping",
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
                source="bundled",
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

    total = result["synced"] + result["updated"] + result["skipped"]
    logger.info(
        "Workflow definition sync complete",
        extra={
            "synced": result["synced"],
            "updated": result["updated"],
            "skipped": result["skipped"],
            "total": total,
        },
    )

    return result


def sync_bundled_rules(
    db: DatabaseProtocol, rules_path: Path | None = None
) -> dict[str, Any]:
    """Sync rule YAML files to workflow_definitions table with workflow_type='rule'.

    Rule YAML files use the new format with a top-level `rules:` dict where each
    entry defines a rule with `event` and `effect` fields. File-level fields
    (`group`, `tags`, `sources`) are inherited by all rules in the file.

    Args:
        db: Database connection.
        rules_path: Path to rules directory. Defaults to bundled rules path.

    Returns:
        Dict with success status and counts.
    """
    if rules_path is None:
        rules_path = get_bundled_rules_path()

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

    for yaml_file in sorted(rules_path.glob("*.yaml")):
        try:
            raw_content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(raw_content)

            if not isinstance(data, dict):
                logger.warning("Skipping non-dict YAML", extra={"file": str(yaml_file)})
                continue

            # Detect rule YAML format: must have 'rules' dict
            rules_dict = data.get("rules")
            if not isinstance(rules_dict, dict):
                logger.debug(
                    "No 'rules' key in YAML, skipping", extra={"file": str(yaml_file)}
                )
                result["skipped"] += 1
                continue

            # File-level defaults
            file_group = data.get("group")
            file_tags = data.get("tags")
            file_sources = data.get("sources")

            for rule_name, rule_data in rules_dict.items():
                if not isinstance(rule_data, dict):
                    result["errors"].append(
                        f"Rule '{rule_name}' in {yaml_file.name} is not a dict"
                    )
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

    total = result["synced"] + result["updated"] + result["skipped"]
    logger.info(
        "Rule definition sync complete",
        extra={
            "synced": result["synced"],
            "updated": result["updated"],
            "skipped": result["skipped"],
            "total": total,
        },
    )

    return result


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
        "effect": rule_data.get("effect"),
    }
    if rule_data.get("when"):
        body_dict["when"] = rule_data["when"]
    if rule_data.get("match"):
        body_dict["match"] = rule_data["match"]
    # Inherit group from file level, rule level overrides
    group = rule_data.get("group", file_group)
    if group:
        body_dict["group"] = group

    # Validate with Pydantic
    try:
        RuleDefinitionBody(**body_dict)
    except ValidationError as ve:
        raise ValueError(f"Invalid rule definition: {ve}") from ve

    definition_json = json.dumps(body_dict)
    priority = rule_data.get("priority", 100)
    description = rule_data.get("description")
    enabled = rule_data.get("enabled", True)

    # Check if rule already exists
    existing = manager.get_by_name(rule_name, include_deleted=True)

    if existing is not None:
        # Respect soft-delete
        if existing.deleted_at is not None:
            result["skipped"] += 1
            return

        if existing.source == "bundled":
            if existing.definition_json == definition_json:
                result["skipped"] += 1
            else:
                manager.update(
                    existing.id,
                    name=rule_name,
                    definition_json=definition_json,
                    workflow_type="rule",
                    project_id=None,
                    description=description,
                    enabled=enabled,
                    priority=priority,
                    sources=file_sources,
                    tags=file_tags,
                    source="bundled",
                )
                result["updated"] += 1
        else:
            result["skipped"] += 1
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
        source="bundled",
    )
    result["synced"] += 1
