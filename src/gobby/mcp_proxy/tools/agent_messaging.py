"""Inter-agent messaging and command tools for the gobby-agents MCP server.

Provides P2P messaging and command coordination between sessions:
- send_message: P2P messaging with same-project validation
- send_command: Ancestor sends command to descendant
- complete_command: Descendant completes command, clears state, sends result
- deliver_pending_messages: Fetch and mark undelivered messages
- activate_command: Activate a pending command, set session variables
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.mcp_proxy.tools.internal import InternalToolRegistry
    from gobby.storage.agent_commands import AgentCommandManager
    from gobby.storage.database import DatabaseProtocol
    from gobby.storage.inter_session_messages import InterSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager
    from gobby.workflows.state_manager import SessionVariableManager

logger = logging.getLogger(__name__)


def add_messaging_tools(
    registry: InternalToolRegistry,
    message_manager: InterSessionMessageManager,
    session_manager: LocalSessionManager,
    command_manager: AgentCommandManager,
    session_var_manager: SessionVariableManager,
    db: DatabaseProtocol,
) -> None:
    """Add inter-agent messaging and command tools to a registry.

    Args:
        registry: The InternalToolRegistry to add tools to
        message_manager: For persisting inter-session messages
        session_manager: For resolving session relationships
        command_manager: For managing agent commands
        session_var_manager: For setting/clearing session variables
        db: Database for direct queries (agent_runs)
    """

    def _resolve(ref: str) -> str:
        """Resolve session reference to UUID."""
        from gobby.utils.project_context import get_project_context

        ctx = get_project_context()
        project_id = ctx.get("id") if ctx else None
        return session_manager.resolve_session_reference(ref, project_id)

    # ── send_message ───────────────────────────────────────────────

    @registry.tool(
        name="send_message",
        description=(
            "Send a P2P message between sessions. Validates both sessions "
            "are in the same project. Auto-writes to agent_runs.result when "
            "sending to parent."
        ),
    )
    async def send_message(
        from_session: str,
        to_session: str,
        content: str,
        priority: str = "normal",
    ) -> dict[str, Any]:
        try:
            from_id = _resolve(from_session)
            to_id = _resolve(to_session)

            from_sess = session_manager.get(from_id)
            if not from_sess:
                return {"success": False, "error": f"Session not found: {from_id}"}

            to_sess = session_manager.get(to_id)
            if not to_sess:
                return {"success": False, "error": f"Session not found: {to_id}"}

            # Validate same project
            if from_sess.project_id != to_sess.project_id:
                return {
                    "success": False,
                    "error": (
                        f"Cross-project messaging not allowed. "
                        f"Sender project: {from_sess.project_id}, "
                        f"recipient project: {to_sess.project_id}"
                    ),
                }

            msg = message_manager.create_message(
                from_session=from_id,
                to_session=to_id,
                content=content,
                priority=priority,
            )

            # Auto-write to agent_runs.result when sending to parent
            if from_sess.parent_session_id == to_id:
                try:
                    row = db.fetchone(
                        "SELECT id FROM agent_runs WHERE child_session_id = ? "
                        "ORDER BY created_at DESC LIMIT 1",
                        (from_id,),
                    )
                    if row:
                        now = datetime.now(UTC).isoformat()
                        db.execute(
                            "UPDATE agent_runs SET result = ?, updated_at = ? WHERE id = ?",
                            (content, now, row["id"]),
                        )
                except Exception as e:
                    logger.warning("Failed to write to agent_runs.result: %s", e)

            return {"success": True, "message": msg.to_dict()}

        except Exception as e:
            logger.error("send_message failed: %s", e)
            return {"success": False, "error": str(e)}

    # ── send_command ───────────────────────────────────────────────

    @registry.tool(
        name="send_command",
        description=(
            "Send a command from an ancestor session to a descendant. "
            "Validates ancestry and rejects if the target already has an active command."
        ),
    )
    async def send_command(
        from_session: str,
        to_session: str,
        command_text: str,
        allowed_tools: list[str] | None = None,
        allowed_mcp_tools: list[str] | None = None,
        exit_condition: str | None = None,
    ) -> dict[str, Any]:
        try:
            from_id = _resolve(from_session)
            to_id = _resolve(to_session)

            # Validate ancestor relationship
            if not session_manager.is_ancestor(ancestor_id=from_id, descendant_id=to_id):
                return {
                    "success": False,
                    "error": f"Session {from_id} is not an ancestor of {to_id}",
                }

            # Reject if active command exists
            active = [
                c for c in command_manager.list_commands(to_session=to_id)
                if c.status in ("pending", "running")
            ]
            if active:
                return {
                    "success": False,
                    "error": (
                        f"Session {to_id} already has an active command: "
                        f"{active[0].id} (status={active[0].status})"
                    ),
                }

            cmd = command_manager.create_command(
                from_session=from_id,
                to_session=to_id,
                command_text=command_text,
                allowed_tools=allowed_tools,
                allowed_mcp_tools=allowed_mcp_tools,
                exit_condition=exit_condition,
            )

            return {"success": True, "command": cmd.to_dict()}

        except Exception as e:
            logger.error("send_command failed: %s", e)
            return {"success": False, "error": str(e)}

    # ── complete_command ───────────────────────────────────────────

    @registry.tool(
        name="complete_command",
        description=(
            "Complete a command: mark it done, clear session variables, "
            "and send the result back to the commanding session."
        ),
    )
    async def complete_command(
        session_id: str,
        command_id: str,
        result: str,
    ) -> dict[str, Any]:
        try:
            resolved_id = _resolve(session_id)
            cmd = command_manager.get_command(command_id)
            if not cmd:
                return {"success": False, "error": f"Command not found: {command_id}"}

            if cmd.to_session != resolved_id:
                return {
                    "success": False,
                    "error": f"Command not assigned to session {resolved_id}",
                }

            # Mark completed
            command_manager.update_status(command_id, "completed")

            # Clear session variables
            session_var_manager.delete_variables(resolved_id)

            # Send result to commanding session
            message_manager.create_message(
                from_session=resolved_id,
                to_session=cmd.from_session,
                content=result,
                priority="normal",
                message_type="command_result",
            )

            return {"success": True, "command_id": command_id, "status": "completed"}

        except Exception as e:
            logger.error("complete_command failed: %s", e)
            return {"success": False, "error": str(e)}

    # ── deliver_pending_messages ───────────────────────────────────

    @registry.tool(
        name="deliver_pending_messages",
        description=(
            "Fetch undelivered messages for a session and mark them as delivered. "
            "Use this to inject pending messages as context."
        ),
    )
    async def deliver_pending_messages(
        session_id: str,
    ) -> dict[str, Any]:
        try:
            resolved_id = _resolve(session_id)
            undelivered = message_manager.get_undelivered_messages(resolved_id)

            messages = []
            for msg in undelivered:
                message_manager.mark_delivered(msg.id)
                messages.append(msg.to_dict())

            return {
                "success": True,
                "messages": messages,
                "count": len(messages),
            }

        except Exception as e:
            logger.error("deliver_pending_messages failed: %s", e)
            return {"success": False, "error": str(e)}

    # ── activate_command ──────────────────────────────────────────

    @registry.tool(
        name="activate_command",
        description=(
            "Activate a pending command: mark it running and set session "
            "variables (command_id, command_text, allowed_tools, exit_condition)."
        ),
    )
    async def activate_command(
        session_id: str,
        command_id: str,
    ) -> dict[str, Any]:
        try:
            resolved_id = _resolve(session_id)
            cmd = command_manager.get_command(command_id)
            if not cmd:
                return {"success": False, "error": f"Command not found: {command_id}"}

            if cmd.to_session != resolved_id:
                return {
                    "success": False,
                    "error": f"Command not assigned to session {resolved_id}",
                }

            # Mark running
            command_manager.update_status(command_id, "running")

            # Set session variables from command fields
            import json as _json

            variables: dict[str, Any] = {
                "command_id": cmd.id,
                "command_text": cmd.command_text,
            }
            if cmd.allowed_tools:
                try:
                    variables["allowed_tools"] = _json.loads(cmd.allowed_tools)
                except (ValueError, TypeError):
                    variables["allowed_tools"] = cmd.allowed_tools
            if cmd.allowed_mcp_tools:
                try:
                    variables["allowed_mcp_tools"] = _json.loads(cmd.allowed_mcp_tools)
                except (ValueError, TypeError):
                    variables["allowed_mcp_tools"] = cmd.allowed_mcp_tools
            if cmd.exit_condition:
                variables["exit_condition"] = cmd.exit_condition

            session_var_manager.merge_variables(resolved_id, variables)

            return {"success": True, "command": cmd.to_dict(), "variables_set": list(variables.keys())}

        except Exception as e:
            logger.error("activate_command failed: %s", e)
            return {"success": False, "error": str(e)}
