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

    @registry.tool(
        name="send_to_parent",
        description="Send a message from a child session to its parent session.",
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
            session_id: The current (child) session ID
            content: Message content to send
            priority: Message priority ("normal" or "urgent")

        Returns:
            Dict with success status and message details
        """
        try:
            # Look up session in database (authoritative source for relationships)
            session = session_manager.get(session_id)
            if not session:
                return {
                    "success": False,
                    "error": f"Session {session_id} not found",
                }

            parent_session_id = session.parent_session_id
            if not parent_session_id:
                return {
                    "success": False,
                    "error": "No parent session for this session",
                }

            # Create the message
            msg = message_manager.create_message(
                from_session=session_id,
                to_session=parent_session_id,
                content=content,
                priority=priority,
            )

            logger.info(
                "Message sent from %s to parent %s: %s", session_id, parent_session_id, msg.id
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
        description="Send a message from a parent session to a specific child session.",
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
            parent_session_id: The parent session ID (sender)
            child_session_id: The child session ID (recipient)
            content: Message content to send
            priority: Message priority ("normal" or "urgent")

        Returns:
            Dict with success status and message details
        """
        try:
            # Verify the child exists in database and belongs to this parent
            child_session = session_manager.get(child_session_id)
            if not child_session:
                return {
                    "success": False,
                    "error": f"Child session {child_session_id} not found",
                }

            if child_session.parent_session_id != parent_session_id:
                return {
                    "success": False,
                    "error": (
                        f"Session {child_session_id} is not a child of {parent_session_id}. "
                        f"Actual parent: {child_session.parent_session_id}"
                    ),
                }

            # Create the message
            msg = message_manager.create_message(
                from_session=parent_session_id,
                to_session=child_session_id,
                content=content,
                priority=priority,
            )

            logger.info(
                "Message sent from %s to child %s: %s", parent_session_id, child_session_id, msg.id
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
        description="Poll for messages sent to this session.",
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
            session_id: The session ID to check messages for
            unread_only: If True, only return unread messages (default: True)

        Returns:
            Dict with success status and list of messages
        """
        try:
            messages = message_manager.get_messages(
                to_session=session_id,
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
        description="Broadcast a message to all active child sessions.",
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
            parent_session_id: The parent session ID
            content: Message content to broadcast
            priority: Message priority ("normal" or "urgent")

        Returns:
            Dict with success status and count of messages sent
        """
        try:
            # Get all children from database
            all_children = session_manager.find_children(parent_session_id)
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
                        from_session=parent_session_id,
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
                parent_session_id,
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
