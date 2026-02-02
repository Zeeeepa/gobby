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

        # Reset mock after registry creation (which also calls discover for dynamic tools)
        mock_loader.discover_pipeline_workflows.reset_mock()

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

        # Reset mock after registry creation (which also calls discover for dynamic tools)
        mock_loader.discover_pipeline_workflows.reset_mock()

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


class TestRunPipelineTool:
    """Tests for the run_pipeline MCP tool."""

    def test_registry_has_run_pipeline_tool(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that run_pipeline tool is registered."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "run_pipeline" in tool_names

    @pytest.mark.asyncio
    async def test_run_pipeline_loads_pipeline(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that run_pipeline loads the pipeline via loader."""
        import asyncio
        from unittest.mock import AsyncMock

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        pipeline = PipelineDefinition(
            name="deploy",
            steps=[PipelineStep(id="step1", exec="echo deploy")],
        )
        mock_loader.load_pipeline.return_value = pipeline

        # Mock executor.execute as async
        execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            outputs_json='{"result": "success"}',
        )
        mock_executor.execute = AsyncMock(return_value=execution)

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        await registry.call(
            "run_pipeline",
            {"name": "deploy", "inputs": {}, "project_id": "proj-1"},
        )

        mock_loader.load_pipeline.assert_called_once_with("deploy")

    @pytest.mark.asyncio
    async def test_run_pipeline_calls_executor(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that run_pipeline calls executor.execute() with pipeline and inputs."""
        from unittest.mock import AsyncMock

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        pipeline = PipelineDefinition(
            name="deploy",
            steps=[PipelineStep(id="step1", exec="echo deploy")],
        )
        mock_loader.load_pipeline.return_value = pipeline

        execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            outputs_json='{"result": "success"}',
        )
        mock_executor.execute = AsyncMock(return_value=execution)

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        await registry.call(
            "run_pipeline",
            {"name": "deploy", "inputs": {"env": "prod"}, "project_id": "proj-1"},
        )

        mock_executor.execute.assert_called_once_with(
            pipeline=pipeline,
            inputs={"env": "prod"},
            project_id="proj-1",
        )

    @pytest.mark.asyncio
    async def test_run_pipeline_returns_completed_status(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that run_pipeline returns execution status and outputs for completed."""
        from unittest.mock import AsyncMock

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        pipeline = PipelineDefinition(
            name="deploy",
            steps=[PipelineStep(id="step1", exec="echo deploy")],
        )
        mock_loader.load_pipeline.return_value = pipeline

        execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            outputs_json='{"result": "success"}',
        )
        mock_executor.execute = AsyncMock(return_value=execution)

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "run_pipeline",
            {"name": "deploy", "inputs": {}, "project_id": "proj-1"},
        )

        assert result["success"] is True
        assert result["status"] == "completed"
        assert result["execution_id"] == "pe-abc123"
        assert result["outputs"] == {"result": "success"}

    @pytest.mark.asyncio
    async def test_run_pipeline_returns_waiting_approval(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that run_pipeline returns waiting_approval status when approval required."""
        from unittest.mock import AsyncMock

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry
        from gobby.workflows.pipeline_state import ApprovalRequired

        pipeline = PipelineDefinition(
            name="deploy",
            steps=[PipelineStep(id="step1", exec="echo deploy")],
        )
        mock_loader.load_pipeline.return_value = pipeline

        # Executor raises ApprovalRequired
        mock_executor.execute = AsyncMock(
            side_effect=ApprovalRequired(
                execution_id="pe-abc123",
                step_id="step1",
                token="approval-token-xyz",
                message="Manual approval required for deployment",
            )
        )

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "run_pipeline",
            {"name": "deploy", "inputs": {}, "project_id": "proj-1"},
        )

        assert result["success"] is True
        assert result["status"] == "waiting_approval"
        assert result["execution_id"] == "pe-abc123"
        assert result["token"] == "approval-token-xyz"
        assert result["message"] == "Manual approval required for deployment"
        assert result["step_id"] == "step1"

    @pytest.mark.asyncio
    async def test_run_pipeline_not_found(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that run_pipeline returns error when pipeline not found."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        mock_loader.load_pipeline.return_value = None

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "run_pipeline",
            {"name": "nonexistent", "inputs": {}, "project_id": "proj-1"},
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_run_pipeline_execution_error(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that run_pipeline returns error when execution fails."""
        from unittest.mock import AsyncMock

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        pipeline = PipelineDefinition(
            name="deploy",
            steps=[PipelineStep(id="step1", exec="echo deploy")],
        )
        mock_loader.load_pipeline.return_value = pipeline

        mock_executor.execute = AsyncMock(side_effect=RuntimeError("Execution failed"))

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "run_pipeline",
            {"name": "deploy", "inputs": {}, "project_id": "proj-1"},
        )

        assert result["success"] is False
        assert "execution failed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_run_pipeline_no_executor_configured(
        self, mock_loader, mock_execution_manager
    ) -> None:
        """Test that run_pipeline returns error when no executor configured."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=None,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "run_pipeline",
            {"name": "deploy", "inputs": {}, "project_id": "proj-1"},
        )

        assert result["success"] is False
        assert "executor" in result["error"].lower()


class TestApprovePipelineTool:
    """Tests for the approve_pipeline MCP tool."""

    def test_registry_has_approve_pipeline_tool(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that approve_pipeline tool is registered."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "approve_pipeline" in tool_names

    @pytest.mark.asyncio
    async def test_approve_pipeline_calls_executor_approve(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that approve_pipeline calls executor.approve()."""
        from unittest.mock import AsyncMock

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        mock_executor.approve = AsyncMock(return_value=execution)

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        await registry.call(
            "approve_pipeline",
            {"token": "approval-token-xyz", "approved_by": "user@example.com"},
        )

        mock_executor.approve.assert_called_once_with(
            token="approval-token-xyz",
            approved_by="user@example.com",
        )

    @pytest.mark.asyncio
    async def test_approve_pipeline_returns_execution_status(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that approve_pipeline returns execution status after approval."""
        from unittest.mock import AsyncMock

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            outputs_json='{"result": "deployed"}',
        )
        mock_executor.approve = AsyncMock(return_value=execution)

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "approve_pipeline",
            {"token": "approval-token-xyz"},
        )

        assert result["success"] is True
        assert result["status"] == "completed"
        assert result["execution_id"] == "pe-abc123"

    @pytest.mark.asyncio
    async def test_approve_pipeline_invalid_token(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that approve_pipeline returns error for invalid token."""
        from unittest.mock import AsyncMock

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        mock_executor.approve = AsyncMock(
            side_effect=ValueError("Invalid or expired token")
        )

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "approve_pipeline",
            {"token": "invalid-token"},
        )

        assert result["success"] is False
        assert "invalid" in result["error"].lower() or "token" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_approve_pipeline_no_executor(
        self, mock_loader, mock_execution_manager
    ) -> None:
        """Test that approve_pipeline returns error when no executor configured."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=None,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "approve_pipeline",
            {"token": "approval-token-xyz"},
        )

        assert result["success"] is False
        assert "executor" in result["error"].lower()


class TestRejectPipelineTool:
    """Tests for the reject_pipeline MCP tool."""

    def test_registry_has_reject_pipeline_tool(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that reject_pipeline tool is registered."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "reject_pipeline" in tool_names

    @pytest.mark.asyncio
    async def test_reject_pipeline_calls_executor_reject(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that reject_pipeline calls executor.reject()."""
        from unittest.mock import AsyncMock

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.CANCELLED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        mock_executor.reject = AsyncMock(return_value=execution)

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        await registry.call(
            "reject_pipeline",
            {"token": "approval-token-xyz", "rejected_by": "user@example.com"},
        )

        mock_executor.reject.assert_called_once_with(
            token="approval-token-xyz",
            rejected_by="user@example.com",
        )

    @pytest.mark.asyncio
    async def test_reject_pipeline_returns_cancelled_status(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that reject_pipeline returns cancelled status."""
        from unittest.mock import AsyncMock

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.CANCELLED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        mock_executor.reject = AsyncMock(return_value=execution)

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "reject_pipeline",
            {"token": "approval-token-xyz"},
        )

        assert result["success"] is True
        assert result["status"] == "cancelled"
        assert result["execution_id"] == "pe-abc123"

    @pytest.mark.asyncio
    async def test_reject_pipeline_invalid_token(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that reject_pipeline returns error for invalid token."""
        from unittest.mock import AsyncMock

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        mock_executor.reject = AsyncMock(
            side_effect=ValueError("Invalid or expired token")
        )

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "reject_pipeline",
            {"token": "invalid-token"},
        )

        assert result["success"] is False
        assert "invalid" in result["error"].lower() or "token" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_reject_pipeline_no_executor(
        self, mock_loader, mock_execution_manager
    ) -> None:
        """Test that reject_pipeline returns error when no executor configured."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=None,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "reject_pipeline",
            {"token": "approval-token-xyz"},
        )

        assert result["success"] is False
        assert "executor" in result["error"].lower()


class TestGetPipelineStatusTool:
    """Tests for the get_pipeline_status MCP tool."""

    def test_registry_has_get_pipeline_status_tool(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that get_pipeline_status tool is registered."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "get_pipeline_status" in tool_names

    @pytest.mark.asyncio
    async def test_get_pipeline_status_returns_execution_details(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that get_pipeline_status returns execution with all fields."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.RUNNING,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
            inputs_json='{"env": "prod"}',
        )
        mock_execution_manager.get_execution.return_value = execution
        mock_execution_manager.get_steps_for_execution.return_value = []

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "get_pipeline_status",
            {"execution_id": "pe-abc123"},
        )

        assert result["success"] is True
        assert result["execution"]["id"] == "pe-abc123"
        assert result["execution"]["pipeline_name"] == "deploy"
        assert result["execution"]["status"] == "running"
        assert result["execution"]["inputs"] == {"env": "prod"}

    @pytest.mark.asyncio
    async def test_get_pipeline_status_includes_step_executions(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that get_pipeline_status includes step_executions list."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry
        from gobby.workflows.pipeline_state import (
            ExecutionStatus,
            PipelineExecution,
            StepExecution,
            StepStatus,
        )

        execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.RUNNING,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
        )

        step1 = StepExecution(
            id=1,
            execution_id="pe-abc123",
            step_id="step1",
            status=StepStatus.COMPLETED,
            output_json='{"stdout": "done"}',
        )
        step2 = StepExecution(
            id=2,
            execution_id="pe-abc123",
            step_id="step2",
            status=StepStatus.RUNNING,
        )

        mock_execution_manager.get_execution.return_value = execution
        mock_execution_manager.get_steps_for_execution.return_value = [step1, step2]

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "get_pipeline_status",
            {"execution_id": "pe-abc123"},
        )

        assert result["success"] is True
        assert "steps" in result
        assert len(result["steps"]) == 2
        assert result["steps"][0]["step_id"] == "step1"
        assert result["steps"][0]["status"] == "completed"
        assert result["steps"][1]["step_id"] == "step2"
        assert result["steps"][1]["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_pipeline_status_not_found(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that get_pipeline_status returns error when not found."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        mock_execution_manager.get_execution.return_value = None

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "get_pipeline_status",
            {"execution_id": "pe-nonexistent"},
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_pipeline_status_no_execution_manager(
        self, mock_loader, mock_executor
    ) -> None:
        """Test that get_pipeline_status returns error when no manager configured."""
        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=None,
        )

        result = await registry.call(
            "get_pipeline_status",
            {"execution_id": "pe-abc123"},
        )

        assert result["success"] is False
        assert "manager" in result["error"].lower() or "configured" in result["error"].lower()


class TestDynamicPipelineTools:
    """Tests for dynamic tool generation from pipelines with expose_as_tool=True."""

    @pytest.mark.asyncio
    async def test_expose_as_tool_creates_dynamic_tool(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that pipelines with expose_as_tool=True are exposed as tools."""
        from pathlib import Path

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        # Create a pipeline with expose_as_tool=True
        pipeline = PipelineDefinition(
            name="run-tests",
            description="Run the test suite",
            steps=[PipelineStep(id="test", exec="pytest")],
            expose_as_tool=True,
        )

        mock_loader.discover_pipeline_workflows.return_value = [
            DiscoveredWorkflow(
                name="run-tests",
                definition=pipeline,
                priority=100,
                is_project=True,
                path=Path("/project/.gobby/workflows/run-tests.yaml"),
            ),
        ]

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "pipeline:run-tests" in tool_names

    @pytest.mark.asyncio
    async def test_expose_as_tool_false_not_exposed(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that pipelines with expose_as_tool=False are NOT exposed as tools."""
        from pathlib import Path

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        # Create a pipeline without expose_as_tool (defaults to False)
        pipeline = PipelineDefinition(
            name="internal-pipeline",
            description="Internal pipeline not exposed",
            steps=[PipelineStep(id="step1", exec="echo internal")],
        )

        mock_loader.discover_pipeline_workflows.return_value = [
            DiscoveredWorkflow(
                name="internal-pipeline",
                definition=pipeline,
                priority=100,
                is_project=True,
                path=Path("/project/.gobby/workflows/internal.yaml"),
            ),
        ]

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "pipeline:internal-pipeline" not in tool_names

    @pytest.mark.asyncio
    async def test_dynamic_tool_has_correct_description(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that dynamic pipeline tools have the pipeline's description."""
        from pathlib import Path

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        pipeline = PipelineDefinition(
            name="deploy",
            description="Deploy to production environment",
            steps=[PipelineStep(id="deploy", exec="deploy-app")],
            expose_as_tool=True,
        )

        mock_loader.discover_pipeline_workflows.return_value = [
            DiscoveredWorkflow(
                name="deploy",
                definition=pipeline,
                priority=100,
                is_project=True,
                path=Path("/project/.gobby/workflows/deploy.yaml"),
            ),
        ]

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        # Use get_schema to get the full schema with description
        schema = registry.get_schema("pipeline:deploy")
        assert schema is not None
        assert schema["description"] == "Deploy to production environment"

    @pytest.mark.asyncio
    async def test_dynamic_tool_includes_input_schema(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that dynamic pipeline tools include input schema from pipeline inputs."""
        from pathlib import Path

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        pipeline = PipelineDefinition(
            name="deploy",
            description="Deploy to environment",
            steps=[PipelineStep(id="deploy", exec="deploy-app")],
            expose_as_tool=True,
            inputs={
                "environment": {"type": "string", "default": "staging"},
                "version": {"type": "string", "description": "Version to deploy"},
            },
        )

        mock_loader.discover_pipeline_workflows.return_value = [
            DiscoveredWorkflow(
                name="deploy",
                definition=pipeline,
                priority=100,
                is_project=True,
                path=Path("/project/.gobby/workflows/deploy.yaml"),
            ),
        ]

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        # Use get_schema to get the full schema with inputSchema
        schema = registry.get_schema("pipeline:deploy")
        assert schema is not None
        assert "inputSchema" in schema
        input_schema = schema["inputSchema"]
        assert "properties" in input_schema
        assert "environment" in input_schema["properties"]
        assert "version" in input_schema["properties"]

    @pytest.mark.asyncio
    async def test_dynamic_tool_executes_pipeline(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that calling a dynamic pipeline tool executes the pipeline."""
        from pathlib import Path
        from unittest.mock import AsyncMock

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        pipeline = PipelineDefinition(
            name="run-tests",
            description="Run tests",
            steps=[PipelineStep(id="test", exec="pytest")],
            expose_as_tool=True,
            inputs={"filter": {"type": "string", "default": ""}},
        )

        mock_loader.discover_pipeline_workflows.return_value = [
            DiscoveredWorkflow(
                name="run-tests",
                definition=pipeline,
                priority=100,
                is_project=True,
                path=Path("/project/.gobby/workflows/run-tests.yaml"),
            ),
        ]
        mock_loader.load_pipeline.return_value = pipeline

        execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="run-tests",
            project_id="",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            outputs_json='{"tests_passed": 42}',
        )
        mock_executor.execute = AsyncMock(return_value=execution)

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        result = await registry.call(
            "pipeline:run-tests",
            {"filter": "test_api"},
        )

        assert result["success"] is True
        assert result["status"] == "completed"
        mock_executor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_exposed_pipelines(
        self, mock_loader, mock_executor, mock_execution_manager
    ) -> None:
        """Test that multiple pipelines with expose_as_tool=True all get tools."""
        from pathlib import Path

        from gobby.mcp_proxy.tools.pipelines import create_pipelines_registry

        pipeline1 = PipelineDefinition(
            name="build",
            description="Build project",
            steps=[PipelineStep(id="build", exec="npm run build")],
            expose_as_tool=True,
        )
        pipeline2 = PipelineDefinition(
            name="test",
            description="Run tests",
            steps=[PipelineStep(id="test", exec="npm test")],
            expose_as_tool=True,
        )
        pipeline3 = PipelineDefinition(
            name="internal",
            description="Internal only",
            steps=[PipelineStep(id="internal", exec="echo internal")],
            expose_as_tool=False,
        )

        mock_loader.discover_pipeline_workflows.return_value = [
            DiscoveredWorkflow(
                name="build",
                definition=pipeline1,
                priority=100,
                is_project=True,
                path=Path("/project/.gobby/workflows/build.yaml"),
            ),
            DiscoveredWorkflow(
                name="test",
                definition=pipeline2,
                priority=100,
                is_project=True,
                path=Path("/project/.gobby/workflows/test.yaml"),
            ),
            DiscoveredWorkflow(
                name="internal",
                definition=pipeline3,
                priority=100,
                is_project=True,
                path=Path("/project/.gobby/workflows/internal.yaml"),
            ),
        ]

        registry = create_pipelines_registry(
            loader=mock_loader,
            executor=mock_executor,
            execution_manager=mock_execution_manager,
        )

        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "pipeline:build" in tool_names
        assert "pipeline:test" in tool_names
        assert "pipeline:internal" not in tool_names
