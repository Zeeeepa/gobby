"""Tests for pipelines MCP tools.

TDD tests for the pipelines MCP registry and tools.
"""

from unittest.mock import MagicMock

import pytest

from gobby.workflows.definitions import PipelineDefinition, PipelineStep
from gobby.workflows.loader import DiscoveredWorkflow

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_loader():
    """Create a mock workflow loader."""
    loader = MagicMock()
    return loader


@pytest.fixture
def mock_executor():
    """Create a mock pipeline executor."""
    executor = MagicMock()
    return executor


@pytest.fixture
def mock_execution_manager():
    """Create a mock execution manager."""
    manager = MagicMock()
    return manager


class TestCreatePipelinesRegistry:
    """Tests for create_pipelines_registry function."""

    def test_returns_internal_tool_registry(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that create_pipelines_registry returns an InternalToolRegistry."""
        from gobby.mcp_proxy.tools.internal import InternalToolRegistry
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        assert isinstance(registry, InternalToolRegistry)

    def test_registry_has_list_pipelines_tool(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that list_pipelines tool is registered."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "list_pipelines" in tool_names

    def test_registry_name(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that registry has correct name."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        assert registry.name == "gobby-pipelines"


class TestListPipelinesTool:
    """Tests for the list_pipelines MCP tool."""

    @pytest.mark.asyncio
    async def test_list_pipelines_calls_discover(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that list_pipelines calls loader.discover_pipeline_workflows()."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        mock_loader.discover_pipeline_workflows.return_value = []

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        # Call the tool
        await registry.call("list_pipelines", {})

        mock_loader.discover_pipeline_workflows.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_pipelines_returns_pipeline_info(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that list_pipelines returns pipeline names and descriptions."""
        from pathlib import Path

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        # Create mock discovered pipelines
        pipeline1 = PipelineDefinition(
            name="deploy",
            description="Deploy to production",
            steps=[PipelineStep(id="step1", exec="echo deploy")],
        )
        pipeline2 = PipelineDefinition(
            name="test",
            description="Run test suite",
            steps=[PipelineStep(id="step1", exec="pytest")],
        )

        mock_loader.discover_pipeline_workflows.return_value = [
            DiscoveredWorkflow(
                name="deploy",
                definition=pipeline1,
                priority=100,
                is_project=False,
                path=Path("/workflows/deploy.yaml"),
            ),
            DiscoveredWorkflow(
                name="test",
                definition=pipeline2,
                priority=100,
                is_project=True,
                path=Path("/project/.gobby/workflows/test.yaml"),
            ),
        ]

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call("list_pipelines", {})

        assert result["success"] is True
        assert "pipelines" in result
        assert len(result["pipelines"]) == 2

        # Check pipeline info
        names = [p["name"] for p in result["pipelines"]]
        assert "deploy" in names
        assert "test" in names

        # Check descriptions are included
        deploy = next(p for p in result["pipelines"] if p["name"] == "deploy")
        assert deploy["description"] == "Deploy to production"

    @pytest.mark.asyncio
    async def test_list_pipelines_includes_is_project(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that list_pipelines indicates if pipeline is project-specific."""
        from pathlib import Path

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        pipeline = PipelineDefinition(
            name="local",
            steps=[PipelineStep(id="step1", exec="echo local")],
        )

        mock_loader.discover_pipeline_workflows.return_value = [
            DiscoveredWorkflow(
                name="local",
                definition=pipeline,
                priority=100,
                is_project=True,
                path=Path("/project/.gobby/workflows/local.yaml"),
            ),
        ]

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call("list_pipelines", {})

        assert result["pipelines"][0]["is_project"] is True

    @pytest.mark.asyncio
    async def test_list_pipelines_with_project_path(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that list_pipelines passes project_path to discover."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        mock_loader.discover_pipeline_workflows.return_value = []

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        await registry.call("list_pipelines", {"project_path": "/my/project"})

        mock_loader.discover_pipeline_workflows.assert_called_once_with(
            project_path="/my/project"
        )

    @pytest.mark.asyncio
    async def test_list_pipelines_empty_result(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that list_pipelines handles no pipelines found."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        mock_loader.discover_pipeline_workflows.return_value = []

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call("list_pipelines", {})

        assert result["success"] is True
        assert result["pipelines"] == []
