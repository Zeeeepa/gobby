"""Session response helper functions.

Standalone functions (not methods) that build session-start responses.
They accept the handler instance as the first ``handler`` parameter.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.hooks.events import HookResponse

if TYPE_CHECKING:
    from gobby.hooks.event_handlers._base import EventHandlersBase
    from gobby.hooks.event_handlers._session_start import AgentActivationResult
    from gobby.storage.session_models import Session

_logger = logging.getLogger(__name__)


def get_claimed_task_info(
    handler: EventHandlersBase,
    session_id: str | None,
    project_id: str | None,
) -> list[tuple[str, str, str]] | None:
    """Fetch claimed task details from session variables.

    Reads the ``claimed_tasks`` session variable (a dict of task UUIDs)
    and resolves each to its current ref, status, and title.

    Best-effort: returns None on any failure (mocked DB, missing tables, etc.)

    Returns:
        List of (ref, status, title) tuples, or None if no claimed tasks.
    """
    if not session_id or not handler._session_storage or not handler._task_manager:
        return None

    try:
        from gobby.workflows.state_manager import SessionVariableManager

        sv_mgr = SessionVariableManager(handler._session_storage.db)
        session_vars = sv_mgr.get_variables(session_id)
    except Exception:
        return None

    if not session_vars.get("task_claimed") or not session_vars.get("claimed_tasks"):
        # DB fallback: check for tasks still assigned to this session
        try:
            db_tasks = handler._task_manager.list_tasks(
                assignee=session_id,
                status="in_progress",
                project_id=project_id,
            )
            if db_tasks:
                reconciled = {}
                db_result: list[tuple[str, str, str]] = []
                for task in db_tasks:
                    ref = f"#{task.seq_num}" if task.seq_num else task.id[:8]
                    reconciled[task.id] = ref
                    db_result.append((ref, task.status, task.title))
                # Reconcile session variables with DB state
                sv_mgr.set_variable(session_id, "task_claimed", True)
                sv_mgr.set_variable(session_id, "claimed_tasks", reconciled)
                return db_result or None
        except Exception:
            pass
        return None

    claimed_tasks: dict[str, Any] = session_vars["claimed_tasks"]
    if not claimed_tasks:
        return None

    result: list[tuple[str, str, str]] = []
    for task_uuid in claimed_tasks:
        try:
            task = handler._task_manager.get_task(task_uuid, project_id=project_id)
            ref = f"#{task.seq_num}" if task.seq_num else task_uuid[:8]
            result.append((ref, task.status, task.title))
        except Exception as e:
            _logger.debug("Failed to fetch task %s: %s", task_uuid[:8], e)
            result.append((task_uuid[:8], "unknown", "(deleted)"))
    return result or None


def build_claimed_task_context(
    handler: EventHandlersBase,
    session_id: str,
    project_id: str | None,
) -> str | None:
    """Build additional_context string for claimed tasks.

    Returns a formatted context block listing all tasks claimed by this
    session, or None if there are no claimed tasks.
    """
    info = get_claimed_task_info(handler, session_id, project_id)
    if not info:
        return None

    lines = ["\n## Claimed Tasks (Persisted)\n"]
    lines.append(
        "You have claimed the following tasks from a previous context. "
        "These tasks are still assigned to you.\n"
    )
    for ref, status, title in info:
        lines.append(f"- {ref} [{status}] {title}")
    return "\n".join(lines)


def compose_session_response(
    handler: EventHandlersBase,
    session: Session | None,
    session_id: str | None,
    external_id: str,
    parent_session_id: str | None,
    machine_id: str,
    project_id: str | None = None,
    task_id: str | None = None,
    additional_context: list[str] | None = None,
    is_pre_created: bool = False,
    terminal_context: dict[str, Any] | None = None,
    agent_info: AgentActivationResult | None = None,
    session_source: str | None = None,
    claimed_tasks_info: list[tuple[str, str, str]] | None = None,
) -> HookResponse:
    """Build HookResponse for session start.

    Shared helper that builds the system message, context, and metadata
    for both pre-created and newly-created sessions.

    Args:
        handler: The event handler mixin instance
        session: Session object (used for seq_num)
        session_id: Session ID
        external_id: External (CLI-native) session ID
        parent_session_id: Parent session ID if any
        machine_id: Machine ID
        project_id: Project ID
        task_id: Task ID if any
        additional_context: Additional context strings to append (e.g., task/skill context)
        is_pre_created: Whether this is a pre-created session
        terminal_context: Terminal context dict to add to metadata
        session_source: Session source (e.g., "clear", "compact", "startup") for handoff indicator
        claimed_tasks_info: Pre-fetched claimed task info from get_claimed_task_info()

    Returns:
        HookResponse with system_message, context, and metadata
    """
    # Build context_parts
    context_parts: list[str] = []
    if parent_session_id:
        context_parts.append(f"Parent session: {parent_session_id}")
    if additional_context:
        context_parts.extend(additional_context)

    # Compute session_ref from session object or fallback to session_id
    session_ref = session_id
    if session and session.seq_num:
        session_ref = f"#{session.seq_num}"

    # Build system message (terminal display)
    # Session ID: prefer #N, fallback to UUID only when no seq_num
    system_message = f"\nGobby Session ID: {session_ref}"
    system_message += " <- Use this for MCP tool calls (session_id parameter)"

    # Parent Session ID (before External ID, with handoff indicator)
    if parent_session_id and handler._session_storage:
        try:
            parent = handler._session_storage.get(parent_session_id)
            if parent:
                parent_ref = f"#{parent.seq_num}" if parent.seq_num else parent_session_id
                # Handoff indicator based on session_source
                indicator = ""
                if session_source in ("clear", "compact"):
                    indicator = " (Handoff)" if parent.summary_markdown else " (No Handoff)"
                system_message += f"\nParent Session ID: {parent_ref}{indicator}"
            else:
                system_message += f"\nParent Session ID: {parent_session_id}"
        except Exception:
            system_message += f"\nParent Session ID: {parent_session_id}"

    system_message += f"\nExternal ID: {external_id} (CLI-native, rarely needed)"

    # Agent info (only if agent loaded -- absence signals activation failure)
    if agent_info:
        # Agent name only -- description moves to tree node
        system_message += f"\nAgent: {agent_info.agent_name}"

        # Build tree nodes: description, role, goal, task, rules, variables, skills
        tree_nodes: list[str] = []
        if agent_info.description:
            tree_nodes.append(f"Description: {agent_info.description.strip()}")
        if agent_info.role:
            tree_nodes.append(f"Role: {agent_info.role.strip()}")
        if agent_info.goal:
            tree_nodes.append(f"Goal: {agent_info.goal.strip()}")
        # Current task (inside agent tree, with claimed/assigned indicator)
        if task_id and handler._task_manager:
            try:
                task = handler._task_manager.get_task(task_id, project_id=project_id)
                task_ref = f"#{task.seq_num}" if task and task.seq_num else task_id
            except Exception:
                task_ref = task_id
            claim_status = "assigned" if parent_session_id else "claimed"
            tree_nodes.append(f"Current Task: {task_ref} ({claim_status})")
        tree_nodes.append(f"Rules: {agent_info.rules_count}")
        tree_nodes.append(f"Variables: {agent_info.variables_count}")
        # Skills is always last (may have sub-node)
        skills_label = f"Skills: {agent_info.skills_count}"

        for node in tree_nodes:
            system_message += f"\n\u251c\u2500 {node}"
        if agent_info.injected_skill_names:
            system_message += f"\n\u2514\u2500 {skills_label}"
            system_message += (
                f"\n   \u2514\u2500 Injected: {', '.join(agent_info.injected_skill_names)}"
            )
        else:
            system_message += f"\n\u2514\u2500 {skills_label}"

    # Claimed tasks (sibling section after agent tree)
    if claimed_tasks_info:
        system_message += f"\nClaimed Tasks: {len(claimed_tasks_info)}"
        for i, (ref, status, title) in enumerate(claimed_tasks_info):
            connector = "\u2514\u2500" if i == len(claimed_tasks_info) - 1 else "\u251c\u2500"
            system_message += f"\n{connector} {ref} [{status}] {title}"

    # Build metadata
    metadata: dict[str, Any] = {
        "session_id": session_id,
        "session_ref": session_ref,
        "parent_session_id": parent_session_id,
        "machine_id": machine_id,
        "project_id": project_id,
        "external_id": external_id,
        "task_id": task_id,
    }
    if is_pre_created:
        metadata["is_pre_created"] = True
    if terminal_context:
        # Only include non-null terminal values
        for key, value in terminal_context.items():
            if value is not None:
                metadata[f"terminal_{key}"] = value

    final_context = "\n".join(context_parts) if context_parts else None

    response = HookResponse(
        decision="allow",
        context=final_context,
        system_message=system_message,
        metadata=metadata,
    )
    handler._apply_debug_echo(response)
    return response
