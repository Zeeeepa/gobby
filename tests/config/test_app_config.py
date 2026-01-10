"""Tests for the configuration system."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from pydantic import ValidationError

from gobby.config.app import (
    CodeExecutionConfig,
    CompactHandoffConfig,
    ContextInjectionConfig,
    DaemonConfig,
    GobbyTasksConfig,
    HookExtensionsConfig,
    ImportMCPServerConfig,
    LLMProviderConfig,
    LLMProvidersConfig,
    LoggingSettings,
    MCPClientProxyConfig,
    MemoryConfig,
    MemorySyncConfig,
    MessageTrackingConfig,
    MetricsConfig,
    PluginItemConfig,
    PluginsConfig,
    RecommendToolsConfig,
    SessionLifecycleConfig,
    SessionSummaryConfig,
    TaskExpansionConfig,
    TaskValidationConfig,
    TitleSynthesisConfig,
    ToolSummarizerConfig,
    WebhookEndpointConfig,
    WebhooksConfig,
    WebSocketBroadcastConfig,
    WebSocketSettings,
    WorkflowConfig,
    apply_cli_overrides,
    expand_env_vars,
    generate_default_config,
    load_config,
    load_yaml,
    save_config,
)


class TestExpandEnvVars:
    """Tests for expand_env_vars function."""

    def test_expand_simple_env_var(self):
        """Test simple ${VAR} expansion."""
        with patch.dict(os.environ, {"MY_VAR": "hello"}):
            result = expand_env_vars("value: ${MY_VAR}")
            assert result == "value: hello"

    def test_expand_with_default_when_var_set(self):
        """Test ${VAR:-default} uses VAR value when set."""
        with patch.dict(os.environ, {"MY_VAR": "actual_value"}):
            result = expand_env_vars("value: ${MY_VAR:-default_value}")
            assert result == "value: actual_value"

    def test_expand_with_default_when_var_unset(self):
        """Test ${VAR:-default} uses default when VAR is unset."""
        # Ensure the var is not set
        env = os.environ.copy()
        env.pop("UNSET_VAR", None)
        with patch.dict(os.environ, env, clear=True):
            result = expand_env_vars("value: ${UNSET_VAR:-fallback}")
            assert result == "value: fallback"

    def test_expand_with_default_when_var_empty(self):
        """Test ${VAR:-default} uses default when VAR is empty string."""
        with patch.dict(os.environ, {"EMPTY_VAR": ""}):
            result = expand_env_vars("value: ${EMPTY_VAR:-fallback}")
            assert result == "value: fallback"

    def test_expand_simple_var_unset_leaves_unchanged(self):
        """Test simple ${VAR} is left unchanged when VAR is unset."""
        env = os.environ.copy()
        env.pop("UNDEFINED_VAR", None)
        with patch.dict(os.environ, env, clear=True):
            result = expand_env_vars("value: ${UNDEFINED_VAR}")
            assert result == "value: ${UNDEFINED_VAR}"

    def test_expand_multiple_vars(self):
        """Test expanding multiple variables in one string."""
        with patch.dict(os.environ, {"VAR1": "first", "VAR2": "second"}):
            result = expand_env_vars("a: ${VAR1}, b: ${VAR2:-def}")
            assert result == "a: first, b: second"

    def test_expand_no_vars(self):
        """Test string without env vars is unchanged."""
        result = expand_env_vars("plain text without variables")
        assert result == "plain text without variables"

    def test_expand_empty_default(self):
        """Test ${VAR:-} uses empty string as default."""
        env = os.environ.copy()
        env.pop("UNSET_VAR", None)
        with patch.dict(os.environ, env, clear=True):
            result = expand_env_vars("value: ${UNSET_VAR:-}")
            assert result == "value: "


class TestWebSocketSettings:
    """Tests for WebSocketSettings configuration."""

    def test_default_values(self):
        """Test default WebSocket settings."""
        settings = WebSocketSettings()
        assert settings.enabled is True
        assert settings.port == 8766
        assert settings.ping_interval == 30
        assert settings.ping_timeout == 10

    def test_custom_values(self):
        """Test custom WebSocket settings."""
        settings = WebSocketSettings(
            enabled=False,
            port=9000,
            ping_interval=60,
            ping_timeout=20,
        )
        assert settings.enabled is False
        assert settings.port == 9000
        assert settings.ping_interval == 60
        assert settings.ping_timeout == 20

    def test_port_validation_too_low(self):
        """Test port validation rejects ports below 1024."""
        with pytest.raises(ValidationError):
            WebSocketSettings(port=80)

    def test_port_validation_too_high(self):
        """Test port validation rejects ports above 65535."""
        with pytest.raises(ValidationError):
            WebSocketSettings(port=70000)

    def test_ping_interval_must_be_positive(self):
        """Test ping_interval must be positive."""
        with pytest.raises(ValidationError):
            WebSocketSettings(ping_interval=0)


class TestLoggingSettings:
    """Tests for LoggingSettings configuration."""

    def test_default_values(self):
        """Test default logging settings."""
        settings = LoggingSettings()
        assert settings.level == "info"
        assert settings.format == "text"
        assert settings.max_size_mb == 10
        assert settings.backup_count == 5

    def test_valid_levels(self):
        """Test valid log levels."""
        for level in ["debug", "info", "warning", "error"]:
            settings = LoggingSettings(level=level)
            assert settings.level == level

    def test_invalid_level(self):
        """Test invalid log level raises error."""
        with pytest.raises(ValidationError):
            LoggingSettings(level="invalid")

    def test_max_size_must_be_positive(self):
        """Test max_size_mb must be positive."""
        with pytest.raises(ValidationError):
            LoggingSettings(max_size_mb=0)


class TestSessionSummaryConfig:
    """Tests for SessionSummaryConfig."""

    def test_default_values(self):
        """Test default session summary config."""
        config = SessionSummaryConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-haiku-4-5"
        assert config.prompt is None

    def test_custom_values(self):
        """Test custom session summary config."""
        config = SessionSummaryConfig(
            enabled=False,
            provider="gemini",
            model="gemini-2.0-flash",
            prompt="Custom prompt",
        )
        assert config.enabled is False
        assert config.provider == "gemini"
        assert config.model == "gemini-2.0-flash"
        assert config.prompt == "Custom prompt"


class TestCodeExecutionConfig:
    """Tests for CodeExecutionConfig."""

    def test_default_values(self):
        """Test default code execution config."""
        config = CodeExecutionConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-sonnet-4-5"
        assert config.max_turns == 5
        assert config.default_timeout == 30

    def test_max_turns_validation(self):
        """Test max_turns must be positive."""
        with pytest.raises(ValidationError):
            CodeExecutionConfig(max_turns=0)

    def test_timeout_validation(self):
        """Test timeout must be positive."""
        with pytest.raises(ValidationError):
            CodeExecutionConfig(default_timeout=0)


class TestMCPClientProxyConfig:
    """Tests for MCPClientProxyConfig."""

    def test_default_values(self):
        """Test default MCP client proxy config."""
        config = MCPClientProxyConfig()
        assert config.enabled is True
        assert config.connect_timeout == 30.0
        assert config.proxy_timeout == 30
        assert config.tool_timeout == 30

    def test_connect_timeout_custom(self):
        """Test connect_timeout can be customized."""
        config = MCPClientProxyConfig(connect_timeout=60.0)
        assert config.connect_timeout == 60.0

    def test_connect_timeout_validation(self):
        """Test connect_timeout must be positive."""
        with pytest.raises(ValidationError):
            MCPClientProxyConfig(connect_timeout=0)

        with pytest.raises(ValidationError):
            MCPClientProxyConfig(connect_timeout=-5.0)

    def test_timeout_validation(self):
        """Test timeouts must be positive."""
        with pytest.raises(ValidationError):
            MCPClientProxyConfig(proxy_timeout=0)

        with pytest.raises(ValidationError):
            MCPClientProxyConfig(tool_timeout=-1)


class TestLLMProviderConfig:
    """Tests for LLMProviderConfig."""

    def test_models_list(self):
        """Test getting models as list."""
        config = LLMProviderConfig(
            models="model-a, model-b, model-c",
        )
        models = config.get_models_list()
        assert models == ["model-a", "model-b", "model-c"]

    def test_empty_models_in_list(self):
        """Test empty model entries are filtered."""
        config = LLMProviderConfig(
            models="model-a, , model-b",
        )
        models = config.get_models_list()
        assert models == ["model-a", "model-b"]


class TestLLMProvidersConfig:
    """Tests for LLMProvidersConfig."""

    def test_default_empty(self):
        """Test default config has no providers."""
        config = LLMProvidersConfig()
        assert config.get_enabled_providers() == []

    def test_enabled_providers(self):
        """Test listing enabled providers."""
        config = LLMProvidersConfig(
            claude=LLMProviderConfig(models="claude-haiku-4-5"),
            gemini=LLMProviderConfig(models="gemini-2.0-flash"),
        )
        providers = config.get_enabled_providers()
        assert "claude" in providers
        assert "gemini" in providers
        assert len(providers) == 2


class TestDaemonConfig:
    """Tests for DaemonConfig."""

    def test_default_values(self):
        """Test default daemon config."""
        config = DaemonConfig()
        assert config.daemon_port == 8765
        assert config.daemon_health_check_interval == 10.0
        assert config.database_path == "~/.gobby/gobby.db"

    def test_port_validation(self):
        """Test daemon port validation."""
        with pytest.raises(ValidationError):
            DaemonConfig(daemon_port=80)

        with pytest.raises(ValidationError):
            DaemonConfig(daemon_port=70000)

    def test_health_check_interval_validation(self):
        """Test health check interval validation."""
        with pytest.raises(ValidationError):
            DaemonConfig(daemon_health_check_interval=0.5)

        with pytest.raises(ValidationError):
            DaemonConfig(daemon_health_check_interval=500.0)

    def test_sub_config_access(self):
        """Test accessing sub-configurations."""
        config = DaemonConfig()
        assert config.get_code_execution_config() == config.code_execution
        assert config.get_recommend_tools_config() == config.recommend_tools
        assert config.get_mcp_client_proxy_config() == config.mcp_client_proxy

    def test_get_verification_defaults(self):
        """Test get_verification_defaults returns verification_defaults config."""
        config = DaemonConfig()
        verification_config = config.get_verification_defaults()
        assert verification_config is config.verification_defaults
        # Verify it returns the correct type
        from gobby.config.features import ProjectVerificationConfig

        assert isinstance(verification_config, ProjectVerificationConfig)


class TestLoadYaml:
    """Tests for load_yaml function."""

    def test_load_yaml_file(self, temp_dir: Path):
        """Test loading YAML file."""
        config_file = temp_dir / "config.yaml"
        config_file.write_text(yaml.dump({"daemon_port": 9000, "logging": {"level": "debug"}}))

        data = load_yaml(str(config_file))
        assert data["daemon_port"] == 9000
        assert data["logging"]["level"] == "debug"

    def test_load_json_file(self, temp_dir: Path):
        """Test loading JSON file."""
        config_file = temp_dir / "config.json"
        config_file.write_text(json.dumps({"daemon_port": 9001}))

        data = load_yaml(str(config_file))
        assert data["daemon_port"] == 9001

    def test_load_nonexistent_file(self, temp_dir: Path):
        """Test loading nonexistent file returns empty dict."""
        data = load_yaml(str(temp_dir / "nonexistent.yaml"))
        assert data == {}

    def test_load_empty_file(self, temp_dir: Path):
        """Test loading empty file returns empty dict."""
        config_file = temp_dir / "empty.yaml"
        config_file.write_text("")

        data = load_yaml(str(config_file))
        assert data == {}

    def test_invalid_extension(self, temp_dir: Path):
        """Test invalid file extension raises error."""
        config_file = temp_dir / "config.txt"
        config_file.write_text("key: value")

        with pytest.raises(ValueError, match="extension"):
            load_yaml(str(config_file))

    def test_invalid_yaml(self, temp_dir: Path):
        """Test invalid YAML raises error."""
        config_file = temp_dir / "invalid.yaml"
        config_file.write_text("invalid: yaml: content: [")

        with pytest.raises(ValueError, match="Invalid YAML"):
            load_yaml(str(config_file))

    def test_invalid_json(self, temp_dir: Path):
        """Test invalid JSON raises error."""
        config_file = temp_dir / "invalid.json"
        config_file.write_text('{"key": "value"')  # Missing closing brace

        with pytest.raises(ValueError, match="Invalid JSON"):
            load_yaml(str(config_file))

    def test_empty_json_file(self, temp_dir: Path):
        """Test loading empty JSON file returns empty dict."""
        config_file = temp_dir / "empty.json"
        config_file.write_text("")

        data = load_yaml(str(config_file))
        assert data == {}

    def test_env_var_expansion_in_yaml(self, temp_dir: Path, monkeypatch):
        """Test environment variable expansion in YAML files."""
        monkeypatch.delenv("TEST_PORT", raising=False)

        config_file = temp_dir / "env_config.yaml"
        config_file.write_text("daemon_port: ${TEST_PORT:-9999}")

        data = load_yaml(str(config_file))
        assert data["daemon_port"] == 9999


class TestApplyCliOverrides:
    """Tests for apply_cli_overrides function."""

    def test_simple_override(self):
        """Test simple key override."""
        config = {"daemon_port": 8765}
        overrides = {"daemon_port": 9000}

        result = apply_cli_overrides(config, overrides)
        assert result["daemon_port"] == 9000

    def test_nested_override(self):
        """Test nested key override with dot notation."""
        config = {"logging": {"level": "info"}}
        overrides = {"logging.level": "debug"}

        result = apply_cli_overrides(config, overrides)
        assert result["logging"]["level"] == "debug"

    def test_creates_nested_path(self):
        """Test creating nested path that doesn't exist."""
        config = {}
        overrides = {"logging.level": "debug"}

        result = apply_cli_overrides(config, overrides)
        assert result["logging"]["level"] == "debug"

    def test_none_overrides(self):
        """Test None overrides returns config unchanged."""
        config = {"key": "value"}
        result = apply_cli_overrides(config, None)
        assert result == config


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_default_config(self, temp_dir: Path, monkeypatch):
        """Test loading default config when no file exists."""
        monkeypatch.chdir(temp_dir)
        config = load_config(config_file=str(temp_dir / "nonexistent.yaml"))
        assert isinstance(config, DaemonConfig)

    def test_load_with_yaml_file(self, temp_dir: Path):
        """Test loading config from YAML file."""
        config_file = temp_dir / "config.yaml"
        config_file.write_text(yaml.dump({"daemon_port": 9000}))

        config = load_config(config_file=str(config_file))
        assert config.daemon_port == 9000

    def test_load_with_cli_overrides(self, temp_dir: Path):
        """Test loading config with CLI overrides."""
        config_file = temp_dir / "config.yaml"
        config_file.write_text(yaml.dump({"daemon_port": 8000}))

        config = load_config(
            config_file=str(config_file),
            cli_overrides={"daemon_port": 9000},
        )
        assert config.daemon_port == 9000

    def test_create_default_config(self, temp_dir: Path):
        """Test creating default config file."""
        config_file = temp_dir / "new_config.yaml"
        assert not config_file.exists()

        load_config(config_file=str(config_file), create_default=True)
        assert config_file.exists()

    def test_load_config_with_none_path_uses_default(self, temp_dir: Path, monkeypatch):
        """Test loading config with config_file=None uses default path."""
        # Mock the default path to point to our temp directory
        default_path = temp_dir / ".gobby" / "config.yaml"
        default_path.parent.mkdir(parents=True, exist_ok=True)
        default_path.write_text(yaml.dump({"daemon_port": 7777}))

        # Patch expanduser to redirect ~/.gobby to temp_dir/.gobby
        original_expanduser = Path.expanduser

        def mock_expanduser(self):
            path_str = str(self)
            if path_str.startswith("~/.gobby"):
                return temp_dir / ".gobby" / path_str[9:]  # Remove ~/.gobby/
            return original_expanduser(self)

        monkeypatch.setattr(Path, "expanduser", mock_expanduser)

        config = load_config(config_file=None)
        assert config.daemon_port == 7777

    def test_load_config_validation_error(self, temp_dir: Path):
        """Test load_config raises ValueError on invalid configuration."""
        config_file = temp_dir / "invalid_config.yaml"
        # Write invalid port value (out of range)
        config_file.write_text(yaml.dump({"daemon_port": 80}))

        with pytest.raises(ValueError, match="Configuration validation failed"):
            load_config(config_file=str(config_file))

    def test_load_config_validation_error_invalid_type(self, temp_dir: Path):
        """Test load_config raises ValueError on invalid type."""
        config_file = temp_dir / "bad_type.yaml"
        # Write string instead of int for port
        config_file.write_text("daemon_port: not_a_number")

        with pytest.raises(ValueError, match="Configuration validation failed"):
            load_config(config_file=str(config_file))


class TestGenerateDefaultConfig:
    """Tests for generate_default_config function."""

    def test_generates_file(self, temp_dir: Path):
        """Test generating default config file."""
        config_file = temp_dir / "generated.yaml"
        generate_default_config(str(config_file))

        assert config_file.exists()
        content = yaml.safe_load(config_file.read_text())
        assert "daemon_port" in content
        assert "websocket" in content
        assert "logging" in content

    def test_creates_parent_directory(self, temp_dir: Path):
        """Test creating parent directory for config file."""
        config_file = temp_dir / "subdir" / "config.yaml"
        generate_default_config(str(config_file))

        assert config_file.exists()


class TestSaveConfig:
    """Tests for save_config function."""

    def test_saves_config(self, temp_dir: Path, default_config: DaemonConfig):
        """Test saving config to file."""
        config_file = temp_dir / "saved.yaml"
        save_config(default_config, str(config_file))

        assert config_file.exists()
        content = yaml.safe_load(config_file.read_text())
        assert content["daemon_port"] == default_config.daemon_port

    def test_file_permissions(self, temp_dir: Path, default_config: DaemonConfig):
        """Test saved config has restrictive permissions."""
        config_file = temp_dir / "secure.yaml"
        save_config(default_config, str(config_file))

        # Check permissions (0o600 = owner read/write only)
        mode = config_file.stat().st_mode & 0o777
        assert mode == 0o600

    def test_creates_parent_directory(self, temp_dir: Path, default_config: DaemonConfig):
        """Test creating parent directory when saving."""
        config_file = temp_dir / "nested" / "dir" / "config.yaml"
        save_config(default_config, str(config_file))

        assert config_file.exists()

    def test_save_config_with_none_path_uses_default(
        self, temp_dir: Path, default_config: DaemonConfig, monkeypatch
    ):
        """Test saving config with config_file=None uses default path."""
        # Patch expanduser to redirect ~/.gobby to temp_dir/.gobby
        original_expanduser = Path.expanduser

        def mock_expanduser(self):
            path_str = str(self)
            if path_str.startswith("~/.gobby"):
                return temp_dir / ".gobby" / path_str[9:]  # Remove ~/.gobby/
            return original_expanduser(self)

        monkeypatch.setattr(Path, "expanduser", mock_expanduser)

        save_config(default_config, config_file=None)

        # Check the file was saved to the mocked default path
        expected_path = temp_dir / ".gobby" / "config.yaml"
        assert expected_path.exists()


class TestRecommendToolsConfig:
    """Tests for RecommendToolsConfig."""

    def test_default_values(self):
        """Test default recommend tools config."""
        config = RecommendToolsConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-sonnet-4-5"
        assert "CRITICAL PRIORITIZATION RULES" in config.prompt


class TestImportMCPServerConfig:
    """Tests for ImportMCPServerConfig."""

    def test_default_values(self):
        """Test default import MCP server config."""
        config = ImportMCPServerConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-haiku-4-5"
        assert "transport" in config.prompt


class TestTitleSynthesisConfig:
    """Tests for TitleSynthesisConfig."""

    def test_default_values(self):
        """Test default title synthesis config."""
        config = TitleSynthesisConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-haiku-4-5"
        assert config.prompt is None


class TestWebSocketBroadcastConfig:
    """Tests for WebSocketBroadcastConfig."""

    def test_default_values(self):
        """Test default WebSocket broadcast config."""
        config = WebSocketBroadcastConfig()
        assert config.enabled is True
        assert "session-start" in config.broadcast_events
        assert config.include_payload is True


class TestHookExtensionsConfig:
    """Tests for HookExtensionsConfig."""

    def test_default_values(self):
        """Test default hook extensions config."""
        config = HookExtensionsConfig()
        assert isinstance(config.websocket, WebSocketBroadcastConfig)


class TestTaskExpansionConfig:
    """Tests for TaskExpansionConfig."""

    def test_default_values(self):
        """Test default task expansion config."""
        config = TaskExpansionConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-opus-4-5"  # Uses opus for complex task expansion
        assert config.prompt is None


class TestTaskValidationConfig:
    """Tests for TaskValidationConfig."""

    def test_default_values(self):
        """Test default task validation config."""
        config = TaskValidationConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-haiku-4-5"
        assert config.prompt is None


class TestWorkflowConfig:
    """Tests for WorkflowConfig."""

    def test_default_values(self):
        """Test default workflow config."""
        config = WorkflowConfig()
        assert config.enabled is True
        assert config.timeout == 0.0

    def test_timeout_validation(self):
        """Test timeout must be positive."""
        with pytest.raises(ValidationError):
            WorkflowConfig(timeout=-1)


class TestMessageTrackingConfig:
    """Tests for MessageTrackingConfig."""

    def test_default_values(self):
        """Test default message tracking config."""
        config = MessageTrackingConfig()
        assert config.enabled is True
        assert config.poll_interval == 5.0
        assert config.debounce_delay == 1.0
        assert config.max_message_length == 10000
        assert config.broadcast_enabled is True

    def test_positive_validation(self):
        """Test positive values validation."""
        with pytest.raises(ValidationError):
            MessageTrackingConfig(poll_interval=0)
        with pytest.raises(ValidationError):
            MessageTrackingConfig(debounce_delay=0)


class TestSessionLifecycleConfig:
    """Tests for SessionLifecycleConfig."""

    def test_default_values(self):
        """Test default session lifecycle config."""
        config = SessionLifecycleConfig()
        assert config.stale_session_timeout_hours == 24
        assert config.expire_check_interval_minutes == 60
        assert config.transcript_processing_interval_minutes == 5
        assert config.transcript_processing_batch_size == 10

    def test_positive_validation(self):
        """Test positive values validation."""
        with pytest.raises(ValidationError):
            SessionLifecycleConfig(stale_session_timeout_hours=0)


class TestMemoryConfig:
    """Tests for MemoryConfig."""

    def test_default_values(self):
        """Test default memory config."""
        config = MemoryConfig()
        assert config.enabled is True
        assert config.auto_extract is True
        assert config.injection_limit == 10
        assert config.importance_threshold == 0.3
        assert config.decay_enabled is True
        assert config.decay_rate == 0.05
        assert config.decay_floor == 0.1

    def test_injection_limit_validation(self):
        """Test injection limit validation."""
        with pytest.raises(ValidationError):
            MemoryConfig(injection_limit=-1)

    def test_probability_validation(self):
        """Test probability fields validation."""
        with pytest.raises(ValidationError):
            MemoryConfig(importance_threshold=1.5)
        with pytest.raises(ValidationError):
            MemoryConfig(decay_rate=-0.1)


# ==============================================================================
# Additional tests for config module decomposition coverage (gt-dfa0d7)
# These tests verify all config classes can be instantiated correctly
# ==============================================================================


class TestCompactHandoffConfig:
    """Tests for CompactHandoffConfig."""

    def test_default_values(self):
        """Test default compact handoff config."""
        config = CompactHandoffConfig()
        assert config.enabled is True
        assert config.prompt is None  # Deprecated

    def test_custom_values(self):
        """Test custom compact handoff config."""
        config = CompactHandoffConfig(enabled=False)
        assert config.enabled is False


class TestContextInjectionConfig:
    """Tests for ContextInjectionConfig."""

    def test_default_values(self):
        """Test default context injection config."""
        config = ContextInjectionConfig()
        assert config.enabled is True
        assert config.default_source == "summary_markdown"
        assert config.max_file_size == 51200
        assert config.max_content_size == 51200
        assert config.max_transcript_messages == 100

    def test_positive_validation(self):
        """Test positive value validation."""
        with pytest.raises(ValidationError):
            ContextInjectionConfig(max_file_size=0)
        with pytest.raises(ValidationError):
            ContextInjectionConfig(max_content_size=-1)
        with pytest.raises(ValidationError):
            ContextInjectionConfig(max_transcript_messages=0)


class TestToolSummarizerConfig:
    """Tests for ToolSummarizerConfig."""

    def test_default_values(self):
        """Test default tool summarizer config."""
        config = ToolSummarizerConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-haiku-4-5"
        assert "180 characters" in config.prompt


class TestGobbyTasksConfig:
    """Tests for GobbyTasksConfig."""

    def test_default_values(self):
        """Test default gobby tasks config."""
        config = GobbyTasksConfig()
        assert config.enabled is True
        assert config.show_result_on_create is False
        assert isinstance(config.expansion, TaskExpansionConfig)
        assert isinstance(config.validation, TaskValidationConfig)

    def test_nested_configs(self):
        """Test nested expansion and validation configs."""
        config = GobbyTasksConfig(
            expansion=TaskExpansionConfig(enabled=False),
            validation=TaskValidationConfig(enabled=False),
        )
        assert config.expansion.enabled is False
        assert config.validation.enabled is False


class TestWebhookEndpointConfig:
    """Tests for WebhookEndpointConfig."""

    def test_required_fields(self):
        """Test required fields."""
        config = WebhookEndpointConfig(name="test", url="https://example.com")
        assert config.name == "test"
        assert config.url == "https://example.com"
        assert config.timeout == 10.0
        assert config.retry_count == 3
        assert config.retry_delay == 1.0
        assert config.can_block is False
        assert config.enabled is True

    def test_custom_values(self):
        """Test custom webhook config."""
        config = WebhookEndpointConfig(
            name="custom",
            url="https://api.example.com/hook",
            events=["session-start", "session-end"],
            timeout=30.0,
            retry_count=5,
            can_block=True,
        )
        assert len(config.events) == 2
        assert config.timeout == 30.0
        assert config.retry_count == 5
        assert config.can_block is True


class TestWebhooksConfig:
    """Tests for WebhooksConfig."""

    def test_default_values(self):
        """Test default webhooks config."""
        config = WebhooksConfig()
        assert config.enabled is True
        assert config.endpoints == []
        assert config.default_timeout == 10.0
        assert config.async_dispatch is True

    def test_with_endpoints(self):
        """Test webhooks config with endpoints."""
        config = WebhooksConfig(
            endpoints=[
                WebhookEndpointConfig(name="test1", url="https://a.com"),
                WebhookEndpointConfig(name="test2", url="https://b.com"),
            ]
        )
        assert len(config.endpoints) == 2


class TestPluginItemConfig:
    """Tests for PluginItemConfig."""

    def test_default_values(self):
        """Test default plugin item config."""
        config = PluginItemConfig()
        assert config.enabled is True
        assert config.config == {}

    def test_with_custom_config(self):
        """Test plugin item with custom config."""
        config = PluginItemConfig(
            enabled=False,
            config={"key": "value", "nested": {"a": 1}},
        )
        assert config.enabled is False
        assert config.config["key"] == "value"
        assert config.config["nested"]["a"] == 1


class TestPluginsConfig:
    """Tests for PluginsConfig."""

    def test_default_values(self):
        """Test default plugins config."""
        config = PluginsConfig()
        assert config.enabled is False  # Disabled by default for security
        assert "~/.gobby/plugins" in config.plugin_dirs
        assert ".gobby/plugins" in config.plugin_dirs
        assert config.auto_discover is True
        assert config.plugins == {}

    def test_with_plugin_configs(self):
        """Test plugins config with individual plugins."""
        config = PluginsConfig(
            enabled=True,
            plugins={
                "my-plugin": PluginItemConfig(config={"debug": True}),
                "other-plugin": PluginItemConfig(enabled=False),
            },
        )
        assert config.enabled is True
        assert len(config.plugins) == 2
        assert config.plugins["my-plugin"].config["debug"] is True
        assert config.plugins["other-plugin"].enabled is False


class TestMemorySyncConfig:
    """Tests for MemorySyncConfig."""

    def test_default_values(self):
        """Test default memory sync config."""
        config = MemorySyncConfig()
        assert config.enabled is True
        assert config.export_debounce == 5.0

    def test_debounce_validation(self):
        """Test export debounce validation."""
        with pytest.raises(ValidationError):
            MemorySyncConfig(export_debounce=-1.0)


class TestMetricsConfig:
    """Tests for MetricsConfig."""

    def test_default_values(self):
        """Test default metrics config."""
        config = MetricsConfig()
        assert config.list_limit == 10000

    def test_list_limit_validation(self):
        """Test list_limit must be non-negative."""
        config = MetricsConfig(list_limit=0)  # 0 is valid (unbounded)
        assert config.list_limit == 0

        with pytest.raises(ValidationError):
            MetricsConfig(list_limit=-1)


# ==============================================================================
# Cross-module reference tests (ensure DaemonConfig wires everything correctly)
# ==============================================================================


class TestDaemonConfigComposition:
    """Tests for DaemonConfig composition with sub-configs."""

    def test_all_sub_configs_accessible(self):
        """Test all sub-configs are accessible from DaemonConfig."""
        config = DaemonConfig()

        # Network/server
        assert isinstance(config.websocket, WebSocketSettings)
        assert isinstance(config.logging, LoggingSettings)

        # Session
        assert isinstance(config.compact_handoff, CompactHandoffConfig)
        assert isinstance(config.context_injection, ContextInjectionConfig)
        assert isinstance(config.session_summary, SessionSummaryConfig)
        assert isinstance(config.session_lifecycle, SessionLifecycleConfig)
        assert isinstance(config.message_tracking, MessageTrackingConfig)

        # MCP
        assert isinstance(config.mcp_client_proxy, MCPClientProxyConfig)
        assert isinstance(config.import_mcp_server, ImportMCPServerConfig)
        assert isinstance(config.tool_summarizer, ToolSummarizerConfig)

        # Tasks
        assert isinstance(config.gobby_tasks, GobbyTasksConfig)
        assert isinstance(config.gobby_tasks.expansion, TaskExpansionConfig)
        assert isinstance(config.gobby_tasks.validation, TaskValidationConfig)

        # LLM
        assert isinstance(config.llm_providers, LLMProvidersConfig)
        assert isinstance(config.title_synthesis, TitleSynthesisConfig)
        assert isinstance(config.code_execution, CodeExecutionConfig)
        assert isinstance(config.recommend_tools, RecommendToolsConfig)

        # Hooks
        assert isinstance(config.hook_extensions, HookExtensionsConfig)
        assert isinstance(config.hook_extensions.websocket, WebSocketBroadcastConfig)
        assert isinstance(config.hook_extensions.webhooks, WebhooksConfig)
        assert isinstance(config.hook_extensions.plugins, PluginsConfig)

        # Workflow
        assert isinstance(config.workflow, WorkflowConfig)
        assert isinstance(config.metrics, MetricsConfig)

        # Memory
        assert isinstance(config.memory, MemoryConfig)
        assert isinstance(config.memory_sync, MemorySyncConfig)

    def test_getters_return_correct_configs(self):
        """Test all getter methods return correct configs."""
        config = DaemonConfig()

        assert config.get_code_execution_config() is config.code_execution
        assert config.get_recommend_tools_config() is config.recommend_tools
        assert config.get_tool_summarizer_config() is config.tool_summarizer
        assert config.get_import_mcp_server_config() is config.import_mcp_server
        assert config.get_mcp_client_proxy_config() is config.mcp_client_proxy
        assert config.get_memory_config() is config.memory
        assert config.get_memory_sync_config() is config.memory_sync
        assert config.get_gobby_tasks_config() is config.gobby_tasks
        assert config.get_metrics_config() is config.metrics

    def test_yaml_round_trip(self, temp_dir: Path):
        """Test config survives YAML serialization round-trip."""
        config = DaemonConfig(
            daemon_port=9000,
            logging=LoggingSettings(level="debug"),
            memory=MemoryConfig(injection_limit=20),
        )

        # Save
        config_file = temp_dir / "roundtrip.yaml"
        save_config(config, str(config_file))

        # Load
        loaded = load_config(config_file=str(config_file))

        assert loaded.daemon_port == 9000
        assert loaded.logging.level == "debug"
        assert loaded.memory.injection_limit == 20


class TestAllConfigClassesInstantiate:
    """Verify all 31 config classes can be instantiated with defaults."""

    def test_all_classes_instantiate(self):
        """Test all config classes instantiate without error."""
        # This test ensures the baseline works before extraction
        configs = [
            WebSocketSettings(),
            LoggingSettings(),
            CompactHandoffConfig(),
            ContextInjectionConfig(),
            SessionSummaryConfig(),
            CodeExecutionConfig(),
            ToolSummarizerConfig(),
            RecommendToolsConfig(),
            ImportMCPServerConfig(),
            MCPClientProxyConfig(),
            GobbyTasksConfig(),
            LLMProviderConfig(models="test-model"),  # Required field
            LLMProvidersConfig(),
            TitleSynthesisConfig(),
            WebSocketBroadcastConfig(),
            WebhookEndpointConfig(name="test", url="https://test.com"),  # Required
            WebhooksConfig(),
            PluginItemConfig(),
            PluginsConfig(),
            HookExtensionsConfig(),
            TaskExpansionConfig(),
            TaskValidationConfig(),
            WorkflowConfig(),
            MessageTrackingConfig(),
            SessionLifecycleConfig(),
            MetricsConfig(),
            MemoryConfig(),
            MemorySyncConfig(),
            DaemonConfig(),
        ]

        assert len(configs) == 29
        for config in configs:
            assert config is not None
