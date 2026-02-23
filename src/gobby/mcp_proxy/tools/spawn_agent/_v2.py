"""Simplified agent spawning via workflow_definitions lookup.

Loads agent definitions from workflow_definitions (workflow_type='agent')
instead of the legacy agent_definitions table. Sets _agent_type for
rule-based behavior enforcement.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import AgentDefinitionBody

from ._implementation import spawn_agent_impl

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


def load_agent_definition_body(
    name: str,
    db: DatabaseProtocol,
    project_id: str | None = None,
) -> AgentDefinitionBody | None:
    """Load an agent definition from workflow_definitions.

    Args:
        name: Agent name to look up.
        db: Database connection.
        project_id: Optional project ID for scoped lookup.

    Returns:
        AgentDefinitionBody if found with workflow_type='agent', None otherwise.
    """
    manager = LocalWorkflowDefinitionManager(db)

    # Look up by name, filtering to workflow_type='agent'
    rows = manager.list_all(workflow_type="agent", project_id=project_id)
    for row in rows:
        if row.name == name:
            try:
                return AgentDefinitionBody.model_validate_json(row.definition_json)
            except Exception as e:
                logger.warning(f"Failed to parse agent definition '{name}': {e}")
                return None

    return None


def build_spawn_params(
    body: AgentDefinitionBody,
    prompt: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Build spawn parameters from an AgentDefinitionBody.

    Extracts provider, model, mode, isolation, etc. from the definition
    and prepends instructions to the prompt. Sets _agent_type and
    _agent_rules in step_variables for rule activation.

    Args:
        body: The agent definition body.
        prompt: The user prompt for the agent.
        task_id: Optional task ID to link.

    Returns:
        Dict of parameters ready for spawn_agent_impl.
    """
    # Prepend instructions to prompt if present
    effective_prompt = prompt
    if body.instructions:
        effective_prompt = f"## Instructions\n{body.instructions}\n\n---\n\n{prompt}"

    # Build step_variables for rule activation
    step_variables: dict[str, Any] = {
        "_agent_type": body.name,
    }
    if body.rules:
        step_variables["_agent_rules"] = body.rules

    return {
        "prompt": effective_prompt,
        "task_id": task_id,
        "provider": body.provider,
        "model": body.model,
        "mode": body.mode,
        "isolation": body.isolation,
        "base_branch": body.base_branch,
        "timeout": body.timeout,
        "max_turns": body.max_turns,
        "step_variables": step_variables,
    }


async def spawn_agent_simplified(
    agent_name: str,
    prompt: str,
    db: DatabaseProtocol,
    runner: AgentRunner,
    parent_session_id: str,
    task_id: str | None = None,
    project_id: str | None = None,
    **extra_kwargs: Any,
) -> dict[str, Any]:
    """Simplified agent spawn: (agent_name, prompt, task_id).

    Loads agent definition from workflow_definitions, builds params,
    and delegates to spawn_agent_impl.

    Args:
        agent_name: Name of the agent in workflow_definitions.
        prompt: What the agent should do.
        db: Database connection.
        runner: AgentRunner for executing agents.
        parent_session_id: Parent session ID.
        task_id: Optional task to link.
        project_id: Optional project ID for scoped lookup.
        **extra_kwargs: Additional kwargs passed to spawn_agent_impl.

    Returns:
        Dict with success status and spawn details.
    """
    body = load_agent_definition_body(agent_name, db, project_id)
    if body is None:
        return {
            "success": False,
            "error": f"Agent '{agent_name}' not found in workflow_definitions",
        }

    params = build_spawn_params(body, prompt, task_id)

    return await spawn_agent_impl(
        prompt=params["prompt"],
        runner=runner,
        agent_lookup_name=agent_name,
        task_id=params["task_id"],
        provider=params["provider"],
        model=params["model"],
        mode=params["mode"],
        isolation=params["isolation"],
        base_branch=params["base_branch"],
        timeout=params["timeout"],
        max_turns=params["max_turns"],
        parent_session_id=parent_session_id,
        **extra_kwargs,
    )
