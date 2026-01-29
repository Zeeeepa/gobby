"""
Inter-agent messaging tools for the gobby-agents MCP server.

Provides messaging capabilities between parent and child sessions:
- send_to_parent: Child sends message to its parent session
- send_to_child: Parent sends message to a specific child
- poll_messages: Check for incoming messages
- mark_message_read: Mark a message as read
- broadcast_to_children: Send message to all children (active in database)

These tools resolve session relationships from the database (LocalSessionManager),
which is the authoritative source for parent_session_id relationships.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.mcp_proxy.tools.internal import InternalToolRegistry
    from gobby.storage.inter_session_messages import InterSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager

logger = logging.getLogger(__name__)


def add_messaging_tools(
    registry: InternalToolRegistry,
    message_manager: InterSessionMessageManager,
    session_manager: LocalSessionManager,
) -> None:
    """
    Add inter-agent messaging tools to an existing registry.

    Args:
        registry: The InternalToolRegistry to add tools to (typically gobby-agents)
        message_manager: InterSessionMessageManager for persisting messages
        session_manager: LocalSessionManager for resolving parent/child relationships
            (database is the authoritative source for session relationships)
    """
    from gobby.utils.project_context import get_project_context

    def _resolve_session_id(ref: str) -> str:
        """Resolve session reference (#N, N, UUID, or prefix) to UUID."""
        project_ctx = get_project_context()
        project_id = project_ctx.get("id") if project_ctx else None
        return session_manager.resolve_session_reference(ref, project_id)

    @registry.tool(
        name="send_to_parent",
        description="Send a message from a child session to its parent session. Accepts #N, N, UUID, or prefix for session_id.",
    )
    async def send_to_parent(
        session_id: str,
        content: str,
        priority: str = "normal",
    ) -> dict[str, Any]:
        """
        Send a message to the parent session.

        Use this when a child agent needs to communicate status, results,
        or requests back to its parent session.

        Args:
            session_id: Session reference (accepts #N, N, UUID, or prefix) for the current (child) session
            content: Message content to send
            priority: Message priority ("normal" or "urgent")

        Returns:
            Dict with success status and message details
        """
        try:
            # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
            try:
                resolved_session_id = _resolve_session_id(session_id)
            except ValueError as e:
                return {"success": False, "error": str(e)}

            # Look up session in database (authoritative source for relationships)
            session = session_manager.get(resolved_session_id)
            if not session:
                return {
                    "success": False,
                    "error": f"Session {resolved_session_id} not found",
                }

            parent_session_id = session.parent_session_id
            if not parent_session_id:
                return {
                    "success": False,
                    "error": "No parent session for this session",
                }

            # Create the message
            msg = message_manager.create_message(
                from_session=resolved_session_id,
                to_session=parent_session_id,
                content=content,
                priority=priority,
            )

            logger.info(
                "Message sent from %s to parent %s: %s",
                resolved_session_id,
                parent_session_id,
                msg.id,
            )

            return {
                "success": True,
                "message": msg.to_dict(),
                "parent_session_id": parent_session_id,
            }

        except Exception as e:
            logger.error("Failed to send message to parent: %s", e)
            return {
                "success": False,
                "error": str(e),
            }

    @registry.tool(
        name="send_to_child",
        description="Send a message from a parent session to a specific child session. Accepts #N, N, UUID, or prefix for session IDs.",
    )
    async def send_to_child(
        parent_session_id: str,
        child_session_id: str,
        content: str,
        priority: str = "normal",
    ) -> dict[str, Any]:
        """
        Send a message to a child session.

        Use this when a parent agent needs to communicate instructions,
        updates, or coordination messages to a spawned child.

        Args:
            parent_session_id: Session reference (accepts #N, N, UUID, or prefix) for the parent (sender)
            child_session_id: Session reference (accepts #N, N, UUID, or prefix) for the child (recipient)
            content: Message content to send
            priority: Message priority ("normal" or "urgent")

        Returns:
            Dict with success status and message details
        """
        try:
            # Resolve session IDs to UUIDs (accepts #N, N, UUID, or prefix)
            try:
                resolved_parent_id = _resolve_session_id(parent_session_id)
                resolved_child_id = _resolve_session_id(child_session_id)
            except ValueError as e:
                return {"success": False, "error": str(e)}

            # Verify the child exists in database and belongs to this parent
            child_session = session_manager.get(resolved_child_id)
            if not child_session:
                return {
                    "success": False,
                    "error": f"Child session {resolved_child_id} not found",
                }

            if child_session.parent_session_id != resolved_parent_id:
                return {
                    "success": False,
                    "error": (
                        f"Session {resolved_child_id} is not a child of {resolved_parent_id}. "
                        f"Actual parent: {child_session.parent_session_id}"
                    ),
                }

            # Create the message
            msg = message_manager.create_message(
                from_session=resolved_parent_id,
                to_session=resolved_child_id,
                content=content,
                priority=priority,
            )

            logger.info(
                "Message sent from %s to child %s: %s",
                resolved_parent_id,
                resolved_child_id,
                msg.id,
            )

            return {
                "success": True,
                "message": msg.to_dict(),
            }

        except Exception as e:
            logger.error("Failed to send message to child: %s", e)
            return {
                "success": False,
                "error": str(e),
            }

    @registry.tool(
        name="poll_messages",
        description="Poll for messages sent to this session. Accepts #N, N, UUID, or prefix for session_id.",
    )
    async def poll_messages(
        session_id: str,
        unread_only: bool = True,
    ) -> dict[str, Any]:
        """
        Poll for incoming messages.

        Check for messages sent to this session from parent or child sessions.
        By default, returns only unread messages.

        Args:
            session_id: Session reference (accepts #N, N, UUID, or prefix) to check messages for
            unread_only: If True, only return unread messages (default: True)

        Returns:
            Dict with success status and list of messages
        """
        try:
            # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
            try:
                resolved_session_id = _resolve_session_id(session_id)
            except ValueError as e:
                return {"success": False, "error": str(e)}

            messages = message_manager.get_messages(
                to_session=resolved_session_id,
                unread_only=unread_only,
            )

            return {
                "success": True,
                "messages": [msg.to_dict() for msg in messages],
                "count": len(messages),
            }

        except Exception as e:
            logger.error(f"Failed to poll messages: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    @registry.tool(
        name="mark_message_read",
        description="Mark a message as read.",
    )
    async def mark_message_read(
        message_id: str,
    ) -> dict[str, Any]:
        """
        Mark a message as read.

        After processing a message, mark it as read so it won't appear
        in subsequent poll_messages calls with unread_only=True.

        Args:
            message_id: The message ID to mark as read

        Returns:
            Dict with success status and updated message
        """
        try:
            msg = message_manager.mark_read(message_id)

            return {
                "success": True,
                "message": msg.to_dict(),
            }

        except ValueError:
            return {
                "success": False,
                "error": f"Message not found: {message_id}",
            }
        except Exception as e:
            logger.error(f"Failed to mark message as read: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    @registry.tool(
        name="broadcast_to_children",
        description="Broadcast a message to all active child sessions. Accepts #N, N, UUID, or prefix for session_id.",
    )
    async def broadcast_to_children(
        parent_session_id: str,
        content: str,
        priority: str = "normal",
    ) -> dict[str, Any]:
        """
        Broadcast a message to all active children.

        Send the same message to all child sessions spawned by this parent
        that are currently active in the database.
        Useful for coordination or shutdown signals.

        Args:
            parent_session_id: Session reference (accepts #N, N, UUID, or prefix) for the parent
            content: Message content to broadcast
            priority: Message priority ("normal" or "urgent")

        Returns:
            Dict with success status and count of messages sent
        """
        try:
            # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
            try:
                resolved_parent_id = _resolve_session_id(parent_session_id)
            except ValueError as e:
                return {"success": False, "error": str(e)}

            # Get all children from database
            all_children = session_manager.find_children(resolved_parent_id)
            # Filter to active children only
            children = [c for c in all_children if c.status == "active"]

            if not children:
                return {
                    "success": True,
                    "sent_count": 0,
                    "message": "No active children found",
                }

            sent_count = 0
            errors = []

            for child in children:
                try:
                    message_manager.create_message(
                        from_session=resolved_parent_id,
                        to_session=child.id,
                        content=content,
                        priority=priority,
                    )
                    sent_count += 1
                except Exception as e:
                    errors.append(f"{child.id}: {e}")

            result: dict[str, Any] = {
                "success": True,
                "sent_count": sent_count,
                "total_children": len(children),
            }

            if errors:
                result["errors"] = errors

            logger.info(
                "Broadcast from %s sent to %d/%d children",
                resolved_parent_id,
                sent_count,
                len(children),
            )

            return result

        except Exception as e:
            logger.error("Failed to broadcast to children: %s", e)
            return {
                "success": False,
                "error": str(e),
            }
