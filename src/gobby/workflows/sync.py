"""Workflow definition synchronization for bundled workflows.

This module provides sync_bundled_workflows() which loads workflow definitions
from the bundled install/shared/workflows/ directory and syncs them to the database.
"""

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from gobby.storage.database import DatabaseProtocol
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager

__all__ = ["get_bundled_workflows_path", "sync_bundled_workflows"]

logger = logging.getLogger(__name__)


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
        logger.warning(f"Bundled workflows path not found: {workflows_path}")
        result["errors"].append(f"Workflows path not found: {workflows_path}")
        return result

    manager = LocalWorkflowDefinitionManager(db)

    for yaml_file in sorted(workflows_path.glob("*.yaml")):
        try:
            raw_content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(raw_content)

            if not isinstance(data, dict):
                logger.warning(f"Skipping non-dict YAML file: {yaml_file}")
                continue

            if "name" not in data:
                logger.warning(f"Skipping YAML without 'name' field: {yaml_file}")
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

            # Check if workflow already exists (global scope)
            existing = manager.get_by_name(name)

            if existing is not None:
                if existing.source == "bundled":
                    # Compare definition_json content to detect changes
                    if existing.definition_json == definition_json:
                        logger.debug(f"Workflow '{name}' already up to date, skipping")
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
                        logger.info(f"Updated bundled workflow definition: {name}")
                        result["updated"] += 1
                else:
                    # Non-bundled workflow with same name exists — don't overwrite
                    logger.debug(
                        f"Workflow '{name}' exists with source='{existing.source}', skipping"
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
            logger.info(f"Synced bundled workflow definition: {name}")
            result["synced"] += 1

        except Exception as e:
            error_msg = f"Failed to sync workflow definition '{yaml_file}': {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

    total = result["synced"] + result["updated"] + result["skipped"]
    logger.info(
        f"Workflow definition sync complete: {result['synced']} synced, "
        f"{result['updated']} updated, {result['skipped']} skipped, {total} total"
    )

    return result
