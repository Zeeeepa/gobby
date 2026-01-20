"""Inter-session messaging for agent coordination.

This module provides storage and management of messages sent between sessions,
enabling parent-child session communication and agent coordination.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from sqlite3 import Row
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.storage.database import LocalDatabase


@dataclass
class InterSessionMessage:
    """A message sent between sessions.

    Attributes:
        id: Unique message identifier
        from_session: ID of the sending session
        to_session: ID of the receiving session
        content: Message content
        priority: Message priority (e.g., "normal", "urgent")
        sent_at: Timestamp when message was sent
        read_at: Timestamp when message was read (None if unread)
    """

    id: str
    from_session: str
    to_session: str
    content: str
    priority: str
    sent_at: str
    read_at: str | None

    @classmethod
    def from_row(cls, row: Row) -> InterSessionMessage:
        """Create instance from database row.

        Args:
            row: SQLite row with message data

        Returns:
            InterSessionMessage instance
        """
        return cls(
            id=row["id"],
            from_session=row["from_session"],
            to_session=row["to_session"],
            content=row["content"],
            priority=row["priority"],
            sent_at=row["sent_at"],
            read_at=row["read_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary with all message fields
        """
        return {
            "id": self.id,
            "from_session": self.from_session,
            "to_session": self.to_session,
            "content": self.content,
            "priority": self.priority,
            "sent_at": self.sent_at,
            "read_at": self.read_at,
        }


class InterSessionMessageManager:
    """Manages inter-session messages.

    Provides CRUD operations for messages sent between sessions,
    enabling agent coordination and parent-child communication.
    """

    def __init__(self, db: LocalDatabase) -> None:
        """Initialize the message manager.

        Args:
            db: LocalDatabase instance for persistence
        """
        self.db = db

    def create_message(
        self,
        from_session: str,
        to_session: str,
        content: str,
        priority: str = "normal",
    ) -> InterSessionMessage:
        """Create and persist a new message.

        Args:
            from_session: ID of the sending session
            to_session: ID of the receiving session
            content: Message content
            priority: Message priority (default: "normal")

        Returns:
            The created InterSessionMessage
        """
        message_id = str(uuid.uuid4())
        sent_at = datetime.now(UTC).isoformat()

        self.db.execute(
            """
            INSERT INTO inter_session_messages
            (id, from_session, to_session, content, priority, sent_at, read_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (message_id, from_session, to_session, content, priority, sent_at),
        )

        return InterSessionMessage(
            id=message_id,
            from_session=from_session,
            to_session=to_session,
            content=content,
            priority=priority,
            sent_at=sent_at,
            read_at=None,
        )

    def get_message(self, message_id: str) -> InterSessionMessage | None:
        """Get a message by ID.

        Args:
            message_id: The message ID to retrieve

        Returns:
            The InterSessionMessage if found, None otherwise
        """
        row = self.db.fetchone(
            "SELECT * FROM inter_session_messages WHERE id = ?",
            (message_id,),
        )

        if row:
            return InterSessionMessage.from_row(row)
        return None

    def get_messages(self, to_session: str, unread_only: bool = False) -> list[InterSessionMessage]:
        """Get messages for a recipient session.

        Args:
            to_session: ID of the receiving session
            unread_only: If True, only return unread messages

        Returns:
            List of InterSessionMessage instances
        """
        if unread_only:
            query = """
                SELECT * FROM inter_session_messages
                WHERE to_session = ? AND read_at IS NULL
            """
        else:
            query = "SELECT * FROM inter_session_messages WHERE to_session = ?"

        rows = self.db.fetchall(query, (to_session,))
        return [InterSessionMessage.from_row(row) for row in rows]

    def mark_read(self, message_id: str) -> InterSessionMessage:
        """Mark a message as read.

        Args:
            message_id: The message ID to mark as read

        Returns:
            The updated InterSessionMessage

        Raises:
            ValueError: If message not found
        """
        read_at = datetime.now(UTC).isoformat()

        self.db.execute(
            "UPDATE inter_session_messages SET read_at = ? WHERE id = ?",
            (read_at, message_id),
        )

        message = self.get_message(message_id)
        if not message:
            raise ValueError(f"Message not found: {message_id}")
        return message
