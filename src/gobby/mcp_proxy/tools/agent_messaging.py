"""
Inter-agent messaging tools for the gobby-agents MCP server.

Provides messaging capabilities between parent and child sessions:
- send_to_parent: Child sends message to its parent session
- send_to_child: Parent sends message to a specific child
- poll_messages: Check for incoming messages
- mark_message_read: Mark a message as read
- broadcast_to_children: Send message to all running children

These tools resolve session relationships from RunningAgentRegistry.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.agents.registry import RunningAgentRegistry
    from gobby.mcp_proxy.tools.internal import InternalToolRegistry
    from gobby.storage.inter_session_messages import InterSessionMessageManager

logger = logging.getLogger(__name__)


def add_messaging_tools(
    registry: InternalToolRegistry,
    message_manager: InterSessionMessageManager,
    agent_registry: RunningAgentRegistry,
) -> None:
    """
    Add inter-agent messaging tools to an existing registry.

    Args:
        registry: The InternalToolRegistry to add tools to (typically gobby-agents)
        message_manager: InterSessionMessageManager for persisting messages
        agent_registry: RunningAgentRegistry for resolving parent/child relationships
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
            # Find the running agent to get parent relationship
            agent = agent_registry.get_by_session(session_id)
            if not agent:
                return {
                    "success": False,
                    "error": f"Session {session_id} not found in running agent registry",
                }

            parent_session_id = agent.parent_session_id
            if not parent_session_id:
                return {
                    "success": False,
                    "error": "No parent session found for this agent",
                }

            # Create the message
            msg = message_manager.create_message(
                from_session=session_id,
                to_session=parent_session_id,
                content=content,
                priority=priority,
            )

            logger.info(f"Message sent from {session_id} to parent {parent_session_id}: {msg.id}")

            return {
                "success": True,
                "message": msg.to_dict(),
                "parent_session_id": parent_session_id,
            }

        except Exception as e:
            logger.error(f"Failed to send message to parent: {e}")
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
            # Verify the child exists and belongs to this parent
            child_agent = agent_registry.get_by_session(child_session_id)
            if not child_agent:
                return {
                    "success": False,
                    "error": f"Child session {child_session_id} not found in running agent registry",
                }

            if child_agent.parent_session_id != parent_session_id:
                return {
                    "success": False,
                    "error": (
                        f"Session {child_session_id} is not a child of {parent_session_id}. "
                        f"Actual parent: {child_agent.parent_session_id}"
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
                f"Message sent from {parent_session_id} to child {child_session_id}: {msg.id}"
            )

            return {
                "success": True,
                "message": msg.to_dict(),
            }

        except Exception as e:
            logger.error(f"Failed to send message to child: {e}")
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
        description="Broadcast a message to all running child sessions.",
    )
    async def broadcast_to_children(
        parent_session_id: str,
        content: str,
        priority: str = "normal",
    ) -> dict[str, Any]:
        """
        Broadcast a message to all running children.

        Send the same message to all child sessions spawned by this parent.
        Useful for coordination or shutdown signals.

        Args:
            parent_session_id: The parent session ID
            content: Message content to broadcast
            priority: Message priority ("normal" or "urgent")

        Returns:
            Dict with success status and count of messages sent
        """
        try:
            children = agent_registry.list_by_parent(parent_session_id)

            if not children:
                return {
                    "success": True,
                    "sent_count": 0,
                    "message": "No running children found",
                }

            sent_count = 0
            errors = []

            for child in children:
                try:
                    message_manager.create_message(
                        from_session=parent_session_id,
                        to_session=child.session_id,
                        content=content,
                        priority=priority,
                    )
                    sent_count += 1
                except Exception as e:
                    errors.append(f"{child.session_id}: {e}")

            result: dict[str, Any] = {
                "success": True,
                "sent_count": sent_count,
                "total_children": len(children),
            }

            if errors:
                result["errors"] = errors

            logger.info(
                f"Broadcast from {parent_session_id} sent to {sent_count}/{len(children)} children"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to broadcast to children: {e}")
            return {
                "success": False,
                "error": str(e),
            }
