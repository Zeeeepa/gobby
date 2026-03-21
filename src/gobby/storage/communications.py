"""Storage manager for communications."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from gobby.communications.models import (
    ChannelConfig,
    CommsIdentity,
    CommsMessage,
    CommsRoutingRule,
)
from gobby.storage.database import DatabaseProtocol

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class LocalCommunicationsStore:
    """Storage manager for communications data."""

    def __init__(self, db: DatabaseProtocol):
        """Initialize with database connection."""
        self.db = db

    def get_routing_rules(self, enabled_only: bool = True) -> list[CommsRoutingRule]:
        """Get all routing rules.

        Args:
            enabled_only: If True, only return enabled rules.

        Returns:
            List of CommsRoutingRule instances.
        """
        sql = "SELECT * FROM comms_routing_rules"
        params: list[Any] = []
        if enabled_only:
            sql += " WHERE enabled = 1"

        sql += " ORDER BY priority DESC"

        rows = self.db.fetchall(sql, tuple(params))
        return [CommsRoutingRule.from_row(dict(row)) for row in rows]

    def get_channel(self, channel_id: str) -> ChannelConfig | None:
        """Get a channel by ID."""
        row = self.db.fetchone("SELECT * FROM comms_channels WHERE id = ?", (channel_id,))
        if not row:
            return None
        return ChannelConfig.from_row(dict(row))

    def list_channels(self, enabled_only: bool = True) -> list[ChannelConfig]:
        """List all channels."""
        sql = "SELECT * FROM comms_channels"
        params: list[Any] = []
        if enabled_only:
            sql += " WHERE enabled = 1"

        rows = self.db.fetchall(sql, tuple(params))
        return [ChannelConfig.from_row(dict(row)) for row in rows]

    def save_message(self, message: CommsMessage) -> None:
        """Save a message to the database."""
        self.db.execute(
            """
            INSERT INTO comms_messages (
                id, channel_id, identity_id, direction, content, content_type,
                platform_message_id, platform_thread_id, session_id, status,
                error, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.channel_id,
                message.identity_id,
                message.direction,
                message.content,
                message.content_type,
                message.platform_message_id,
                message.platform_thread_id,
                message.session_id,
                message.status,
                message.error,
                json.dumps(message.metadata_json),
                message.created_at,
            ),
        )

    def get_identity(self, channel_id: str, external_user_id: str) -> CommsIdentity | None:
        """Get an identity by channel and external user ID."""
        row = self.db.fetchone(
            "SELECT * FROM comms_identities WHERE channel_id = ? AND external_user_id = ?",
            (channel_id, external_user_id),
        )
        if not row:
            return None
        return CommsIdentity.from_row(dict(row))

    def save_identity(self, identity: CommsIdentity) -> None:
        """Save or update an identity."""
        existing = self.get_identity(identity.channel_id, identity.external_user_id)
        if existing:
            self.db.execute(
                """
                UPDATE comms_identities SET
                    external_username = ?,
                    session_id = ?,
                    project_id = ?,
                    metadata_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    identity.external_username,
                    identity.session_id,
                    identity.project_id,
                    json.dumps(identity.metadata_json),
                    identity.updated_at,
                    existing.id,
                ),
            )
        else:
            self.db.execute(
                """
                INSERT INTO comms_identities (
                    id, channel_id, external_user_id, external_username,
                    session_id, project_id, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identity.id,
                    identity.channel_id,
                    identity.external_user_id,
                    identity.external_username,
                    identity.session_id,
                    identity.project_id,
                    json.dumps(identity.metadata_json),
                    identity.created_at,
                    identity.updated_at,
                ),
            )
