"""Tests for memory-related feature configurations."""

import pytest

from gobby.config.features import (
    MemoryDedupDecisionConfig,
    MemoryEntityExtractionConfig,
    MemoryFactExtractionConfig,
)

pytestmark = pytest.mark.unit


class TestMemoryFactExtractionConfig:
    """Tests for MemoryFactExtractionConfig."""

    def test_exists(self) -> None:
        """MemoryFactExtractionConfig can be instantiated."""
        config = MemoryFactExtractionConfig()
        assert config is not None

    def test_defaults(self) -> None:
        """MemoryFactExtractionConfig has correct defaults."""
        config = MemoryFactExtractionConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-haiku-4-5"

    def test_prompt_path_default(self) -> None:
        """MemoryFactExtractionConfig has a prompt_path field."""
        config = MemoryFactExtractionConfig()
        assert hasattr(config, "prompt_path")

    def test_overridable(self) -> None:
        """MemoryFactExtractionConfig fields are independently configurable."""
        config = MemoryFactExtractionConfig(
            enabled=False,
            provider="gemini",
            model="gemini-2.0-flash",
        )
        assert config.enabled is False
        assert config.provider == "gemini"
        assert config.model == "gemini-2.0-flash"


class TestMemoryDedupDecisionConfig:
    """Tests for MemoryDedupDecisionConfig."""

    def test_exists(self) -> None:
        """MemoryDedupDecisionConfig can be instantiated."""
        config = MemoryDedupDecisionConfig()
        assert config is not None

    def test_defaults(self) -> None:
        """MemoryDedupDecisionConfig has correct defaults."""
        config = MemoryDedupDecisionConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-haiku-4-5"

    def test_prompt_path_default(self) -> None:
        """MemoryDedupDecisionConfig has a prompt_path field."""
        config = MemoryDedupDecisionConfig()
        assert hasattr(config, "prompt_path")

    def test_overridable(self) -> None:
        """MemoryDedupDecisionConfig fields are independently configurable."""
        config = MemoryDedupDecisionConfig(
            enabled=False,
            provider="litellm",
            model="gpt-4o-mini",
        )
        assert config.enabled is False
        assert config.provider == "litellm"
        assert config.model == "gpt-4o-mini"


class TestMemoryEntityExtractionConfig:
    """Tests for MemoryEntityExtractionConfig."""

    def test_exists(self) -> None:
        """MemoryEntityExtractionConfig can be instantiated."""
        config = MemoryEntityExtractionConfig()
        assert config is not None

    def test_defaults(self) -> None:
        """MemoryEntityExtractionConfig has correct defaults."""
        config = MemoryEntityExtractionConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-haiku-4-5"

    def test_prompt_path_default(self) -> None:
        """MemoryEntityExtractionConfig has a prompt_path field."""
        config = MemoryEntityExtractionConfig()
        assert hasattr(config, "prompt_path")

    def test_overridable(self) -> None:
        """MemoryEntityExtractionConfig fields are independently configurable."""
        config = MemoryEntityExtractionConfig(
            enabled=False,
            provider="codex",
            model="o3-mini",
        )
        assert config.enabled is False
        assert config.provider == "codex"
        assert config.model == "o3-mini"


class TestDaemonConfigIntegration:
    """Tests for memory feature configs in DaemonConfig."""

    def test_memory_fact_extraction_on_daemon_config(self) -> None:
        """DaemonConfig has memory_fact_extraction attribute."""
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()
        assert hasattr(config, "memory_fact_extraction")
        assert isinstance(config.memory_fact_extraction, MemoryFactExtractionConfig)

    def test_memory_dedup_decision_on_daemon_config(self) -> None:
        """DaemonConfig has memory_dedup_decision attribute."""
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()
        assert hasattr(config, "memory_dedup_decision")
        assert isinstance(config.memory_dedup_decision, MemoryDedupDecisionConfig)

    def test_memory_entity_extraction_on_daemon_config(self) -> None:
        """DaemonConfig has memory_entity_extraction attribute."""
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()
        assert hasattr(config, "memory_entity_extraction")
        assert isinstance(config.memory_entity_extraction, MemoryEntityExtractionConfig)
