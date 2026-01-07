"""
Tests for config/extensions.py module.

RED PHASE: Tests initially import from extensions.py (should fail),
then will pass once plugin/webhook config classes are extracted from app.py.
"""

import pytest
from pydantic import ValidationError

# =============================================================================
# Import Tests (RED phase targets)
# =============================================================================


class TestWebSocketBroadcastConfigImport:
    """Test that WebSocketBroadcastConfig can be imported from the extensions module."""

    def test_import_from_extensions_module(self) -> None:
        """Test importing WebSocketBroadcastConfig from config.extensions (RED phase target)."""
        from gobby.config.extensions import WebSocketBroadcastConfig

        assert WebSocketBroadcastConfig is not None


class TestWebhookEndpointConfigImport:
    """Test that WebhookEndpointConfig can be imported from the extensions module."""

    def test_import_from_extensions_module(self) -> None:
        """Test importing WebhookEndpointConfig from config.extensions (RED phase target)."""
        from gobby.config.extensions import WebhookEndpointConfig

        assert WebhookEndpointConfig is not None


class TestWebhooksConfigImport:
    """Test that WebhooksConfig can be imported from the extensions module."""

    def test_import_from_extensions_module(self) -> None:
        """Test importing WebhooksConfig from config.extensions (RED phase target)."""
        from gobby.config.extensions import WebhooksConfig

        assert WebhooksConfig is not None


class TestPluginItemConfigImport:
    """Test that PluginItemConfig can be imported from the extensions module."""

    def test_import_from_extensions_module(self) -> None:
        """Test importing PluginItemConfig from config.extensions (RED phase target)."""
        from gobby.config.extensions import PluginItemConfig

        assert PluginItemConfig is not None


class TestPluginsConfigImport:
    """Test that PluginsConfig can be imported from the extensions module."""

    def test_import_from_extensions_module(self) -> None:
        """Test importing PluginsConfig from config.extensions (RED phase target)."""
        from gobby.config.extensions import PluginsConfig

        assert PluginsConfig is not None


class TestHookExtensionsConfigImport:
    """Test that HookExtensionsConfig can be imported from the extensions module."""

    def test_import_from_extensions_module(self) -> None:
        """Test importing HookExtensionsConfig from config.extensions (RED phase target)."""
        from gobby.config.extensions import HookExtensionsConfig

        assert HookExtensionsConfig is not None


# =============================================================================
# WebSocketBroadcastConfig Tests
# =============================================================================


class TestWebSocketBroadcastConfigDefaults:
    """Test WebSocketBroadcastConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test WebSocketBroadcastConfig creates with all defaults."""
        from gobby.config.extensions import WebSocketBroadcastConfig

        config = WebSocketBroadcastConfig()
        assert config.enabled is True
        assert "session-start" in config.broadcast_events
        assert "session-end" in config.broadcast_events
        assert "pre-tool-use" in config.broadcast_events
        assert "post-tool-use" in config.broadcast_events
        assert config.include_payload is True


class TestWebSocketBroadcastConfigCustom:
    """Test WebSocketBroadcastConfig with custom values."""

    def test_disabled_broadcast(self) -> None:
        """Test disabling broadcast."""
        from gobby.config.extensions import WebSocketBroadcastConfig

        config = WebSocketBroadcastConfig(enabled=False)
        assert config.enabled is False

    def test_custom_events(self) -> None:
        """Test custom broadcast events."""
        from gobby.config.extensions import WebSocketBroadcastConfig

        config = WebSocketBroadcastConfig(broadcast_events=["session-start"])
        assert config.broadcast_events == ["session-start"]

    def test_no_payload(self) -> None:
        """Test disabling payload inclusion."""
        from gobby.config.extensions import WebSocketBroadcastConfig

        config = WebSocketBroadcastConfig(include_payload=False)
        assert config.include_payload is False


# =============================================================================
# WebhookEndpointConfig Tests
# =============================================================================


class TestWebhookEndpointConfigDefaults:
    """Test WebhookEndpointConfig default values."""

    def test_required_fields(self) -> None:
        """Test WebhookEndpointConfig requires name and url."""
        from gobby.config.extensions import WebhookEndpointConfig

        config = WebhookEndpointConfig(
            name="test-webhook",
            url="https://example.com/webhook",
        )
        assert config.name == "test-webhook"
        assert config.url == "https://example.com/webhook"
        assert config.events == []
        assert config.headers == {}
        assert config.timeout == 10.0
        assert config.retry_count == 3
        assert config.retry_delay == 1.0
        assert config.can_block is False
        assert config.enabled is True


class TestWebhookEndpointConfigCustom:
    """Test WebhookEndpointConfig with custom values."""

    def test_custom_timeout(self) -> None:
        """Test setting custom timeout."""
        from gobby.config.extensions import WebhookEndpointConfig

        config = WebhookEndpointConfig(
            name="test",
            url="https://example.com",
            timeout=30.0,
        )
        assert config.timeout == 30.0

    def test_custom_retry_settings(self) -> None:
        """Test custom retry settings."""
        from gobby.config.extensions import WebhookEndpointConfig

        config = WebhookEndpointConfig(
            name="test",
            url="https://example.com",
            retry_count=5,
            retry_delay=2.0,
        )
        assert config.retry_count == 5
        assert config.retry_delay == 2.0

    def test_can_block_enabled(self) -> None:
        """Test enabling can_block."""
        from gobby.config.extensions import WebhookEndpointConfig

        config = WebhookEndpointConfig(
            name="blocking-webhook",
            url="https://example.com",
            can_block=True,
        )
        assert config.can_block is True

    def test_custom_headers(self) -> None:
        """Test custom headers."""
        from gobby.config.extensions import WebhookEndpointConfig

        config = WebhookEndpointConfig(
            name="test",
            url="https://example.com",
            headers={"Authorization": "Bearer token123"},
        )
        assert config.headers["Authorization"] == "Bearer token123"

    def test_custom_events(self) -> None:
        """Test custom events filter."""
        from gobby.config.extensions import WebhookEndpointConfig

        config = WebhookEndpointConfig(
            name="test",
            url="https://example.com",
            events=["session-start", "session-end"],
        )
        assert config.events == ["session-start", "session-end"]


class TestWebhookEndpointConfigValidation:
    """Test WebhookEndpointConfig validation."""

    def test_timeout_range(self) -> None:
        """Test timeout must be between 1 and 60."""
        from gobby.config.extensions import WebhookEndpointConfig

        # Too low
        with pytest.raises(ValidationError):
            WebhookEndpointConfig(name="test", url="https://example.com", timeout=0.5)

        # Too high
        with pytest.raises(ValidationError):
            WebhookEndpointConfig(name="test", url="https://example.com", timeout=61.0)

        # Valid boundaries
        config = WebhookEndpointConfig(name="test", url="https://example.com", timeout=1.0)
        assert config.timeout == 1.0
        config = WebhookEndpointConfig(name="test", url="https://example.com", timeout=60.0)
        assert config.timeout == 60.0

    def test_retry_count_range(self) -> None:
        """Test retry_count must be between 0 and 10."""
        from gobby.config.extensions import WebhookEndpointConfig

        with pytest.raises(ValidationError):
            WebhookEndpointConfig(name="test", url="https://example.com", retry_count=-1)

        with pytest.raises(ValidationError):
            WebhookEndpointConfig(name="test", url="https://example.com", retry_count=11)

        config = WebhookEndpointConfig(name="test", url="https://example.com", retry_count=0)
        assert config.retry_count == 0
        config = WebhookEndpointConfig(name="test", url="https://example.com", retry_count=10)
        assert config.retry_count == 10

    def test_retry_delay_range(self) -> None:
        """Test retry_delay must be between 0.1 and 30."""
        from gobby.config.extensions import WebhookEndpointConfig

        with pytest.raises(ValidationError):
            WebhookEndpointConfig(name="test", url="https://example.com", retry_delay=0.05)

        with pytest.raises(ValidationError):
            WebhookEndpointConfig(name="test", url="https://example.com", retry_delay=31.0)


# =============================================================================
# WebhooksConfig Tests
# =============================================================================


class TestWebhooksConfigDefaults:
    """Test WebhooksConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test WebhooksConfig creates with all defaults."""
        from gobby.config.extensions import WebhooksConfig

        config = WebhooksConfig()
        assert config.enabled is True
        assert config.endpoints == []
        assert config.default_timeout == 10.0
        assert config.async_dispatch is True


class TestWebhooksConfigCustom:
    """Test WebhooksConfig with custom values."""

    def test_disabled_webhooks(self) -> None:
        """Test disabling webhooks."""
        from gobby.config.extensions import WebhooksConfig

        config = WebhooksConfig(enabled=False)
        assert config.enabled is False

    def test_with_endpoints(self) -> None:
        """Test with webhook endpoints."""
        from gobby.config.extensions import WebhookEndpointConfig, WebhooksConfig

        endpoint = WebhookEndpointConfig(
            name="test-webhook",
            url="https://example.com/webhook",
        )
        config = WebhooksConfig(endpoints=[endpoint])
        assert len(config.endpoints) == 1
        assert config.endpoints[0].name == "test-webhook"

    def test_sync_dispatch(self) -> None:
        """Test synchronous dispatch."""
        from gobby.config.extensions import WebhooksConfig

        config = WebhooksConfig(async_dispatch=False)
        assert config.async_dispatch is False


class TestWebhooksConfigValidation:
    """Test WebhooksConfig validation."""

    def test_default_timeout_range(self) -> None:
        """Test default_timeout must be between 1 and 60."""
        from gobby.config.extensions import WebhooksConfig

        with pytest.raises(ValidationError):
            WebhooksConfig(default_timeout=0.5)

        with pytest.raises(ValidationError):
            WebhooksConfig(default_timeout=61.0)


# =============================================================================
# PluginItemConfig Tests
# =============================================================================


class TestPluginItemConfigDefaults:
    """Test PluginItemConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test PluginItemConfig creates with all defaults."""
        from gobby.config.extensions import PluginItemConfig

        config = PluginItemConfig()
        assert config.enabled is True
        assert config.config == {}


class TestPluginItemConfigCustom:
    """Test PluginItemConfig with custom values."""

    def test_disabled_plugin(self) -> None:
        """Test disabling a plugin."""
        from gobby.config.extensions import PluginItemConfig

        config = PluginItemConfig(enabled=False)
        assert config.enabled is False

    def test_custom_config(self) -> None:
        """Test plugin-specific configuration."""
        from gobby.config.extensions import PluginItemConfig

        config = PluginItemConfig(config={"key": "value", "nested": {"a": 1}})
        assert config.config["key"] == "value"
        assert config.config["nested"]["a"] == 1


# =============================================================================
# PluginsConfig Tests
# =============================================================================


class TestPluginsConfigDefaults:
    """Test PluginsConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test PluginsConfig creates with all defaults."""
        from gobby.config.extensions import PluginsConfig

        config = PluginsConfig()
        assert config.enabled is False  # Disabled by default for security
        assert "~/.gobby/plugins" in config.plugin_dirs
        assert ".gobby/plugins" in config.plugin_dirs
        assert config.auto_discover is True
        assert config.plugins == {}


class TestPluginsConfigCustom:
    """Test PluginsConfig with custom values."""

    def test_enabled_plugins(self) -> None:
        """Test enabling plugin system."""
        from gobby.config.extensions import PluginsConfig

        config = PluginsConfig(enabled=True)
        assert config.enabled is True

    def test_custom_plugin_dirs(self) -> None:
        """Test custom plugin directories."""
        from gobby.config.extensions import PluginsConfig

        config = PluginsConfig(plugin_dirs=["/custom/plugins", "./my-plugins"])
        assert config.plugin_dirs == ["/custom/plugins", "./my-plugins"]

    def test_disabled_auto_discover(self) -> None:
        """Test disabling auto-discovery."""
        from gobby.config.extensions import PluginsConfig

        config = PluginsConfig(auto_discover=False)
        assert config.auto_discover is False

    def test_with_plugin_configs(self) -> None:
        """Test with per-plugin configurations."""
        from gobby.config.extensions import PluginItemConfig, PluginsConfig

        plugin_config = PluginItemConfig(config={"api_key": "secret"})
        config = PluginsConfig(plugins={"my-plugin": plugin_config})
        assert "my-plugin" in config.plugins
        assert config.plugins["my-plugin"].config["api_key"] == "secret"


# =============================================================================
# HookExtensionsConfig Tests
# =============================================================================


class TestHookExtensionsConfigDefaults:
    """Test HookExtensionsConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test HookExtensionsConfig creates with all defaults."""
        from gobby.config.extensions import HookExtensionsConfig

        config = HookExtensionsConfig()
        assert config.websocket is not None
        assert config.websocket.enabled is True
        assert config.webhooks is not None
        assert config.webhooks.enabled is True
        assert config.plugins is not None
        assert config.plugins.enabled is False  # Disabled by default


class TestHookExtensionsConfigCustom:
    """Test HookExtensionsConfig with custom values."""

    def test_custom_websocket_config(self) -> None:
        """Test custom websocket configuration."""
        from gobby.config.extensions import HookExtensionsConfig, WebSocketBroadcastConfig

        ws_config = WebSocketBroadcastConfig(enabled=False)
        config = HookExtensionsConfig(websocket=ws_config)
        assert config.websocket.enabled is False

    def test_custom_webhooks_config(self) -> None:
        """Test custom webhooks configuration."""
        from gobby.config.extensions import HookExtensionsConfig, WebhooksConfig

        webhooks = WebhooksConfig(enabled=False)
        config = HookExtensionsConfig(webhooks=webhooks)
        assert config.webhooks.enabled is False

    def test_custom_plugins_config(self) -> None:
        """Test custom plugins configuration."""
        from gobby.config.extensions import HookExtensionsConfig, PluginsConfig

        plugins = PluginsConfig(enabled=True)
        config = HookExtensionsConfig(plugins=plugins)
        assert config.plugins.enabled is True


# =============================================================================
# Baseline Tests (import from app.py)
# =============================================================================


class TestWebSocketBroadcastConfigFromAppPy:
    """Verify that tests pass when importing from app.py (reference implementation)."""

    def test_import_from_app_py(self) -> None:
        """Test importing WebSocketBroadcastConfig from app.py works (baseline)."""
        from gobby.config.app import WebSocketBroadcastConfig

        config = WebSocketBroadcastConfig()
        assert config.enabled is True


class TestWebhookEndpointConfigFromAppPy:
    """Verify WebhookEndpointConfig tests pass when importing from app.py."""

    def test_import_from_app_py(self) -> None:
        """Test importing WebhookEndpointConfig from app.py works (baseline)."""
        from gobby.config.app import WebhookEndpointConfig

        config = WebhookEndpointConfig(name="test", url="https://example.com")
        assert config.timeout == 10.0

    def test_validation_via_app_py(self) -> None:
        """Test validation works when imported from app.py."""
        from gobby.config.app import WebhookEndpointConfig

        with pytest.raises(ValidationError):
            WebhookEndpointConfig(name="test", url="https://example.com", timeout=0.5)


class TestWebhooksConfigFromAppPy:
    """Verify WebhooksConfig tests pass when importing from app.py."""

    def test_import_from_app_py(self) -> None:
        """Test importing WebhooksConfig from app.py works (baseline)."""
        from gobby.config.app import WebhooksConfig

        config = WebhooksConfig()
        assert config.enabled is True


class TestPluginsConfigFromAppPy:
    """Verify PluginsConfig tests pass when importing from app.py."""

    def test_import_from_app_py(self) -> None:
        """Test importing PluginsConfig from app.py works (baseline)."""
        from gobby.config.app import PluginsConfig

        config = PluginsConfig()
        assert config.enabled is False


class TestHookExtensionsConfigFromAppPy:
    """Verify HookExtensionsConfig tests pass when importing from app.py."""

    def test_import_from_app_py(self) -> None:
        """Test importing HookExtensionsConfig from app.py works (baseline)."""
        from gobby.config.app import HookExtensionsConfig

        config = HookExtensionsConfig()
        assert config.websocket is not None
