"""Tests for ServiceContainer lazy pipeline executor creation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.app_context import ServiceContainer

pytestmark = pytest.mark.unit


def _make_container(**overrides):
    """Create a minimal ServiceContainer with sensible defaults."""
    defaults = {
        "config": MagicMock(),
        "database": MagicMock(),
        "session_manager": MagicMock(),
        "task_manager": MagicMock(),
    }
    defaults.update(overrides)
    return ServiceContainer(**defaults)


class TestGetPipelineExecutor:
    """Tests for ServiceContainer.get_pipeline_executor()."""

    def test_returns_existing_executor(self) -> None:
        """If pipeline_executor is set at startup, return it directly."""
        existing_executor = MagicMock()
        container = _make_container(pipeline_executor=existing_executor)

        result = container.get_pipeline_executor()

        assert result is existing_executor

    def test_returns_none_without_workflow_loader(self) -> None:
        """Returns None when workflow_loader is unavailable."""
        container = _make_container(workflow_loader=None)

        result = container.get_pipeline_executor(project_id="proj-1")

        assert result is None

    def test_returns_none_without_database(self) -> None:
        """Returns None when database is unavailable."""
        container = _make_container(database=None, workflow_loader=MagicMock())

        result = container.get_pipeline_executor(project_id="proj-1")

        assert result is None

    def test_lazy_creation_wires_event_callback(self) -> None:
        """Lazily created executor gets event_callback wired from websocket_server."""
        mock_ws = MagicMock()
        mock_ws.broadcast_pipeline_event = AsyncMock()
        mock_db = MagicMock()
        mock_loader = MagicMock()
        mock_llm = MagicMock()

        container = _make_container(
            database=mock_db,
            workflow_loader=mock_loader,
            llm_service=mock_llm,
            websocket_server=mock_ws,
            pipeline_execution_manager=MagicMock(),
        )

        executor = container.get_pipeline_executor(project_id="proj-1")

        assert executor is not None
        assert executor.event_callback is not None

    def test_lazy_creation_wires_tool_proxy_getter(self) -> None:
        """Lazily created executor gets tool_proxy_getter wired from container."""
        mock_tool_proxy_getter = MagicMock()
        mock_db = MagicMock()
        mock_loader = MagicMock()

        container = _make_container(
            database=mock_db,
            workflow_loader=mock_loader,
            tool_proxy_getter=mock_tool_proxy_getter,
            pipeline_execution_manager=MagicMock(),
        )

        executor = container.get_pipeline_executor(project_id="proj-1")

        assert executor is not None
        assert executor.tool_proxy_getter is mock_tool_proxy_getter

    def test_lazy_creation_caches_executor(self) -> None:
        """Subsequent calls return the same cached executor."""
        container = _make_container(
            database=MagicMock(),
            workflow_loader=MagicMock(),
            pipeline_execution_manager=MagicMock(),
        )

        first = container.get_pipeline_executor(project_id="proj-1")
        second = container.get_pipeline_executor(project_id="proj-1")

        assert first is not None
        assert first is second

    def test_lazy_creation_different_projects_get_separate_executors(self) -> None:
        """Different project IDs get separate cached executors."""
        container = _make_container(
            database=MagicMock(),
            workflow_loader=MagicMock(),
            llm_service=MagicMock(),
        )

        exec_a = container.get_pipeline_executor(project_id="proj-a")
        exec_b = container.get_pipeline_executor(project_id="proj-b")

        assert exec_a is not None
        assert exec_b is not None
        assert exec_a is not exec_b

    def test_lazy_creation_without_websocket_no_event_callback(self) -> None:
        """Lazily created executor without websocket_server has no event_callback."""
        container = _make_container(
            database=MagicMock(),
            workflow_loader=MagicMock(),
            websocket_server=None,
            pipeline_execution_manager=MagicMock(),
        )

        executor = container.get_pipeline_executor(project_id="proj-1")

        assert executor is not None
        assert executor.event_callback is None

    def test_lazy_creation_without_tool_proxy_getter(self) -> None:
        """Lazily created executor without tool_proxy_getter has None."""
        container = _make_container(
            database=MagicMock(),
            workflow_loader=MagicMock(),
            tool_proxy_getter=None,
            pipeline_execution_manager=MagicMock(),
        )

        executor = container.get_pipeline_executor(project_id="proj-1")

        assert executor is not None
        assert executor.tool_proxy_getter is None

    def test_uses_container_project_id_as_fallback(self) -> None:
        """When no project_id is passed, falls back to container's project_id."""
        container = _make_container(
            database=MagicMock(),
            workflow_loader=MagicMock(),
            project_id="default-proj",
            pipeline_execution_manager=MagicMock(),
        )

        executor = container.get_pipeline_executor()

        assert executor is not None
        # Verify it was cached under the container's project_id
        assert "default-proj" in container._project_infra_cache
