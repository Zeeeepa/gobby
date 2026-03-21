"""Configuration for the Gobby communications framework."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChannelDefaults(BaseModel):
    """Default settings for communication channels."""

    rate_limit_per_minute: int = Field(default=30, description="Default rate limit per minute")
    burst: int = Field(default=5, description="Default burst size")
    retry_count: int = Field(default=3, description="Default retry count")
    poll_interval_seconds: int = Field(default=30, description="Default poll interval in seconds")
    retention_days: int = Field(default=90, description="Default retention days")


class CommunicationsConfig(BaseModel):
    """Configuration for the communications framework."""

    enabled: bool = Field(default=False, description="Enable communications framework")
    webhook_base_url: str = Field(default="", description="Base URL for incoming webhooks")
    channel_defaults: ChannelDefaults = Field(
        default_factory=ChannelDefaults, description="Default channel settings"
    )
    inbound_enabled: bool = Field(default=True, description="Enable inbound messages")
    outbound_enabled: bool = Field(default=True, description="Enable outbound messages")
    auto_create_sessions: bool = Field(
        default=True, description="Auto-create sessions for new inbound identities"
    )
