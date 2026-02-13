"""
Tests for config.py MCP tools module.

Tests the config tools that provide read/write access to daemon configuration.
"""

from pathlib import Path

import pytest

from gobby.config.app import DaemonConfig
from gobby.mcp_proxy.tools.config import create_config_registry
from gobby.storage.config_store import ConfigStore
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit


@pytest.fixture
def temp_db(tmp_path: Path) -> LocalDatabase:
    """Create a temporary database with schema."""
    db_path = tmp_path / "test.db"
    db = LocalDatabase(db_path)
    run_migrations(db)
    return db


@pytest.fixture
def config_store(temp_db: LocalDatabase) -> ConfigStore:
    """Create a ConfigStore backed by temp database."""
    return ConfigStore(temp_db)


@pytest.fixture
def config_state() -> dict[str, DaemonConfig]:
    """Mutable state holder for tracking config updates."""
    return {"config": DaemonConfig()}


@pytest.fixture
def config_registry(config_store: ConfigStore, config_state: dict[str, DaemonConfig]):
    """Create a config registry with test fixtures."""
    return create_config_registry(
        config=config_state["config"],
        config_store=config_store,
        config_setter=lambda c: config_state.__setitem__("config", c),
    )


class TestGetConfig:
    """Tests for get_config tool."""

    def test_get_config_returns_value(self, config_registry) -> None:
        """Test get_config returns a known config value."""
        tool = config_registry.get_tool("get_config")
        result = tool(key="daemon_port")

        assert result["success"] is True
        assert result["key"] == "daemon_port"
        assert result["value"] == 60887

    def test_get_config_nested_value(self, config_registry) -> None:
        """Test get_config returns nested config values."""
        tool = config_registry.get_tool("get_config")
        result = tool(key="logging.level")

        assert result["success"] is True
        assert result["key"] == "logging.level"

    def test_get_config_missing_key(self, config_registry) -> None:
        """Test get_config returns error for missing key."""
        tool = config_registry.get_tool("get_config")
        result = tool(key="nonexistent.key.path")

        assert result["success"] is False
        assert "not found" in result["error"]


class TestGetConfigSection:
    """Tests for get_config_section tool."""

    def test_get_config_section_returns_nested_dict(self, config_registry) -> None:
        """Test get_config_section returns filtered nested dict."""
        tool = config_registry.get_tool("get_config_section")
        result = tool(prefix="logging")

        assert result["success"] is True
        assert result["prefix"] == "logging"
        assert isinstance(result["section"], dict)
        assert "level" in result["section"]

    def test_get_config_section_missing_prefix(self, config_registry) -> None:
        """Test get_config_section returns error for nonexistent prefix."""
        tool = config_registry.get_tool("get_config_section")
        result = tool(prefix="nonexistent_section")

        assert result["success"] is False
        assert "No keys found" in result["error"]

    def test_get_config_section_returns_subsection(self, config_registry) -> None:
        """Test get_config_section works with deeper prefixes."""
        tool = config_registry.get_tool("get_config_section")
        result = tool(prefix="conductor")

        assert result["success"] is True
        section = result["section"]
        assert "daily_budget_usd" in section


class TestSetConfig:
    """Tests for set_config tool."""

    def test_set_config_persists_to_db(
        self, config_registry, config_store: ConfigStore
    ) -> None:
        """Test set_config persists the value to the database."""
        tool = config_registry.get_tool("set_config")
        result = tool(key="daemon_port", value=61000)

        assert result["success"] is True
        assert result["value"] == 61000

        # Verify persisted in DB
        db_value = config_store.get("daemon_port")
        assert db_value == 61000

    def test_set_config_updates_in_memory(
        self, config_registry, config_state: dict[str, DaemonConfig]
    ) -> None:
        """Test set_config updates the in-memory config via config_setter."""
        tool = config_registry.get_tool("set_config")
        result = tool(key="daemon_port", value=61001)

        assert result["success"] is True
        assert config_state["config"].daemon_port == 61001

    def test_set_config_rejects_invalid_value(self, config_registry) -> None:
        """Test set_config rejects values that fail Pydantic validation."""
        tool = config_registry.get_tool("set_config")
        # Port must be 1024-65535
        result = tool(key="daemon_port", value=80)

        assert result["success"] is False
        assert "error" in result

    def test_set_config_nested_key(
        self, config_registry, config_store: ConfigStore, config_state: dict[str, DaemonConfig]
    ) -> None:
        """Test set_config works with nested dotted keys."""
        tool = config_registry.get_tool("set_config")
        result = tool(key="conductor.daily_budget_usd", value=100.0)

        assert result["success"] is True
        assert config_store.get("conductor.daily_budget_usd") == 100.0
        assert config_state["config"].conductor.daily_budget_usd == 100.0


class TestListConfigKeys:
    """Tests for list_config_keys tool."""

    def test_list_config_keys_empty(self, config_registry) -> None:
        """Test list_config_keys returns empty list when DB has no keys."""
        tool = config_registry.get_tool("list_config_keys")
        result = tool()

        assert result["success"] is True
        assert result["count"] == 0
        assert result["keys"] == []

    def test_list_config_keys_after_set(
        self, config_registry, config_store: ConfigStore
    ) -> None:
        """Test list_config_keys returns keys after setting values."""
        config_store.set("daemon_port", 60887)
        config_store.set("conductor.daily_budget_usd", 50.0)

        tool = config_registry.get_tool("list_config_keys")
        result = tool()

        assert result["success"] is True
        assert result["count"] == 2
        assert "daemon_port" in result["keys"]
        assert "conductor.daily_budget_usd" in result["keys"]

    def test_list_config_keys_with_prefix(
        self, config_registry, config_store: ConfigStore
    ) -> None:
        """Test list_config_keys filters by prefix."""
        config_store.set("conductor.daily_budget_usd", 50.0)
        config_store.set("conductor.warning_threshold", 0.8)
        config_store.set("daemon_port", 60887)

        tool = config_registry.get_tool("list_config_keys")
        result = tool(prefix="conductor")

        assert result["success"] is True
        assert result["count"] == 2
        assert all(k.startswith("conductor") for k in result["keys"])


class TestEnsureDefaults:
    """Tests for ensure_defaults tool."""

    def test_ensure_defaults_populates_missing_keys(
        self, config_registry, config_store: ConfigStore
    ) -> None:
        """Test ensure_defaults inserts Pydantic defaults for missing keys."""
        tool = config_registry.get_tool("ensure_defaults")
        result = tool(section="conductor")

        assert result["success"] is True
        assert result["inserted"] > 0
        assert "conductor.daily_budget_usd" in result["keys_inserted"]

        # Verify persisted in DB
        db_value = config_store.get("conductor.daily_budget_usd")
        assert db_value == 50.0

    def test_ensure_defaults_does_not_overwrite_existing(
        self, config_registry, config_store: ConfigStore
    ) -> None:
        """Test ensure_defaults skips keys that already exist in DB."""
        # Pre-set a custom value
        config_store.set("conductor.daily_budget_usd", 200.0)

        tool = config_registry.get_tool("ensure_defaults")
        result = tool(section="conductor")

        assert result["success"] is True
        # Should not have overwritten the existing key
        db_value = config_store.get("conductor.daily_budget_usd")
        assert db_value == 200.0

        # The pre-set key should not be in keys_inserted
        if result["inserted"] > 0:
            assert "conductor.daily_budget_usd" not in result["keys_inserted"]

    def test_ensure_defaults_all_present(
        self, config_registry, config_store: ConfigStore
    ) -> None:
        """Test ensure_defaults reports when all keys are already present."""
        # First call populates
        tool = config_registry.get_tool("ensure_defaults")
        tool(section="conductor")

        # Second call should find nothing to insert
        result = tool(section="conductor")
        assert result["success"] is True
        assert result["inserted"] == 0
        assert "already present" in result["message"]

    def test_ensure_defaults_invalid_section(self, config_registry) -> None:
        """Test ensure_defaults returns error for nonexistent section."""
        tool = config_registry.get_tool("ensure_defaults")
        result = tool(section="nonexistent_section")

        assert result["success"] is False
        assert "No default keys" in result["error"]
