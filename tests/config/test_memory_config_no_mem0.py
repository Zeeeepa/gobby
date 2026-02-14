"""Tests that MemoryConfig no longer has mem0 fields."""

from __future__ import annotations

import pytest

from gobby.config.persistence import MemoryConfig

pytestmark = pytest.mark.unit


class TestMem0FieldsRemoved:
    """Verify that mem0 fields are no longer present on MemoryConfig."""

    def test_no_mem0_url_field(self) -> None:
        """MemoryConfig should not have mem0_url field."""
        config = MemoryConfig()
        assert not hasattr(config, "mem0_url")

    def test_no_mem0_api_key_field(self) -> None:
        """MemoryConfig should not have mem0_api_key field."""
        config = MemoryConfig()
        assert not hasattr(config, "mem0_api_key")

    def test_no_mem0_timeout_field(self) -> None:
        """MemoryConfig should not have mem0_timeout field."""
        config = MemoryConfig()
        assert not hasattr(config, "mem0_timeout")

    def test_no_mem0_sync_interval_field(self) -> None:
        """MemoryConfig should not have mem0_sync_interval field."""
        config = MemoryConfig()
        assert not hasattr(config, "mem0_sync_interval")

    def test_no_mem0_sync_max_backoff_field(self) -> None:
        """MemoryConfig should not have mem0_sync_max_backoff field."""
        config = MemoryConfig()
        assert not hasattr(config, "mem0_sync_max_backoff")


class TestOldConfigGracefulIgnore:
    """Verify that old configs with mem0 fields don't crash."""

    def test_old_config_with_mem0_url_ignored(self) -> None:
        """MemoryConfig should gracefully ignore mem0_url from old configs."""
        config = MemoryConfig(mem0_url="http://localhost:8888")
        assert not hasattr(config, "mem0_url")

    def test_old_config_with_all_mem0_fields_ignored(self) -> None:
        """MemoryConfig should gracefully ignore all old mem0 fields."""
        config = MemoryConfig(
            mem0_url="http://localhost:8888",
            mem0_api_key="sk-test",
            mem0_timeout=30.0,
            mem0_sync_interval=5.0,
            mem0_sync_max_backoff=120.0,
        )
        # Should not crash, and fields should not be present
        assert not hasattr(config, "mem0_url")
        assert not hasattr(config, "mem0_api_key")

    def test_neo4j_fields_still_present(self) -> None:
        """Neo4j fields should still exist on MemoryConfig."""
        config = MemoryConfig(
            neo4j_url="http://localhost:8474",
            neo4j_auth="neo4j:password",
        )
        assert config.neo4j_url == "http://localhost:8474"
        assert config.neo4j_auth == "neo4j:password"
