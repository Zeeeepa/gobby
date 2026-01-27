"""
Tests for Sandbox Configuration Models.
"""

from typing import Any

import pytest

from gobby.agents.sandbox import ResolvedSandboxPaths, SandboxConfig


class TestSandboxConfig:
    """Tests for SandboxConfig Pydantic model."""

    def test_default_values(self):
        """Test that SandboxConfig has correct default values."""
        config = SandboxConfig()

        assert config.enabled is False
        assert config.mode == "permissive"
        assert config.allow_network is True
        assert config.extra_read_paths == []
        assert config.extra_write_paths == []

    def test_custom_values(self):
        """Test creating SandboxConfig with custom values."""
        config = SandboxConfig(
            enabled=True,
            mode="restrictive",
            allow_network=False,
            extra_read_paths=["/usr/share", "/opt/data"],
            extra_write_paths=["/tmp/output"],
        )

        assert config.enabled is True
        assert config.mode == "restrictive"
        assert config.allow_network is False
        assert config.extra_read_paths == ["/usr/share", "/opt/data"]
        assert config.extra_write_paths == ["/tmp/output"]

    def test_mode_literal_validation(self):
        """Test that mode only accepts valid literal values."""
        # Valid modes
        for mode in ["permissive", "restrictive"]:
            config = SandboxConfig(mode=mode)
            assert config.mode == mode

        # Invalid mode should raise validation error
        with pytest.raises(ValueError):
            SandboxConfig(mode="invalid_mode")  # type: ignore

    def test_serialization_to_dict(self):
        """Test that SandboxConfig can be serialized to dict."""
        config = SandboxConfig(
            enabled=True,
            mode="restrictive",
            allow_network=False,
            extra_read_paths=["/path/one"],
            extra_write_paths=["/path/two"],
        )

        data = config.model_dump()

        assert isinstance(data, dict)
        assert data["enabled"] is True
        assert data["mode"] == "restrictive"
        assert data["allow_network"] is False
        assert data["extra_read_paths"] == ["/path/one"]
        assert data["extra_write_paths"] == ["/path/two"]

    def test_serialization_from_dict(self):
        """Test that SandboxConfig can be created from dict."""
        data: dict[str, Any] = {
            "enabled": True,
            "mode": "permissive",
            "allow_network": True,
            "extra_read_paths": ["/data"],
            "extra_write_paths": [],
        }

        config = SandboxConfig(**data)

        assert config.enabled is True
        assert config.mode == "permissive"
        assert config.extra_read_paths == ["/data"]

    def test_json_serialization(self):
        """Test JSON serialization round-trip."""
        config = SandboxConfig(
            enabled=True,
            mode="restrictive",
            extra_read_paths=["/opt"],
        )

        json_str = config.model_dump_json()
        restored = SandboxConfig.model_validate_json(json_str)

        assert restored.enabled == config.enabled
        assert restored.mode == config.mode
        assert restored.extra_read_paths == config.extra_read_paths

    def test_partial_dict_uses_defaults(self):
        """Test that partial dict uses defaults for missing fields."""
        data: dict[str, Any] = {
            "enabled": True,
        }

        config = SandboxConfig(**data)

        assert config.enabled is True
        # Other fields should have defaults
        assert config.mode == "permissive"
        assert config.allow_network is True
        assert config.extra_read_paths == []
        assert config.extra_write_paths == []


class TestResolvedSandboxPaths:
    """Tests for ResolvedSandboxPaths Pydantic model."""

    def test_creation_with_required_fields(self):
        """Test creating ResolvedSandboxPaths with required fields."""
        paths = ResolvedSandboxPaths(
            workspace_path="/home/user/project",
            read_paths=["/usr/share"],
            write_paths=["/home/user/project"],
            allow_external_network=False,
        )

        assert paths.workspace_path == "/home/user/project"
        assert paths.gobby_daemon_port == 60887  # Default
        assert paths.read_paths == ["/usr/share"]
        assert paths.write_paths == ["/home/user/project"]
        assert paths.allow_external_network is False

    def test_default_daemon_port(self):
        """Test that gobby_daemon_port defaults to 60887."""
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=[],
            allow_external_network=True,
        )

        assert paths.gobby_daemon_port == 60887

    def test_custom_daemon_port(self):
        """Test setting custom daemon port."""
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            gobby_daemon_port=9999,
            read_paths=[],
            write_paths=[],
            allow_external_network=True,
        )

        assert paths.gobby_daemon_port == 9999

    def test_path_list_handling(self):
        """Test that path lists are handled correctly."""
        paths = ResolvedSandboxPaths(
            workspace_path="/workspace",
            read_paths=["/opt", "/usr/local", "/etc/config"],
            write_paths=["/workspace", "/tmp"],
            allow_external_network=False,
        )

        assert len(paths.read_paths) == 3
        assert "/opt" in paths.read_paths
        assert len(paths.write_paths) == 2
        assert "/tmp" in paths.write_paths

    def test_empty_path_lists(self):
        """Test with empty path lists."""
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=[],
            allow_external_network=True,
        )

        assert paths.read_paths == []
        assert paths.write_paths == []

    def test_serialization_to_dict(self):
        """Test that ResolvedSandboxPaths can be serialized to dict."""
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            gobby_daemon_port=60887,
            read_paths=["/data"],
            write_paths=["/project"],
            allow_external_network=False,
        )

        data = paths.model_dump()

        assert isinstance(data, dict)
        assert data["workspace_path"] == "/project"
        assert data["gobby_daemon_port"] == 60887
        assert data["read_paths"] == ["/data"]
        assert data["write_paths"] == ["/project"]
        assert data["allow_external_network"] is False
