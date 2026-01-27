"""
Tests for Sandbox Configuration Models.
"""

from typing import Any

import pytest

from gobby.agents.sandbox import (
    ClaudeSandboxResolver,
    CodexSandboxResolver,
    GeminiSandboxResolver,
    ResolvedSandboxPaths,
    SandboxConfig,
    SandboxResolver,
    compute_sandbox_paths,
    get_sandbox_resolver,
)


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

    def test_enabled_field_accepts_bool(self):
        """Test that enabled field only accepts boolean values."""
        # True
        config_true = SandboxConfig(enabled=True)
        assert config_true.enabled is True

        # False
        config_false = SandboxConfig(enabled=False)
        assert config_false.enabled is False

    def test_allow_network_field_accepts_bool(self):
        """Test that allow_network field only accepts boolean values."""
        # True
        config_true = SandboxConfig(allow_network=True)
        assert config_true.allow_network is True

        # False
        config_false = SandboxConfig(allow_network=False)
        assert config_false.allow_network is False

    def test_empty_path_lists_are_valid(self):
        """Test that empty path lists are valid configuration."""
        config = SandboxConfig(
            enabled=True,
            extra_read_paths=[],
            extra_write_paths=[],
        )

        assert config.extra_read_paths == []
        assert config.extra_write_paths == []

    def test_paths_preserve_order(self):
        """Test that path lists preserve insertion order."""
        paths = ["/first", "/second", "/third"]
        config = SandboxConfig(
            extra_read_paths=paths,
            extra_write_paths=list(reversed(paths)),
        )

        assert config.extra_read_paths == ["/first", "/second", "/third"]
        assert config.extra_write_paths == ["/third", "/second", "/first"]

    def test_model_copy_deep_creates_independent_instance(self):
        """Test that model_copy(deep=True) creates an independent copy."""
        original = SandboxConfig(
            enabled=True,
            mode="restrictive",
            extra_read_paths=["/data"],
        )

        copy = original.model_copy(deep=True)
        copy.extra_read_paths.append("/new")

        # Original should be unchanged (deep copy)
        assert "/new" not in original.extra_read_paths
        assert "/new" in copy.extra_read_paths


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


class TestSandboxResolver:
    """Tests for SandboxResolver abstract base class."""

    def test_cannot_instantiate_directly(self):
        """Test that SandboxResolver cannot be instantiated directly."""
        with pytest.raises(TypeError):
            SandboxResolver()  # type: ignore

    def test_subclass_must_implement_cli_name(self):
        """Test that subclass must implement cli_name property."""

        class IncompleteResolver(SandboxResolver):
            def resolve(
                self, config: SandboxConfig, paths: ResolvedSandboxPaths
            ) -> tuple[list[str], dict[str, str]]:
                return ([], {})

        with pytest.raises(TypeError):
            IncompleteResolver()  # type: ignore

    def test_subclass_must_implement_resolve(self):
        """Test that subclass must implement resolve method."""

        class IncompleteResolver(SandboxResolver):
            @property
            def cli_name(self) -> str:
                return "test"

        with pytest.raises(TypeError):
            IncompleteResolver()  # type: ignore

    def test_complete_subclass_can_be_instantiated(self):
        """Test that a complete subclass can be instantiated."""

        class CompleteResolver(SandboxResolver):
            @property
            def cli_name(self) -> str:
                return "test-cli"

            def resolve(
                self, config: SandboxConfig, paths: ResolvedSandboxPaths
            ) -> tuple[list[str], dict[str, str]]:
                return (["--sandbox"], {"TEST_VAR": "value"})

        resolver = CompleteResolver()
        assert resolver.cli_name == "test-cli"

        config = SandboxConfig(enabled=True)
        resolved_paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],
            allow_external_network=False,
        )

        args, env = resolver.resolve(config, resolved_paths)
        assert args == ["--sandbox"]
        assert env == {"TEST_VAR": "value"}


class TestClaudeSandboxResolver:
    """Tests for ClaudeSandboxResolver."""

    def test_cli_name(self):
        """Test that cli_name returns 'claude'."""
        resolver = ClaudeSandboxResolver()
        assert resolver.cli_name == "claude"

    def test_disabled_returns_empty(self):
        """Test that disabled sandbox returns empty args and env."""
        resolver = ClaudeSandboxResolver()
        config = SandboxConfig(enabled=False)
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        assert args == []
        assert env == {}

    def test_enabled_returns_settings_flag(self):
        """Test that enabled sandbox returns --settings with JSON config."""
        resolver = ClaudeSandboxResolver()
        config = SandboxConfig(enabled=True)
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        # Claude Code uses --settings with JSON
        assert len(args) == 2
        assert args[0] == "--settings"
        # Second arg should be valid JSON containing sandbox.enabled: true
        import json

        settings = json.loads(args[1])
        assert settings["sandbox"]["enabled"] is True

    def test_settings_json_structure(self):
        """Test that JSON settings has correct structure."""
        resolver = ClaudeSandboxResolver()
        config = SandboxConfig(enabled=True, mode="restrictive")
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        import json

        settings = json.loads(args[1])
        # Verify full sandbox structure
        assert "sandbox" in settings
        assert settings["sandbox"]["enabled"] is True
        assert settings["sandbox"]["autoAllowBashIfSandboxed"] is True
        assert "network" in settings["sandbox"]
        assert settings["sandbox"]["network"]["allowLocalBinding"] is True

    def test_returns_empty_env(self):
        """Test that Claude resolver always returns empty env dict."""
        resolver = ClaudeSandboxResolver()
        config = SandboxConfig(enabled=True)
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],
            allow_external_network=False,
        )

        args, env = resolver.resolve(config, paths)
        assert env == {}


class TestCodexSandboxResolver:
    """Tests for CodexSandboxResolver."""

    def test_cli_name(self):
        """Test that cli_name returns 'codex'."""
        resolver = CodexSandboxResolver()
        assert resolver.cli_name == "codex"

    def test_disabled_returns_empty(self):
        """Test that disabled sandbox returns empty args and env."""
        resolver = CodexSandboxResolver()
        config = SandboxConfig(enabled=False)
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        assert args == []
        assert env == {}

    def test_enabled_permissive_mode(self):
        """Test permissive mode returns workspace-write."""
        resolver = CodexSandboxResolver()
        config = SandboxConfig(enabled=True, mode="permissive")
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        assert "--sandbox" in args
        assert "workspace-write" in args

    def test_enabled_restrictive_mode(self):
        """Test restrictive mode returns read-only."""
        resolver = CodexSandboxResolver()
        config = SandboxConfig(enabled=True, mode="restrictive")
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        assert "--sandbox" in args
        assert "read-only" in args

    def test_extra_write_paths_added(self):
        """Test that extra write paths are added via --add-dir."""
        resolver = CodexSandboxResolver()
        config = SandboxConfig(enabled=True)
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project", "/extra/path"],
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        assert "--add-dir" in args
        # Extra path should be added (workspace is implicit)
        add_dir_idx = args.index("--add-dir")
        assert args[add_dir_idx + 1] == "/extra/path"

    def test_multiple_extra_write_paths(self):
        """Test that multiple extra write paths are all added."""
        resolver = CodexSandboxResolver()
        config = SandboxConfig(enabled=True)
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project", "/path/one", "/path/two"],
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        # Count --add-dir occurrences (should be 2 for the extra paths)
        add_dir_count = args.count("--add-dir")
        assert add_dir_count == 2

    def test_no_extra_paths_no_add_dir(self):
        """Test that no --add-dir is added when only workspace path exists."""
        resolver = CodexSandboxResolver()
        config = SandboxConfig(enabled=True)
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],  # Only workspace
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        assert "--add-dir" not in args


class TestGeminiSandboxResolver:
    """Tests for GeminiSandboxResolver."""

    def test_cli_name(self):
        """Test that cli_name returns 'gemini'."""
        resolver = GeminiSandboxResolver()
        assert resolver.cli_name == "gemini"

    def test_disabled_returns_empty(self):
        """Test that disabled sandbox returns empty args and env."""
        resolver = GeminiSandboxResolver()
        config = SandboxConfig(enabled=False)
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        assert args == []
        assert env == {}

    def test_enabled_returns_sandbox_flag(self):
        """Test that enabled sandbox returns exactly -s flag."""
        resolver = GeminiSandboxResolver()
        config = SandboxConfig(enabled=True)
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        assert args == ["-s"]

    def test_permissive_sets_exact_seatbelt_profile(self):
        """Test permissive mode sets SEATBELT_PROFILE to permissive-open."""
        resolver = GeminiSandboxResolver()
        config = SandboxConfig(enabled=True, mode="permissive")
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        assert env["SEATBELT_PROFILE"] == "permissive-open"

    def test_restrictive_sets_exact_seatbelt_profile(self):
        """Test restrictive mode sets SEATBELT_PROFILE to restrictive-closed."""
        resolver = GeminiSandboxResolver()
        config = SandboxConfig(enabled=True, mode="restrictive")
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        assert env["SEATBELT_PROFILE"] == "restrictive-closed"

    def test_permissive_returns_both_args_and_env(self):
        """Test permissive mode returns both -s flag and SEATBELT_PROFILE."""
        resolver = GeminiSandboxResolver()
        config = SandboxConfig(enabled=True, mode="permissive")
        paths = ResolvedSandboxPaths(
            workspace_path="/project",
            read_paths=[],
            write_paths=["/project"],
            allow_external_network=True,
        )

        args, env = resolver.resolve(config, paths)
        assert args == ["-s"]
        assert "SEATBELT_PROFILE" in env
        assert len(env) == 1  # Only SEATBELT_PROFILE


class TestGetSandboxResolver:
    """Tests for get_sandbox_resolver factory function."""

    def test_returns_claude_resolver(self):
        """Test that 'claude' returns ClaudeSandboxResolver."""
        resolver = get_sandbox_resolver("claude")
        assert isinstance(resolver, ClaudeSandboxResolver)

    def test_returns_codex_resolver(self):
        """Test that 'codex' returns CodexSandboxResolver."""
        resolver = get_sandbox_resolver("codex")
        assert isinstance(resolver, CodexSandboxResolver)

    def test_returns_gemini_resolver(self):
        """Test that 'gemini' returns GeminiSandboxResolver."""
        resolver = get_sandbox_resolver("gemini")
        assert isinstance(resolver, GeminiSandboxResolver)

    def test_unknown_cli_raises_value_error(self):
        """Test that unknown CLI raises ValueError."""
        with pytest.raises(ValueError, match="Unknown CLI"):
            get_sandbox_resolver("unknown-cli")


class TestComputeSandboxPaths:
    """Tests for compute_sandbox_paths helper function."""

    def test_computes_paths_from_config(self):
        """Test computing paths from SandboxConfig."""
        config = SandboxConfig(
            enabled=True,
            allow_network=False,
            extra_read_paths=["/opt/data"],
            extra_write_paths=["/tmp/output"],
        )

        paths = compute_sandbox_paths(
            config=config,
            workspace_path="/project",
            gobby_daemon_port=60887,
        )

        assert paths.workspace_path == "/project"
        assert paths.gobby_daemon_port == 60887
        assert paths.allow_external_network is False
        assert "/project" in paths.write_paths
        assert "/tmp/output" in paths.write_paths
        assert "/opt/data" in paths.read_paths

    def test_workspace_always_in_write_paths(self):
        """Test that workspace is always included in write_paths."""
        config = SandboxConfig(enabled=True)

        paths = compute_sandbox_paths(
            config=config,
            workspace_path="/my/workspace",
        )

        assert "/my/workspace" in paths.write_paths

    def test_custom_daemon_port(self):
        """Test custom daemon port is set."""
        config = SandboxConfig(enabled=True)

        paths = compute_sandbox_paths(
            config=config,
            workspace_path="/project",
            gobby_daemon_port=9999,
        )

        assert paths.gobby_daemon_port == 9999
