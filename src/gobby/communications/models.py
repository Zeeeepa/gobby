"""Communications data models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class ChannelCapabilities:
    """Capabilities of a communication channel."""

    threading: bool = False
    reactions: bool = False
    files: bool = False
    markdown: bool = False
    max_message_length: int = 4000

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChannelCapabilities:
        """Create from dictionary."""
        return cls(
            threading=data.get("threading", False),
            reactions=data.get("reactions", False),
            files=data.get("files", False),
            markdown=data.get("markdown", False),
            max_message_length=data.get("max_message_length", 4000),
        )

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ChannelCapabilities:
        """Create from database row."""
        return cls(
            threading=bool(row.get("threading", False)),
            reactions=bool(row.get("reactions", False)),
            files=bool(row.get("files", False)),
            markdown=bool(row.get("markdown", False)),
            max_message_length=row.get("max_message_length", 4000),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "threading": self.threading,
            "reactions": self.reactions,
            "files": self.files,
            "markdown": self.markdown,
            "max_message_length": self.max_message_length,
        }


@dataclass
class ChannelConfig:
    """Configuration for a communication channel."""

    id: str
    channel_type: str
    name: str
    enabled: bool
    config_json: dict[str, Any]
    created_at: str
    updated_at: str
    webhook_secret: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ChannelConfig:
        """Create from database row."""
        config_json = row.get("config_json")
        if isinstance(config_json, str):
            import json

            config_json = json.loads(config_json)

        return cls(
            id=row["id"],
            channel_type=row.get("channel_type", "unknown"),
            name=row.get("name", "Unknown Channel"),
            enabled=bool(row.get("enabled", False)),
            config_json=config_json or {},
            webhook_secret=row.get("webhook_secret"),
            created_at=row.get("created_at", datetime.now().isoformat()),
            updated_at=row.get("updated_at", datetime.now().isoformat()),
        )


@dataclass
class CommsMessage:
    """A message sent or received via a communication channel."""

    id: str
    channel_id: str
    direction: Literal["inbound", "outbound"]
    content: str
    created_at: str
    identity_id: str | None = None
    content_type: str = "text"
    platform_message_id: str | None = None
    platform_thread_id: str | None = None
    session_id: str | None = None
    status: str = "sent"
    error: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> CommsMessage:
        """Create from database row."""
        metadata_json = row.get("metadata_json")
        if isinstance(metadata_json, str):
            import json

            metadata_json = json.loads(metadata_json)

        return cls(
            id=row["id"],
            channel_id=row.get("channel_id", "unknown"),
            identity_id=row.get("identity_id"),
            direction=row.get("direction", "outbound"),  # type: ignore[arg-type]
            content=row.get("content", ""),
            content_type=row.get("content_type", "text"),
            platform_message_id=row.get("platform_message_id"),
            platform_thread_id=row.get("platform_thread_id"),
            session_id=row.get("session_id"),
            status=row.get("status", "sent"),
            error=row.get("error"),
            metadata_json=metadata_json or {},
            created_at=row.get("created_at", datetime.now().isoformat()),
        )


@dataclass
class CommsIdentity:
    """An identity (user) on a communication channel."""

    id: str
    channel_id: str
    external_user_id: str
    created_at: str
    updated_at: str
    external_username: str | None = None
    session_id: str | None = None
    project_id: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> CommsIdentity:
        """Create from database row."""
        metadata_json = row.get("metadata_json")
        if isinstance(metadata_json, str):
            import json

            metadata_json = json.loads(metadata_json)

        return cls(
            id=row["id"],
            channel_id=row.get("channel_id", "unknown"),
            external_user_id=row.get("external_user_id", "unknown"),
            external_username=row.get("external_username"),
            session_id=row.get("session_id"),
            project_id=row.get("project_id"),
            metadata_json=metadata_json or {},
            created_at=row.get("created_at", datetime.now().isoformat()),
            updated_at=row.get("updated_at", datetime.now().isoformat()),
        )


@dataclass
class CommsRoutingRule:
    """A rule for routing inbound communication events."""

    id: str
    name: str
    channel_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    event_pattern: str = "*"
    project_id: str | None = None
    session_id: str | None = None
    priority: int = 0
    enabled: bool = True
    config_json: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> CommsRoutingRule:
        """Create from database row."""
        config_json = row.get("config_json")
        if isinstance(config_json, str):
            import json

            config_json = json.loads(config_json)

        return cls(
            id=row["id"],
            name=row.get("name", "Unknown Rule"),
            channel_id=row.get("channel_id"),
            event_pattern=row.get("event_pattern", "*"),
            project_id=row.get("project_id"),
            session_id=row.get("session_id"),
            priority=int(row.get("priority", 0)),
            enabled=bool(row.get("enabled", True)),
            config_json=config_json or {},
            created_at=row.get("created_at", datetime.now().isoformat()),
            updated_at=row.get("updated_at", datetime.now().isoformat()),
        )
