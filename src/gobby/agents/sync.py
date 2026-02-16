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
                # Compare full serialized definitions to detect any change
                existing_def = manager.export_to_definition(existing.id)
                existing_json = existing_def.model_dump_json(exclude_none=False)
                new_json = agent_def.model_dump_json(exclude_none=False)
                needs_update = existing_json != new_json or existing.source_path != source_path

                if needs_update:
                    # Atomic in-place update via manager.update() — avoids
                    # the non-atomic delete-then-import pattern that could
                    # lose the definition if import fails.
                    try:
                        workflows_dict = None
                        if agent_def.workflows:
                            workflows_dict = {
                                wf_name: spec.model_dump(exclude_none=True)
                                for wf_name, spec in agent_def.workflows.items()
                            }
                        sandbox_dict = agent_def.sandbox.model_dump() if agent_def.sandbox else None
                        skill_dict = (
                            agent_def.skill_profile.model_dump()
                            if agent_def.skill_profile
                            else None
                        )

                        manager.update(
                            existing.id,
                            description=agent_def.description,
                            role=agent_def.role,
                            goal=agent_def.goal,
                            personality=agent_def.personality,
                            instructions=agent_def.instructions,
                            provider=agent_def.provider,
                            model=agent_def.model,
                            mode=agent_def.mode,
                            terminal=agent_def.terminal,
                            isolation=agent_def.isolation,
                            base_branch=agent_def.base_branch,
                            timeout=agent_def.timeout,
                            max_turns=agent_def.max_turns,
                            default_workflow=agent_def.default_workflow,
                            sandbox_config=sandbox_dict,
                            skill_profile=skill_dict,
                            workflows=workflows_dict,
                            lifecycle_variables=agent_def.lifecycle_variables or None,
                            default_variables=agent_def.default_variables or None,
                            source_path=source_path,
                        )
                        logger.info(f"Updated bundled agent definition: {name}")
                        result["updated"] += 1
                    except Exception as e:
                        logger.error(f"Failed to update bundled agent '{name}': {e}")
                        result["errors"].append(f"Failed to update '{name}': {e}")
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
