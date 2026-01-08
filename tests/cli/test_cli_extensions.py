"""Comprehensive tests for CLI extension commands (hooks, plugins, webhooks).

Tests for /Users/josh/Projects/gobby/src/gobby/cli/extensions.py

These tests use Click's CliRunner and mock external dependencies to test:
- hooks list/test commands
- plugins list/reload commands
- webhooks list/test commands
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli import cli
from gobby.cli.extensions import (
    _get_hook_description,
)
from gobby.hooks.events import HookEventType

# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_daemon_client():
    """Create a mock daemon client."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_config():
    """Create a mock daemon config."""
    config = MagicMock()
    config.daemon_port = 9876
    return config


# ==============================================================================
# Helper Function Tests
# ==============================================================================


class TestGetHookDescription:
    """Tests for _get_hook_description helper function."""

    def test_session_start_description(self):
        """Test description for SESSION_START event."""
        desc = _get_hook_description(HookEventType.SESSION_START)
        assert desc == "Fired when a new session starts"

    def test_session_end_description(self):
        """Test description for SESSION_END event."""
        desc = _get_hook_description(HookEventType.SESSION_END)
        assert desc == "Fired when a session ends"

    def test_before_agent_description(self):
        """Test description for BEFORE_AGENT event."""
        desc = _get_hook_description(HookEventType.BEFORE_AGENT)
        assert desc == "Fired before agent turn starts"

    def test_after_agent_description(self):
        """Test description for AFTER_AGENT event."""
        desc = _get_hook_description(HookEventType.AFTER_AGENT)
        assert desc == "Fired after agent turn completes"

    def test_stop_description(self):
        """Test description for STOP event."""
        desc = _get_hook_description(HookEventType.STOP)
        assert desc == "Fired when agent attempts to stop (can block)"

    def test_before_tool_description(self):
        """Test description for BEFORE_TOOL event."""
        desc = _get_hook_description(HookEventType.BEFORE_TOOL)
        assert desc == "Fired before a tool is executed (can block)"

    def test_after_tool_description(self):
        """Test description for AFTER_TOOL event."""
        desc = _get_hook_description(HookEventType.AFTER_TOOL)
        assert desc == "Fired after a tool completes"

    def test_before_tool_selection_description(self):
        """Test description for BEFORE_TOOL_SELECTION event."""
        desc = _get_hook_description(HookEventType.BEFORE_TOOL_SELECTION)
        assert desc == "Fired before tool selection (Gemini)"

    def test_before_model_description(self):
        """Test description for BEFORE_MODEL event."""
        desc = _get_hook_description(HookEventType.BEFORE_MODEL)
        assert desc == "Fired before model call (Gemini)"

    def test_after_model_description(self):
        """Test description for AFTER_MODEL event."""
        desc = _get_hook_description(HookEventType.AFTER_MODEL)
        assert desc == "Fired after model call (Gemini)"

    def test_pre_compact_description(self):
        """Test description for PRE_COMPACT event."""
        desc = _get_hook_description(HookEventType.PRE_COMPACT)
        assert desc == "Fired before session context is compacted"

    def test_notification_description(self):
        """Test description for NOTIFICATION event."""
        desc = _get_hook_description(HookEventType.NOTIFICATION)
        assert desc == "Notification event from CLI"

    def test_unknown_event_returns_empty(self):
        """Test that unknown events return empty string."""
        # Events not in the descriptions dict should return empty string
        desc = _get_hook_description(HookEventType.SUBAGENT_START)
        assert desc == ""

        desc = _get_hook_description(HookEventType.PERMISSION_REQUEST)
        assert desc == ""


# ==============================================================================
# Hooks Command Tests
# ==============================================================================


class TestHooksGroup:
    """Tests for the hooks command group."""

    def test_hooks_help(self, runner: CliRunner):
        """Test hooks --help displays help text."""
        result = runner.invoke(cli, ["hooks", "--help"])
        assert result.exit_code == 0
        assert "Manage hook system configuration and testing" in result.output


class TestHooksListCommand:
    """Tests for the hooks list command."""

    def test_hooks_list_help(self, runner: CliRunner):
        """Test hooks list --help displays help text."""
        result = runner.invoke(cli, ["hooks", "list", "--help"])
        assert result.exit_code == 0
        assert "List supported hook event types" in result.output

    @patch("gobby.cli.load_config")
    def test_hooks_list_default_output(
        self,
        mock_load_config: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
    ):
        """Test hooks list with default (human-readable) output."""
        mock_load_config.return_value = mock_config

        result = runner.invoke(cli, ["hooks", "list"])

        assert result.exit_code == 0
        assert "Supported Hook Event Types:" in result.output
        # Check that event types are listed
        assert "session_start" in result.output
        assert "session_end" in result.output
        assert "before_tool" in result.output
        assert "after_tool" in result.output

    @patch("gobby.cli.load_config")
    def test_hooks_list_json_output(
        self,
        mock_load_config: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
    ):
        """Test hooks list with JSON output."""
        mock_load_config.return_value = mock_config

        result = runner.invoke(cli, ["hooks", "list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0

        # Check structure of hook entries
        first_hook = data[0]
        assert "name" in first_hook
        assert "description" in first_hook

        # Verify all expected hook types are present
        hook_names = [h["name"] for h in data]
        assert "session_start" in hook_names
        assert "session_end" in hook_names
        assert "before_tool" in hook_names
        assert "after_tool" in hook_names
        assert "stop" in hook_names

    @patch("gobby.cli.load_config")
    def test_hooks_list_contains_descriptions(
        self,
        mock_load_config: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
    ):
        """Test that hooks list includes descriptions."""
        mock_load_config.return_value = mock_config

        result = runner.invoke(cli, ["hooks", "list"])

        assert result.exit_code == 0
        # Check for some descriptions
        assert "Fired when a new session starts" in result.output
        assert "Fired before a tool is executed" in result.output


class TestHooksTestCommand:
    """Tests for the hooks test command."""

    def test_hooks_test_help(self, runner: CliRunner):
        """Test hooks test --help displays help text."""
        result = runner.invoke(cli, ["hooks", "test", "--help"])
        assert result.exit_code == 0
        assert "Test a hook by sending a test event" in result.output
        assert "--source" in result.output
        assert "claude" in result.output
        assert "gemini" in result.output
        assert "codex" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_hooks_test_success(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test hooks test with successful response."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "continue": True,
            "reason": "Test hook executed successfully",
        }

        result = runner.invoke(cli, ["hooks", "test", "session-start"])

        assert result.exit_code == 0
        assert "Hook test: session-start" in result.output
        assert "Source: claude" in result.output
        assert "Continue: True" in result.output
        assert "Reason: Test hook executed successfully" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_hooks_test_with_source_option(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test hooks test with different source option."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {"continue": True}

        result = runner.invoke(cli, ["hooks", "test", "before-tool", "-s", "gemini"])

        assert result.exit_code == 0
        assert "Source: gemini" in result.output

        # Verify API was called with correct source
        mock_call_api.assert_called_once()
        call_args = mock_call_api.call_args
        assert call_args[1]["json_data"]["source"] == "gemini"

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_hooks_test_tool_event_adds_tool_name(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test hooks test with tool-related event includes tool_name."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {"continue": True}

        result = runner.invoke(cli, ["hooks", "test", "before-tool"])

        assert result.exit_code == 0

        # Verify API was called with tool_name in input_data
        mock_call_api.assert_called_once()
        call_args = mock_call_api.call_args
        input_data = call_args[1]["json_data"]["input_data"]
        assert input_data["tool_name"] == "test_tool"

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_hooks_test_non_tool_event_no_tool_name(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test hooks test with non-tool event does not include tool_name."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {"continue": True}

        result = runner.invoke(cli, ["hooks", "test", "session-start"])

        assert result.exit_code == 0

        # Verify API was called without tool_name
        mock_call_api.assert_called_once()
        call_args = mock_call_api.call_args
        input_data = call_args[1]["json_data"]["input_data"]
        assert input_data["tool_name"] is None

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_hooks_test_json_output(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test hooks test with JSON output."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "continue": True,
            "reason": "success",
            "inject_context": {"key": "value"},
        }

        result = runner.invoke(cli, ["hooks", "test", "session-start", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["continue"] is True
        assert data["reason"] == "success"
        assert data["inject_context"] == {"key": "value"}

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_hooks_test_with_inject_context(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test hooks test displays inject_context in output."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "continue": True,
            "inject_context": "Some context data that will be truncated if too long",
        }

        result = runner.invoke(cli, ["hooks", "test", "session-start"])

        assert result.exit_code == 0
        assert "Context:" in result.output

    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_hooks_test_daemon_not_running(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test hooks test when daemon is not running."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = False

        result = runner.invoke(cli, ["hooks", "test", "session-start"])

        assert result.exit_code == 1

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_hooks_test_api_failure(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test hooks test when API call fails."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = None

        result = runner.invoke(cli, ["hooks", "test", "session-start"])

        assert result.exit_code == 1
        assert "Failed to execute test hook" in result.output


# ==============================================================================
# Plugins Command Tests
# ==============================================================================


class TestPluginsGroup:
    """Tests for the plugins command group."""

    def test_plugins_help(self, runner: CliRunner):
        """Test plugins --help displays help text."""
        result = runner.invoke(cli, ["plugins", "--help"])
        assert result.exit_code == 0
        assert "Manage Python hook plugins" in result.output


class TestPluginsListCommand:
    """Tests for the plugins list command."""

    def test_plugins_list_help(self, runner: CliRunner):
        """Test plugins list --help displays help text."""
        result = runner.invoke(cli, ["plugins", "list", "--help"])
        assert result.exit_code == 0
        assert "List loaded plugins" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_plugins_list_disabled(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test plugins list when plugin system is disabled."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {"enabled": False, "plugins": []}

        result = runner.invoke(cli, ["plugins", "list"])

        assert result.exit_code == 0
        assert "Plugin system is disabled" in result.output
        assert "plugins.enabled: true" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_plugins_list_no_plugins(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test plugins list with no plugins loaded."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "enabled": True,
            "plugins": [],
            "plugin_dirs": ["/home/user/.gobby/plugins", ".gobby/plugins"],
        }

        result = runner.invoke(cli, ["plugins", "list"])

        assert result.exit_code == 0
        assert "No plugins loaded" in result.output
        assert "Plugin directories:" in result.output
        assert "/home/user/.gobby/plugins" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_plugins_list_with_plugins(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test plugins list with plugins loaded."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "enabled": True,
            "plugins": [
                {
                    "name": "test-plugin",
                    "version": "1.0.0",
                    "description": "A test plugin",
                    "handlers": ["session_start", "before_tool"],
                    "actions": [{"name": "action1"}, {"name": "action2"}],
                },
                {
                    "name": "simple-plugin",
                    "version": "0.1.0",
                },
            ],
        }

        result = runner.invoke(cli, ["plugins", "list"])

        assert result.exit_code == 0
        assert "Loaded Plugins (2):" in result.output
        assert "test-plugin v1.0.0" in result.output
        assert "A test plugin" in result.output
        assert "Handlers: 2" in result.output
        assert "Actions: action1, action2" in result.output
        assert "simple-plugin v0.1.0" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_plugins_list_json_output(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test plugins list with JSON output."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "enabled": True,
            "plugins": [{"name": "test-plugin", "version": "1.0.0"}],
        }

        result = runner.invoke(cli, ["plugins", "list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["enabled"] is True
        assert len(data["plugins"]) == 1
        assert data["plugins"][0]["name"] == "test-plugin"

    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_plugins_list_daemon_not_running(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test plugins list when daemon is not running."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = False

        result = runner.invoke(cli, ["plugins", "list"])

        assert result.exit_code == 1

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_plugins_list_api_failure(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test plugins list when API call fails."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = None

        result = runner.invoke(cli, ["plugins", "list"])

        assert result.exit_code == 1
        assert "Failed to list plugins" in result.output


class TestPluginsReloadCommand:
    """Tests for the plugins reload command."""

    def test_plugins_reload_help(self, runner: CliRunner):
        """Test plugins reload --help displays help text."""
        result = runner.invoke(cli, ["plugins", "reload", "--help"])
        assert result.exit_code == 0
        assert "Reload a plugin by name" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_plugins_reload_success(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test plugins reload with successful response."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {"success": True, "version": "1.2.0"}

        result = runner.invoke(cli, ["plugins", "reload", "my-plugin"])

        assert result.exit_code == 0
        assert "Plugin 'my-plugin' reloaded successfully" in result.output
        assert "Version: 1.2.0" in result.output

        # Verify API was called with correct plugin name
        mock_call_api.assert_called_once()
        call_args = mock_call_api.call_args
        assert call_args[1]["json_data"]["name"] == "my-plugin"

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_plugins_reload_success_no_version(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test plugins reload success without version in response."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {"success": True}

        result = runner.invoke(cli, ["plugins", "reload", "my-plugin"])

        assert result.exit_code == 0
        assert "Plugin 'my-plugin' reloaded successfully" in result.output
        assert "Version:" not in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_plugins_reload_failure(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test plugins reload when reload fails."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "success": False,
            "error": "Plugin not found",
        }

        result = runner.invoke(cli, ["plugins", "reload", "nonexistent-plugin"])

        assert result.exit_code == 1
        assert "Failed to reload plugin: Plugin not found" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_plugins_reload_failure_unknown_error(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test plugins reload when reload fails with no error message."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {"success": False}

        result = runner.invoke(cli, ["plugins", "reload", "my-plugin"])

        assert result.exit_code == 1
        assert "Failed to reload plugin: Unknown error" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_plugins_reload_json_output(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test plugins reload with JSON output."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {"success": True, "version": "1.0.0"}

        result = runner.invoke(cli, ["plugins", "reload", "my-plugin", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert data["version"] == "1.0.0"

    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_plugins_reload_daemon_not_running(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test plugins reload when daemon is not running."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = False

        result = runner.invoke(cli, ["plugins", "reload", "my-plugin"])

        assert result.exit_code == 1

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_plugins_reload_api_failure(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test plugins reload when API call fails."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = None

        result = runner.invoke(cli, ["plugins", "reload", "my-plugin"])

        assert result.exit_code == 1
        assert "Failed to reload plugin: my-plugin" in result.output

    def test_plugins_reload_requires_plugin_name(self, runner: CliRunner):
        """Test plugins reload requires plugin name argument."""
        result = runner.invoke(cli, ["plugins", "reload"])

        assert result.exit_code == 2
        assert "Missing argument" in result.output


# ==============================================================================
# Webhooks Command Tests
# ==============================================================================


class TestWebhooksGroup:
    """Tests for the webhooks command group."""

    def test_webhooks_help(self, runner: CliRunner):
        """Test webhooks --help displays help text."""
        result = runner.invoke(cli, ["webhooks", "--help"])
        assert result.exit_code == 0
        assert "Manage webhook endpoints" in result.output


class TestWebhooksListCommand:
    """Tests for the webhooks list command."""

    def test_webhooks_list_help(self, runner: CliRunner):
        """Test webhooks list --help displays help text."""
        result = runner.invoke(cli, ["webhooks", "list", "--help"])
        assert result.exit_code == 0
        assert "List configured webhook endpoints" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_list_disabled(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks list when webhook system is disabled."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {"enabled": False, "endpoints": []}

        result = runner.invoke(cli, ["webhooks", "list"])

        assert result.exit_code == 0
        assert "Webhook system is disabled" in result.output
        assert "hook_extensions.webhooks.enabled: true" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_list_no_endpoints(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks list with no endpoints configured."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {"enabled": True, "endpoints": []}

        result = runner.invoke(cli, ["webhooks", "list"])

        assert result.exit_code == 0
        assert "No webhook endpoints configured" in result.output
        assert "Configure webhooks in ~/.gobby/config.yaml:" in result.output
        assert "hook_extensions:" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_list_with_endpoints(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks list with endpoints configured."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "enabled": True,
            "endpoints": [
                {
                    "name": "slack-webhook",
                    "url": "https://hooks.slack.com/services/xxx",
                    "enabled": True,
                    "events": ["session_start", "session_end"],
                    "can_block": False,
                },
                {
                    "name": "custom-webhook",
                    "url": "https://example.com/webhook",
                    "enabled": False,
                    "events": [],
                    "can_block": True,
                },
            ],
        }

        result = runner.invoke(cli, ["webhooks", "list"])

        assert result.exit_code == 0
        assert "Webhook Endpoints (2):" in result.output
        # First endpoint
        assert "slack-webhook [enabled]" in result.output
        assert "URL: https://hooks.slack.com/services/xxx" in result.output
        assert "Events: session_start, session_end" in result.output
        # Second endpoint
        assert "custom-webhook [disabled]" in result.output
        assert "URL: https://example.com/webhook" in result.output
        assert "Events: all" in result.output
        assert "Can block: yes" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_list_endpoint_no_url(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks list with endpoint missing URL."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "enabled": True,
            "endpoints": [
                {
                    "name": "incomplete-webhook",
                    "enabled": True,
                },
            ],
        }

        result = runner.invoke(cli, ["webhooks", "list"])

        assert result.exit_code == 0
        assert "URL: not configured" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_list_json_output(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks list with JSON output."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "enabled": True,
            "endpoints": [
                {
                    "name": "test-webhook",
                    "url": "https://example.com/webhook",
                }
            ],
        }

        result = runner.invoke(cli, ["webhooks", "list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["enabled"] is True
        assert len(data["endpoints"]) == 1
        assert data["endpoints"][0]["name"] == "test-webhook"

    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_list_daemon_not_running(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks list when daemon is not running."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = False

        result = runner.invoke(cli, ["webhooks", "list"])

        assert result.exit_code == 1

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_list_api_failure(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks list when API call fails."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = None

        result = runner.invoke(cli, ["webhooks", "list"])

        assert result.exit_code == 1
        assert "Failed to list webhooks" in result.output


class TestWebhooksTestCommand:
    """Tests for the webhooks test command."""

    def test_webhooks_test_help(self, runner: CliRunner):
        """Test webhooks test --help displays help text."""
        result = runner.invoke(cli, ["webhooks", "test", "--help"])
        assert result.exit_code == 0
        assert "Test a webhook endpoint" in result.output
        assert "--event" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_test_success(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks test with successful response."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "success": True,
            "status_code": 200,
            "response_time_ms": 150.5,
        }

        result = runner.invoke(cli, ["webhooks", "test", "my-webhook"])

        assert result.exit_code == 0
        assert "Webhook 'my-webhook' test successful!" in result.output
        assert "Status: 200" in result.output
        assert "Response time: 150ms" in result.output

        # Verify API was called with correct payload
        mock_call_api.assert_called_once()
        call_args = mock_call_api.call_args
        assert call_args[1]["json_data"]["name"] == "my-webhook"
        assert call_args[1]["json_data"]["event_type"] == "notification"

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_test_with_event_option(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks test with custom event type."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {"success": True, "status_code": 200}

        result = runner.invoke(cli, ["webhooks", "test", "my-webhook", "-e", "session_start"])

        assert result.exit_code == 0

        # Verify API was called with correct event type
        mock_call_api.assert_called_once()
        call_args = mock_call_api.call_args
        assert call_args[1]["json_data"]["event_type"] == "session_start"

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_test_success_no_response_time(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks test success without response time."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {"success": True, "status_code": 200}

        result = runner.invoke(cli, ["webhooks", "test", "my-webhook"])

        assert result.exit_code == 0
        assert "Webhook 'my-webhook' test successful!" in result.output
        assert "Response time:" not in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_test_failure(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks test when webhook fails."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "success": False,
            "error": "Connection refused",
            "status_code": None,
        }

        result = runner.invoke(cli, ["webhooks", "test", "my-webhook"])

        assert result.exit_code == 1
        assert "Webhook test failed: Connection refused" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_test_failure_with_status_code(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks test failure with status code."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "success": False,
            "error": "Not Found",
            "status_code": 404,
        }

        result = runner.invoke(cli, ["webhooks", "test", "my-webhook"])

        assert result.exit_code == 1
        assert "Webhook test failed: Not Found" in result.output
        assert "Status: 404" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_test_failure_unknown_error(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks test failure with no error message."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {"success": False}

        result = runner.invoke(cli, ["webhooks", "test", "my-webhook"])

        assert result.exit_code == 1
        assert "Webhook test failed: Unknown error" in result.output

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_test_json_output(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks test with JSON output."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = {
            "success": True,
            "status_code": 200,
            "response_time_ms": 50.0,
        }

        result = runner.invoke(cli, ["webhooks", "test", "my-webhook", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert data["status_code"] == 200
        assert data["response_time_ms"] == 50.0

    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_test_daemon_not_running(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks test when daemon is not running."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = False

        result = runner.invoke(cli, ["webhooks", "test", "my-webhook"])

        assert result.exit_code == 1

    @patch("gobby.cli.extensions.call_mcp_api")
    @patch("gobby.cli.extensions.check_daemon_running")
    @patch("gobby.cli.extensions.get_daemon_client")
    @patch("gobby.cli.load_config")
    def test_webhooks_test_api_failure(
        self,
        mock_load_config: MagicMock,
        mock_get_client: MagicMock,
        mock_check_daemon: MagicMock,
        mock_call_api: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_daemon_client: MagicMock,
    ):
        """Test webhooks test when API call fails."""
        mock_load_config.return_value = mock_config
        mock_get_client.return_value = mock_daemon_client
        mock_check_daemon.return_value = True
        mock_call_api.return_value = None

        result = runner.invoke(cli, ["webhooks", "test", "my-webhook"])

        assert result.exit_code == 1
        assert "Failed to test webhook: my-webhook" in result.output

    def test_webhooks_test_requires_webhook_name(self, runner: CliRunner):
        """Test webhooks test requires webhook name argument."""
        result = runner.invoke(cli, ["webhooks", "test"])

        assert result.exit_code == 2
        assert "Missing argument" in result.output


# ==============================================================================
# Integration Tests - Command Groups Registration
# ==============================================================================


class TestCommandGroupsRegistration:
    """Tests verifying command groups are properly registered with CLI."""

    def test_hooks_registered_in_cli(self, runner: CliRunner):
        """Test that hooks command group is registered in main CLI."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "hooks" in result.output

    def test_plugins_registered_in_cli(self, runner: CliRunner):
        """Test that plugins command group is registered in main CLI."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "plugins" in result.output

    def test_webhooks_registered_in_cli(self, runner: CliRunner):
        """Test that webhooks command group is registered in main CLI."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "webhooks" in result.output

    def test_hooks_subcommands_registered(self, runner: CliRunner):
        """Test that hooks subcommands are registered."""
        result = runner.invoke(cli, ["hooks", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "test" in result.output

    def test_plugins_subcommands_registered(self, runner: CliRunner):
        """Test that plugins subcommands are registered."""
        result = runner.invoke(cli, ["plugins", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "reload" in result.output

    def test_webhooks_subcommands_registered(self, runner: CliRunner):
        """Test that webhooks subcommands are registered."""
        result = runner.invoke(cli, ["webhooks", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "test" in result.output
