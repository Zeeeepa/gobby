"""
Tests for the example_notify plugin demonstrating workflow action patterns.
"""

from __future__ import annotations

import json

# Import the plugin class
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "examples" / "plugins"))
from example_notify import HTTP_NOTIFY_SCHEMA, LOG_METRIC_SCHEMA, ExampleNotifyPlugin

pytestmark = pytest.mark.unit

class TestPluginLoading:
    """Tests for plugin initialization and loading."""

    def test_plugin_has_required_attributes(self) -> None:
        """Plugin should have name, version, and description."""
        plugin = ExampleNotifyPlugin()

        assert plugin.name == "example-notify"
        assert plugin.version == "1.0.0"
        assert plugin.description != ""

    def test_on_load_registers_actions(self) -> None:
        """on_load should register http_notify and log_metric actions."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({})

        assert "http_notify" in plugin._actions
        assert "log_metric" in plugin._actions

    def test_on_load_with_custom_config(self) -> None:
        """on_load should apply custom configuration."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load(
            {
                "default_channel": "#alerts",
                "log_file": "/tmp/custom_metrics.log",
            }
        )

        assert plugin.default_channel == "#alerts"
        assert plugin.log_file == Path("/tmp/custom_metrics.log")

    def test_actions_have_schemas(self) -> None:
        """Registered actions should have non-empty schemas."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({})

        http_action = plugin._actions["http_notify"]
        log_action = plugin._actions["log_metric"]

        assert http_action.schema == HTTP_NOTIFY_SCHEMA
        assert log_action.schema == LOG_METRIC_SCHEMA
        assert "url" in http_action.schema["properties"]
        assert "metric_name" in log_action.schema["properties"]


class TestSchemaValidation:
    """Tests for input schema validation."""

    def test_http_notify_validates_required_url(self) -> None:
        """http_notify should require url parameter."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({})

        action = plugin._actions["http_notify"]

        # Missing required 'url'
        is_valid, error = action.validate_input({})
        assert not is_valid
        assert "url" in error

        # With required 'url'
        is_valid, error = action.validate_input({"url": "https://example.com"})
        assert is_valid
        assert error is None

    def test_log_metric_validates_required_fields(self) -> None:
        """log_metric should require metric_name and value."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({})

        action = plugin._actions["log_metric"]

        # Missing all required
        is_valid, error = action.validate_input({})
        assert not is_valid

        # Missing value
        is_valid, error = action.validate_input({"metric_name": "test"})
        assert not is_valid
        assert "value" in error

        # All required present
        is_valid, error = action.validate_input(
            {
                "metric_name": "test",
                "value": 42,
            }
        )
        assert is_valid

    def test_validates_type_mismatch(self) -> None:
        """Schema validation should catch type mismatches."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({})

        action = plugin._actions["log_metric"]

        # value should be number, not string
        is_valid, error = action.validate_input(
            {
                "metric_name": "test",
                "value": "not a number",
            }
        )
        assert not is_valid
        assert "type" in error.lower()

    def test_validates_optional_fields(self) -> None:
        """Optional fields should validate when provided."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({})

        action = plugin._actions["http_notify"]

        # Valid with optional fields
        is_valid, error = action.validate_input(
            {
                "url": "https://example.com",
                "method": "POST",
                "payload": {"key": "value"},
                "headers": {"Authorization": "Bearer token"},
            }
        )
        assert is_valid


class TestHttpNotifyAction:
    """Tests for the http_notify action executor."""

    @pytest.mark.asyncio
    async def test_http_notify_returns_success(self):
        """http_notify should return success with simulated flag."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({})

        context = MagicMock()
        context.session_id = "test-session"

        result = await plugin._execute_http_notify(
            context=context,
            url="https://hooks.slack.com/services/xxx",
            method="POST",
            payload={"text": "Hello"},
        )

        assert result["success"] is True
        assert result["simulated"] is True
        assert result["method"] == "POST"
        assert result["url"] == "https://hooks.slack.com/services/xxx"

    @pytest.mark.asyncio
    async def test_http_notify_uses_default_channel(self):
        """http_notify should use default channel when not specified."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({"default_channel": "#alerts"})

        context = MagicMock()

        result = await plugin._execute_http_notify(
            context=context,
            url="https://example.com",
        )

        assert result["channel"] == "#alerts"

    @pytest.mark.asyncio
    async def test_http_notify_uses_custom_channel(self):
        """http_notify should use custom channel when specified."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({"default_channel": "#general"})

        context = MagicMock()

        result = await plugin._execute_http_notify(
            context=context,
            url="https://example.com",
            channel="#custom",
        )

        assert result["channel"] == "#custom"

    @pytest.mark.asyncio
    async def test_http_notify_increments_counter(self):
        """http_notify should increment notification counter."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({})

        context = MagicMock()

        assert plugin._notifications_sent == 0

        await plugin._execute_http_notify(context=context, url="https://example.com")
        assert plugin._notifications_sent == 1

        await plugin._execute_http_notify(context=context, url="https://example.com")
        assert plugin._notifications_sent == 2


class TestLogMetricAction:
    """Tests for the log_metric action executor."""

    @pytest.mark.asyncio
    async def test_log_metric_writes_to_file(self):
        """log_metric should write metric to log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "metrics.log"

            plugin = ExampleNotifyPlugin()
            plugin.on_load({"log_file": str(log_file)})

            context = MagicMock()
            context.session_id = "test-session"

            result = await plugin._execute_log_metric(
                context=context,
                metric_name="build_duration",
                value=42.5,
                tags={"project": "test"},
            )

            assert result["success"] is True
            assert result["metric_name"] == "build_duration"
            assert result["value"] == 42.5

            # Verify file contents
            assert log_file.exists()
            with open(log_file) as f:
                line = f.readline()
                entry = json.loads(line)

            assert entry["metric"] == "build_duration"
            assert entry["value"] == 42.5
            assert entry["tags"] == {"project": "test"}
            assert entry["session_id"] == "test-session"

    @pytest.mark.asyncio
    async def test_log_metric_appends_to_existing(self):
        """log_metric should append to existing log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "metrics.log"

            plugin = ExampleNotifyPlugin()
            plugin.on_load({"log_file": str(log_file)})

            context = MagicMock()
            context.session_id = "test-session"

            # Log multiple metrics
            await plugin._execute_log_metric(context=context, metric_name="metric1", value=1)
            await plugin._execute_log_metric(context=context, metric_name="metric2", value=2)

            # Verify file has both entries
            with open(log_file) as f:
                lines = f.readlines()

            assert len(lines) == 2
            assert json.loads(lines[0])["metric"] == "metric1"
            assert json.loads(lines[1])["metric"] == "metric2"

    @pytest.mark.asyncio
    async def test_log_metric_creates_directory(self):
        """log_metric should create parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "nested" / "deep" / "metrics.log"

            plugin = ExampleNotifyPlugin()
            plugin.on_load({"log_file": str(log_file)})

            context = MagicMock()
            context.session_id = None

            result = await plugin._execute_log_metric(context=context, metric_name="test", value=1)

            assert result["success"] is True
            assert log_file.exists()

    @pytest.mark.asyncio
    async def test_log_metric_increments_counter(self):
        """log_metric should increment metrics counter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "metrics.log"

            plugin = ExampleNotifyPlugin()
            plugin.on_load({"log_file": str(log_file)})

            context = MagicMock()
            context.session_id = None

            assert plugin._metrics_logged == 0

            await plugin._execute_log_metric(context=context, metric_name="test", value=1)
            assert plugin._metrics_logged == 1


class TestWorkflowIntegration:
    """Tests for integration with the workflow engine."""

    def test_actions_accessible_via_get_action(self) -> None:
        """Actions should be retrievable via get_action()."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({})

        http_action = plugin.get_action("http_notify")
        log_action = plugin.get_action("log_metric")
        missing_action = plugin.get_action("nonexistent")

        assert http_action is not None
        assert http_action.name == "http_notify"
        assert log_action is not None
        assert log_action.name == "log_metric"
        assert missing_action is None

    def test_action_has_correct_plugin_name(self) -> None:
        """Actions should reference their parent plugin."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({})

        action = plugin.get_action("http_notify")

        assert action.plugin_name == "example-notify"

    @pytest.mark.asyncio
    async def test_action_handler_is_callable(self):
        """Action handlers should be directly callable."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({})

        action = plugin.get_action("http_notify")
        context = MagicMock()
        context.session_id = "test"

        # Call the handler directly
        result = await action.handler(
            context=context,
            url="https://example.com",
        )

        assert result["success"] is True


class TestPluginLifecycle:
    """Tests for plugin lifecycle management."""

    def test_on_unload_logs_stats(self, caplog) -> None:
        """on_unload should log statistics."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({})

        # Simulate some activity
        plugin._notifications_sent = 5
        plugin._metrics_logged = 10

        with caplog.at_level("INFO"):
            plugin.on_unload()

        assert "notifications_sent=5" in caplog.text
        assert "metrics_logged=10" in caplog.text

    def test_register_duplicate_action_raises(self) -> None:
        """Registering duplicate action should raise ValueError."""
        plugin = ExampleNotifyPlugin()
        plugin.on_load({})

        # Try to register same action again
        with pytest.raises(ValueError, match="already registered"):
            plugin.register_workflow_action(
                action_type="http_notify",
                schema={},
                executor_fn=lambda ctx: None,
            )


class TestSchemaDefinitions:
    """Tests for the schema constants."""

    def test_http_notify_schema_structure(self) -> None:
        """HTTP_NOTIFY_SCHEMA should have correct structure."""
        assert HTTP_NOTIFY_SCHEMA["type"] == "object"
        assert "properties" in HTTP_NOTIFY_SCHEMA
        assert "required" in HTTP_NOTIFY_SCHEMA
        assert HTTP_NOTIFY_SCHEMA["required"] == ["url"]

        props = HTTP_NOTIFY_SCHEMA["properties"]
        assert "url" in props
        assert "method" in props
        assert "payload" in props
        assert "headers" in props
        assert "channel" in props

    def test_log_metric_schema_structure(self) -> None:
        """LOG_METRIC_SCHEMA should have correct structure."""
        assert LOG_METRIC_SCHEMA["type"] == "object"
        assert "properties" in LOG_METRIC_SCHEMA
        assert "required" in LOG_METRIC_SCHEMA
        assert set(LOG_METRIC_SCHEMA["required"]) == {"metric_name", "value"}

        props = LOG_METRIC_SCHEMA["properties"]
        assert "metric_name" in props
        assert "value" in props
        assert "tags" in props
        assert props["value"]["type"] == "number"
