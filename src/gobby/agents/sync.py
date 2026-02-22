"""Agent definition synchronization for bundled agents.

This module provides sync_bundled_agents() which loads agent definitions from the
bundled install/shared/agents/ directory and syncs them to workflow_definitions
with workflow_type='agent'.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from gobby.storage.database import DatabaseProtocol
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import AgentDefinitionBody

__all__ = ["get_bundled_agents_path", "sync_bundled_agents"]

logger = logging.getLogger(__name__)


def get_bundled_agents_path() -> Path:
    """Get the path to bundled agents directory.

    Returns:
        Path to src/gobby/install/shared/agents/
    """
    from gobby.paths import get_install_dir

    return get_install_dir() / "shared" / "agents"


def _agent_def_to_body(agent_def: Any) -> AgentDefinitionBody:
    """Convert a full AgentDefinition to simplified AgentDefinitionBody.

    Composes role/goal/personality/instructions into a single instructions field.
    Drops fields not in the simplified model (sandbox, workflows, etc.).
    """
    # Compose instructions from structured fields
    if agent_def.role or agent_def.goal or agent_def.personality:
        composed = agent_def.build_prompt_preamble()
    else:
        composed = agent_def.instructions

    # Map mode ("self" not valid in AgentDefinitionBody)
    mode = agent_def.mode
    if mode == "self":
        mode = "headless"

    return AgentDefinitionBody(
        name=agent_def.name,
        description=agent_def.description,
        instructions=composed,
        provider=agent_def.provider,
        model=agent_def.model,
        mode=mode,
        isolation=agent_def.isolation,
        base_branch=agent_def.base_branch,
        timeout=agent_def.timeout,
        max_turns=agent_def.max_turns,
    )


def sync_bundled_agents(db: DatabaseProtocol) -> dict[str, Any]:
    """Sync bundled agent definitions from install/shared/agents/ to workflow_definitions.

    This function:
    1. Walks all .yaml files in the bundled agents directory
    2. Parses each into an AgentDefinition (for validation)
    3. Converts to AgentDefinitionBody (12-field simplified model)
    4. Creates new records or updates changed content (idempotent)
    5. All records are stored with workflow_type='agent' and source='bundled'

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

    manager = LocalWorkflowDefinitionManager(db)

    for yaml_file in sorted(agents_path.glob("*.yaml")):
        try:
            raw_content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(raw_content)

            if not isinstance(data, dict):
                logger.warning(f"Skipping non-dict YAML file: {yaml_file}")
                continue

            name = data.get("name", yaml_file.stem)
            data["name"] = name

            # Parse into AgentDefinition to validate
            agent_def = AgentDefinition(**data)

            # Convert to simplified body
            body = _agent_def_to_body(agent_def)
            body_json = body.model_dump_json()

            # Check if agent already exists in workflow_definitions
            existing = manager.get_by_name(name, include_deleted=True)

            if existing is not None and existing.workflow_type != "agent":
                # Name collision with a non-agent workflow — skip
                logger.debug(
                    f"Agent '{name}' conflicts with existing {existing.workflow_type} "
                    f"definition, skipping"
                )
                result["skipped"] += 1
                continue

            if existing is not None and existing.workflow_type == "agent":
                # If user soft-deleted it, respect their intent — skip sync
                if existing.deleted_at is not None:
                    logger.debug(f"Agent definition '{name}' is soft-deleted, skipping sync")
                    result["skipped"] += 1
                    continue

                # Compare definition_json to detect changes
                needs_update = existing.definition_json != body_json

                if needs_update:
                    try:
                        manager.update(
                            existing.id,
                            definition_json=body_json,
                            description=body.description,
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

            # Create the agent definition in workflow_definitions
            manager.create(
                name=name,
                definition_json=body_json,
                workflow_type="agent",
                description=body.description,
                source="bundled",
                enabled=body.enabled,
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
