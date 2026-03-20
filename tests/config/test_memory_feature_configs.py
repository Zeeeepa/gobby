"""Tests for memory-related feature configurations."""

import pytest

from gobby.config.features import (
    KnowledgeGraphQueueConfig,
    MemoryEntityExtractionConfig,
    MemoryExtractionConfig,
)

pytestmark = pytest.mark.unit


class TestMemoryExtractionConfig:
    """Tests for MemoryExtractionConfig."""

    def test_exists(self) -> None:
        config = MemoryExtractionConfig()
        assert config is not None

    def test_defaults(self) -> None:
        config = MemoryExtractionConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "haiku"

    def test_overridable(self) -> None:
        config = MemoryExtractionConfig(
            enabled=False,
            provider="gemini",
            model="gemini-2.0-flash",
        )
        assert config.enabled is False
        assert config.provider == "gemini"
        assert config.model == "gemini-2.0-flash"


class TestKnowledgeGraphQueueConfig:
    """Tests for KnowledgeGraphQueueConfig."""

    def test_exists(self) -> None:
        config = KnowledgeGraphQueueConfig()
        assert config is not None

    def test_defaults(self) -> None:
        config = KnowledgeGraphQueueConfig()
        assert config.interval_minutes == 30
        assert config.batch_size == 20

    def test_overridable(self) -> None:
        config = KnowledgeGraphQueueConfig(
            interval_minutes=15,
            batch_size=50,
        )
        assert config.interval_minutes == 15
        assert config.batch_size == 50


class TestMemoryEntityExtractionConfig:
    """Tests for MemoryEntityExtractionConfig."""

    def test_exists(self) -> None:
        config = MemoryEntityExtractionConfig()
        assert config is not None

    def test_defaults(self) -> None:
        config = MemoryEntityExtractionConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "haiku"

    def test_prompt_path_default(self) -> None:
        config = MemoryEntityExtractionConfig()
        assert hasattr(config, "prompt_path")

    def test_overridable(self) -> None:
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

    def test_knowledge_graph_queue_on_daemon_config(self) -> None:
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()
        assert hasattr(config, "knowledge_graph_queue")
        assert isinstance(config.knowledge_graph_queue, KnowledgeGraphQueueConfig)

    def test_memory_entity_extraction_on_daemon_config(self) -> None:
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()
        assert hasattr(config, "memory_entity_extraction")
        assert isinstance(config.memory_entity_extraction, MemoryEntityExtractionConfig)

    def test_memory_extraction_on_daemon_config(self) -> None:
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()
        assert hasattr(config, "memory_extraction")
        assert isinstance(config.memory_extraction, MemoryExtractionConfig)
        assert config.memory_extraction.enabled is True
