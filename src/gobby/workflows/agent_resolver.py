import json
import logging

from pydantic import ValidationError

from gobby.storage.database import DatabaseProtocol
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import AgentDefinitionBody

logger = logging.getLogger(__name__)


class AgentResolutionError(Exception):
    """Raised when an agent definition cannot be found or parsed."""


def resolve_agent(
    name: str,
    db: DatabaseProtocol,
    cli_source: str | None = None,
    project_id: str | None = None,
) -> AgentDefinitionBody | None:
    """Resolve an agent by name via direct DB lookup.

    - Looks up agent by name in workflow_definitions
    - Resolves 'inherit' provider from `cli_source`
    - Returns None if agent not found (except 'default' which returns Pydantic defaults)
    """
    manager = LocalWorkflowDefinitionManager(db)

    row = manager.get_by_name(name, project_id=project_id)
    if not row or row.workflow_type != "agent" or not row.definition_json:
        if name == "default":
            return AgentDefinitionBody(name="default", mode="inherit")
        return None

    try:
        data = json.loads(row.definition_json)
        if "name" not in data:
            data["name"] = row.name
        body = AgentDefinitionBody(**data)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.debug(f"Failed to parse agent definition for {name}: {e}")
        return None

    # Resolve 'inherit' provider — source IS the provider (bare: claude, gemini, codex)
    if body.provider == "inherit":
        if cli_source:
            body.provider = cli_source
        else:
            body.provider = "claude"

    return body
