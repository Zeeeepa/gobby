"""Tests for memory-related feature configurations."""

import pytest

from gobby.config.features import (
    KnowledgeGraphQueueConfig,
)

pytestmark = pytest.mark.unit


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


class TestDaemonConfigIntegration:
    """Tests for memory feature configs in DaemonConfig."""

    def test_knowledge_graph_queue_on_daemon_config(self) -> None:
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()
        assert hasattr(config, "knowledge_graph_queue")
        assert isinstance(config.knowledge_graph_queue, KnowledgeGraphQueueConfig)

    def test_no_memory_entity_extraction_on_daemon_config(self) -> None:
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()
        assert not hasattr(config, "memory_entity_extraction")
