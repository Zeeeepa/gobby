"""Tests for communications configuration."""

from __future__ import annotations

from gobby.config.app import DaemonConfig
from gobby.config.communications import CommunicationsConfig, ChannelDefaults


def test_communications_config_defaults():
    config = CommunicationsConfig()
    assert config.enabled is False
    assert config.webhook_base_url == ""
    assert config.inbound_enabled is True
    assert config.outbound_enabled is True
    assert config.auto_create_sessions is True

    assert config.channel_defaults.rate_limit_per_minute == 30
    assert config.channel_defaults.burst == 5
    assert config.channel_defaults.retry_count == 3
    assert config.channel_defaults.poll_interval_seconds == 30
    assert config.channel_defaults.retention_days == 90


def test_daemon_config_includes_communications():
    config = DaemonConfig()
    assert hasattr(config, "communications")
    assert isinstance(config.communications, CommunicationsConfig)
    assert config.communications.enabled is False
