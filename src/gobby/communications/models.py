"""Communication models for the Gobby communications framework."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


def _parse_json_field(row: Any, field_name: str) -> dict[str, Any] | None:
    """Helper to parse a JSON field from a database row."""
    if hasattr(row, "keys") and field_name not in row.keys():
        return None
    raw = row[field_name]
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
        return None
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse {field_name} JSON, returning None")
        return None


@dataclass(kw_only=True)
class ChannelCapabilities:
    """Capabilities supported by a communication channel."""

    threading: bool
    reactions: bool
    files: bool
    markdown: bool
    max_message_length: int

    @classmethod
    def from_row(cls, row: Any) -> ChannelCapabilities:
        """Create ChannelCapabilities from database row or dict."""
        return cls(
            threading=bool(row["threading"]) if "threading" in row.keys() else False,
            reactions=bool(row["reactions"]) if "reactions" in row.keys() else False,
            files=bool(row["files"]) if "files" in row.keys() else False,
            markdown=bool(row["markdown"]) if "markdown" in row.keys() else False,
            max_message_length=int(row["max_message_length"])
            if "max_message_length" in row.keys()
            else 0,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "threading": self.threading,
            "reactions": self.reactions,
            "files": self.files,
            "markdown": self.markdown,
            "max_message_length": self.max_message_length,
        }


@dataclass(kw_only=True)
class ChannelConfig:
    """Configuration for a communication channel."""

    id: str
    channel_type: str
    name: str
    enabled: bool
    config_json: dict[str, Any] = field(default_factory=dict)
    webhook_secret: str | None = None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: Any) -> ChannelConfig:
        """Create ChannelConfig from database row."""
        return cls(
            id=row["id"],
            channel_type=row["channel_type"],
            name=row["name"],
            enabled=bool(row["enabled"]) if "enabled" in row.keys() else True,
            config_json=_parse_json_field(row, "config_json") or {},
            webhook_secret=row["webhook_secret"] if "webhook_secret" in row.keys() else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "channel_type": self.channel_type,
            "name": self.name,
            "enabled": self.enabled,
            "config_json": self.config_json,
            "webhook_secret": self.webhook_secret,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(kw_only=True)
class CommsMessage:
    """A message sent or received via a communication channel."""

    id: str
    channel_id: str
    direction: Literal["inbound", "outbound"]
    content: str
    identity_id: str | None = None
    content_type: str = "text"
    platform_message_id: str | None = None
    platform_thread_id: str | None = None
    session_id: str | None = None
    status: str = "sent"
    error: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None

    @classmethod
    def from_row(cls, row: Any) -> CommsMessage:
        """Create CommsMessage from database row."""
        return cls(
            id=row["id"],
            channel_id=row["channel_id"],
            identity_id=row["identity_id"] if "identity_id" in row.keys() else None,
            direction=row["direction"],
            content=row["content"],
            content_type=row["content_type"] or "text" if "content_type" in row.keys() else "text",
            platform_message_id=row["platform_message_id"]
            if "platform_message_id" in row.keys()
            else None,
            platform_thread_id=row["platform_thread_id"]
            if "platform_thread_id" in row.keys()
            else None,
            session_id=row["session_id"] if "session_id" in row.keys() else None,
            status=row["status"] or "sent" if "status" in row.keys() else "sent",
            error=row["error"] if "error" in row.keys() else None,
            metadata_json=_parse_json_field(row, "metadata_json") or {},
            created_at=row["created_at"] if "created_at" in row.keys() else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "identity_id": self.identity_id,
            "direction": self.direction,
            "content": self.content,
            "content_type": self.content_type,
            "platform_message_id": self.platform_message_id,
            "platform_thread_id": self.platform_thread_id,
            "session_id": self.session_id,
            "status": self.status,
            "error": self.error,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at,
        }


@dataclass(kw_only=True)
class CommsIdentity:
    """An identity on a communication channel."""

    id: str
    channel_id: str
    external_user_id: str
    project_id: str
    external_username: str | None = None
    session_id: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: Any) -> CommsIdentity:
        """Create CommsIdentity from database row."""
        return cls(
            id=row["id"],
            channel_id=row["channel_id"],
            external_user_id=row["external_user_id"],
            external_username=row["external_username"]
            if "external_username" in row.keys()
            else None,
            session_id=row["session_id"] if "session_id" in row.keys() else None,
            project_id=row["project_id"],
            metadata_json=_parse_json_field(row, "metadata_json") or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "external_user_id": self.external_user_id,
            "external_username": self.external_username,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(kw_only=True)
class CommsRoutingRule:
    """A routing rule for communication events."""

    id: str
    name: str
    project_id: str
    channel_id: str | None = None
    event_pattern: str = "*"
    session_id: str | None = None
    priority: int = 0
    enabled: bool = True
    config_json: dict[str, Any] = field(default_factory=dict)
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: Any) -> CommsRoutingRule:
        """Create CommsRoutingRule from database row."""
        return cls(
            id=row["id"],
            name=row["name"],
            channel_id=row["channel_id"] if "channel_id" in row.keys() else None,
            event_pattern=row["event_pattern"] or "*" if "event_pattern" in row.keys() else "*",
            project_id=row["project_id"],
            session_id=row["session_id"] if "session_id" in row.keys() else None,
            priority=row["priority"] if "priority" in row.keys() else 0,
            enabled=bool(row["enabled"]) if "enabled" in row.keys() else True,
            config_json=_parse_json_field(row, "config_json") or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "channel_id": self.channel_id,
            "event_pattern": self.event_pattern,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "priority": self.priority,
            "enabled": self.enabled,
            "config_json": self.config_json,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
