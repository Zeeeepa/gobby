"""Agent definition synchronization for bundled agents.

This module provides sync_bundled_agents() which loads agent definitions from the
bundled install/shared/agents/ directory and syncs them to the database.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from gobby.storage.agent_definitions import LocalAgentDefinitionManager
from gobby.storage.database import DatabaseProtocol

__all__ = ["get_bundled_agents_path", "sync_bundled_agents"]

logger = logging.getLogger(__name__)


def get_bundled_agents_path() -> Path:
    """Get the path to bundled agents directory.

    Returns:
        Path to src/gobby/install/shared/agents/
    """
    from gobby.paths import get_install_dir

    return get_install_dir() / "shared" / "agents"


def sync_bundled_agents(db: DatabaseProtocol) -> dict[str, Any]:
    """Sync bundled agent definitions from install/shared/agents/ to the database.

    This function:
    1. Walks all .yaml files in the bundled agents directory (skips deprecated/)
    2. Parses each into an AgentDefinition
    3. Creates new records or updates changed content (idempotent)
    4. All records are created with scope='bundled' and project_id=None

    Args:
        db: Database connection

    Returns:
        Dict with success status and counts
    """
    from gobby.agents.definitions import AgentDefinition

    agents_path = get_bundled_agents_path()

    result: dict[str, Any] = {
        "success": True,
        "synced": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
    }

    if not agents_path.exists():
        logger.warning(f"Bundled agents path not found: {agents_path}")
        result["errors"].append(f"Agents path not found: {agents_path}")
        return result

    # dev_mode=True so we can update bundled records during sync
    manager = LocalAgentDefinitionManager(db, dev_mode=True)

    for yaml_file in sorted(agents_path.glob("*.yaml")):
        # Skip deprecated directory contents
        if "deprecated" in yaml_file.parts:
            continue

        try:
            raw_content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(raw_content)

            if not isinstance(data, dict):
                logger.warning(f"Skipping non-dict YAML file: {yaml_file}")
                continue

            name = data.get("name", yaml_file.stem)
            data["name"] = name
            source_path = str(yaml_file)

            # Parse into AgentDefinition to validate
            agent_def = AgentDefinition(**data)

            # Check if agent already exists (bundled scope)
            existing = manager.get_bundled(name)

            if existing is not None:
                # Compare key fields to detect stale content
                existing_def = manager.export_to_definition(existing.id)
                needs_update = (
                    existing_def.description != agent_def.description
                    or existing_def.role != agent_def.role
                    or existing_def.goal != agent_def.goal
                    or existing_def.personality != agent_def.personality
                    or existing_def.instructions != agent_def.instructions
                    or existing_def.provider != agent_def.provider
                    or existing_def.mode != agent_def.mode
                    or existing_def.model != agent_def.model
                    or existing_def.default_workflow != agent_def.default_workflow
                    or existing.source_path != source_path
                )

                if needs_update:
                    # Re-import by deleting and recreating
                    manager.delete(existing.id)
                    manager.import_from_definition(
                        agent_def,
                        scope="bundled",
                        source_path=source_path,
                        project_id=None,
                    )
                    logger.info(f"Updated bundled agent definition: {name}")
                    result["updated"] += 1
                else:
                    logger.debug(f"Agent definition '{name}' already up to date, skipping")
                    result["skipped"] += 1
                continue

            # Create the agent definition in the database
            manager.import_from_definition(
                agent_def,
                scope="bundled",
                source_path=source_path,
                project_id=None,
            )
            logger.info(f"Synced bundled agent definition: {name}")
            result["synced"] += 1

        except Exception as e:
            error_msg = f"Failed to sync agent definition '{yaml_file}': {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

    total = result["synced"] + result["updated"] + result["skipped"]
    logger.info(
        f"Agent definition sync complete: {result['synced']} synced, "
        f"{result['updated']} updated, {result['skipped']} skipped, {total} total"
    )

    return result
