"""Apply agent persona to a session.

Shared logic for applying an agent definition's persona (rules, skills,
variables, step workflows, tool restrictions) to a session. Used by:

- The ``apply_persona`` MCP tool (direct invocation by agents/users)
- The SessionStart hook (automatic activation on session creation)

This module does NOT spawn a process or create a child session.  It
configures an *existing* session to behave as a given agent definition.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from gobby.storage.database import DatabaseProtocol
from gobby.workflows.definitions import AgentDefinitionBody

logger = logging.getLogger(__name__)


def build_persona_changes(
    agent_body: AgentDefinitionBody,
    session_id: str,
    db: DatabaseProtocol,
    *,
    enabled_rules: list[Any] | None = None,
    all_skills: list[Any] | None = None,
    enabled_variables: list[Any] | None = None,
    is_spawned: bool = False,
) -> tuple[dict[str, Any], set[str], set[str] | None]:
    """Compute session variable changes for an agent persona.

    Merges rule/skill/variable selectors from the agent definition against
    the enabled definitions in the database to produce the full set of
    session variables needed to configure the session.

    Args:
        agent_body: Resolved agent definition.
        session_id: Target session ID.
        db: Database handle for loading rules/skills/variables when not
            provided via the explicit parameters.
        enabled_rules: Pre-loaded enabled rule rows.  When ``None``, loaded
            from the database.
        all_skills: Pre-loaded skill list.  When ``None``, loaded from DB.
        enabled_variables: Pre-loaded enabled variable rows.  When ``None``,
            loaded from the database.
        is_spawned: Whether this session was created by spawn_agent (sets
            the ``is_spawned_agent`` variable).

    Returns:
        ``(changes, active_rule_names, active_skill_names)`` where
        *changes* is a dict ready for
        :meth:`SessionVariableManager.merge_variables`.
    """
    from gobby.skills.manager import SkillManager
    from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
    from gobby.workflows.selectors import (
        resolve_rules_for_agent,
        resolve_skills_for_agent,
        resolve_variables_for_agent,
    )

    # Load from DB when callers don't supply pre-fetched rows
    if enabled_rules is None:
        def_manager = LocalWorkflowDefinitionManager(db)
        enabled_rules = def_manager.list_all(workflow_type="rule", enabled=True)

    if all_skills is None:
        skill_mgr = SkillManager(db)
        all_skills = skill_mgr.list_skills()

    if enabled_variables is None:
        def_manager = LocalWorkflowDefinitionManager(db)
        enabled_variables = def_manager.list_all(workflow_type="variable", enabled=True)

    # --- Rule resolution ---
    active_rules = resolve_rules_for_agent(agent_body, enabled_rules)

    changes: dict[str, Any] = {
        "_agent_type": agent_body.name,
        "_active_rule_names": list(active_rules),
        "is_spawned_agent": is_spawned,
    }

    # --- Skill resolution ---
    active_skills = resolve_skills_for_agent(agent_body, all_skills)
    if active_skills is not None:
        changes["_active_skill_names"] = list(active_skills)

    if agent_body.workflows and agent_body.workflows.skill_format:
        changes["_skill_format"] = agent_body.workflows.skill_format

    # --- Agent-defined variables ---
    if agent_body.workflows and agent_body.workflows.variables:
        for key, value in agent_body.workflows.variables.items():
            if key.startswith("_"):
                logger.warning(f"Skipping reserved variable {key!r} from agent definition")
                continue
            changes[key] = value

    # --- DB-level variable definitions ---
    active_variable_names = resolve_variables_for_agent(agent_body, enabled_variables)
    for var_row in enabled_variables:
        if active_variable_names is None or var_row.name in active_variable_names:
            try:
                var_body = json.loads(var_row.definition_json)
                if var_row.name not in changes:
                    changes[var_row.name] = var_body.get("value")
            except json.JSONDecodeError:
                logger.debug(f"Failed to parse variable definition for {var_row.name}")

    # --- Agent-level tool restrictions ---
    if agent_body.blocked_tools:
        changes["_agent_blocked_tools"] = agent_body.blocked_tools
    if agent_body.blocked_mcp_tools:
        changes["_agent_blocked_mcp_tools"] = agent_body.blocked_mcp_tools

    # --- Step workflow instance ---
    if agent_body.steps:
        from gobby.workflows.definitions import WorkflowInstance
        from gobby.workflows.state_manager import WorkflowInstanceManager

        step_wf_name = f"{agent_body.name}-steps"
        step_instance = WorkflowInstance(
            id=str(uuid.uuid4()),
            session_id=session_id,
            workflow_name=step_wf_name,
            enabled=True,
            priority=10,
            current_step=agent_body.steps[0].name,
            variables=dict(agent_body.step_variables),
        )
        WorkflowInstanceManager(db).save_instance(step_instance)
        changes["_step_workflow_name"] = step_wf_name
        changes["step_workflow_complete"] = False
        logger.info(
            f"Created step workflow instance {step_wf_name} for session {session_id} "
            f"(agent={agent_body.name}, step={agent_body.steps[0].name})",
        )

    return changes, active_rules, active_skills


async def apply_persona_impl(
    agent: str,
    db: DatabaseProtocol | None = None,
    session_id: str | None = None,
    variables: dict[str, Any] | None = None,
    task_id: str | None = None,
    task_manager: Any | None = None,
    cli_source: str | None = None,
) -> dict[str, Any]:
    """Apply an agent definition's persona to a session.

    This is the implementation behind the ``apply_persona`` MCP tool.
    It resolves the agent definition, builds session variable changes,
    and writes them.

    Args:
        agent: Agent definition name to apply.
        db: Database handle.
        session_id: Target session ID.  When ``None``, attempts to read
            from the session context ContextVar.
        variables: Additional variables to merge after persona changes.
        task_id: Optional task to bind to the session.
        task_manager: Task manager for resolving task references.
        cli_source: CLI source hint for provider resolution.

    Returns:
        Dict with success status and activation details.
    """
    if db is None:
        return {"success": False, "error": "Database not available"}

    # Resolve session ID from ContextVar if not provided
    if session_id is None:
        from gobby.utils.session_context import get_session_context

        ctx = get_session_context()
        session_id = ctx.session_id if ctx else None

    if not session_id:
        return {"success": False, "error": "No session context — cannot apply persona"}

    # Resolve agent definition
    from gobby.workflows.agent_resolver import resolve_agent

    agent_body = resolve_agent(agent, db, cli_source=cli_source)
    if agent_body is None:
        return {
            "success": False,
            "error": f"Agent definition '{agent}' not found",
        }

    # Resolve task binding
    extra_vars: dict[str, Any] = {}
    if task_id and task_manager:
        try:
            from gobby.utils.project_context import get_project_context

            ctx = get_project_context()
            project_id = ctx.get("id") if ctx else None
            if project_id:
                from gobby.mcp_proxy.tools.spawn_agent._implementation import (
                    resolve_task_id_for_mcp,
                )

                resolved_id = resolve_task_id_for_mcp(task_manager, task_id, project_id)
                task = task_manager.get_task(resolved_id)
                if task:
                    task_ref = f"#{task.seq_num}" if task.seq_num else resolved_id
                    extra_vars["assigned_task_id"] = task_ref
                    extra_vars["session_task"] = task_ref
        except Exception as e:
            logger.warning(f"Failed to resolve task_id {task_id}: {e}")

    # Build changes
    changes, active_rules, active_skills = build_persona_changes(
        agent_body=agent_body,
        session_id=session_id,
        db=db,
        is_spawned=False,
    )

    # Merge extra variables (task binding, caller-provided)
    changes.update(extra_vars)
    if variables:
        changes.update(variables)

    # Write to session
    from gobby.workflows.state_manager import SessionVariableManager

    SessionVariableManager(db).merge_variables(session_id, changes)

    return {
        "success": True,
        "mode": "persona",
        "persona_applied": agent_body.name,
        "has_steps": bool(agent_body.steps),
        "active_rules": len(active_rules),
        "active_skills": len(active_skills) if active_skills is not None else "all",
        "message": f"Agent persona '{agent_body.name}' applied to session {session_id}",
    }
