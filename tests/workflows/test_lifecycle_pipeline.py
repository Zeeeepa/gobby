"""Tests for pipeline integration with lifecycle workflows."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.templates import TemplateEngine

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_db():
    """Create a mock database."""
    return MagicMock()


@pytest.fixture
def mock_session_manager():
    """Create a mock session manager."""
    return MagicMock()


@pytest.fixture
def mock_pipeline_executor():
    """Create a mock pipeline executor."""
    return MagicMock()


@pytest.fixture
def mock_workflow_loader():
    """Create a mock workflow loader."""
    return MagicMock()


@pytest.fixture
def action_executor_with_pipeline(
    mock_db,
    mock_session_manager,
    mock_pipeline_executor,
    mock_workflow_loader,
):
    """Create an ActionExecutor with pipeline support."""
    return ActionExecutor(
        db=mock_db,
        session_manager=mock_session_manager,
        template_engine=TemplateEngine(),
        pipeline_executor=mock_pipeline_executor,
        workflow_loader=mock_workflow_loader,
    )


class TestLifecyclePipelineTriggers:
    """Tests for pipeline execution in lifecycle workflow triggers."""

    @pytest.mark.asyncio
    async def test_run_pipeline_in_on_after_tool_trigger(
        self, action_executor_with_pipeline, mock_pipeline_executor, mock_workflow_loader
    ) -> None:
        """Verify run_pipeline action works in on_after_tool trigger context."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        # Setup mock pipeline
        mock_pipeline = PipelineDefinition(
            name="post-tool-pipeline",
            description="Run after tool execution",
            steps=[PipelineStep(id="process", exec="process-result")],
        )
        mock_workflow_loader.load_pipeline.return_value = mock_pipeline

        # Setup mock execution
        mock_execution = PipelineExecution(
            id="pe-trigger-123",
            pipeline_name="post-tool-pipeline",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
        )
        mock_pipeline_executor.execute = AsyncMock(return_value=mock_execution)

        # Create context simulating a lifecycle trigger
        context = ActionContext(
            session_id="test-session",
            state=WorkflowState(
                session_id="test-session",
                workflow_name="lifecycle-workflow",
                step="on_after_tool",
                variables={"last_tool": "Bash"},
            ),
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=TemplateEngine(),
        )

        # Execute run_pipeline action
        result = await action_executor_with_pipeline.execute(
            "run_pipeline",
            context,
            name="post-tool-pipeline",
            inputs={"tool_name": "{{ last_tool }}"},
        )

        # Verify pipeline was executed
        assert result is not None
        assert result["status"] == "completed"
        assert result["execution_id"] == "pe-trigger-123"
        mock_workflow_loader.load_pipeline.assert_called_once_with("post-tool-pipeline")
        mock_pipeline_executor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_executes_when_tool_matches(
        self, action_executor_with_pipeline, mock_pipeline_executor, mock_workflow_loader
    ) -> None:
        """Verify pipeline only executes when trigger conditions match."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        # Setup mock pipeline
        mock_pipeline = PipelineDefinition(
            name="bash-only-pipeline",
            description="Run only for Bash tool",
            steps=[PipelineStep(id="bash-step", exec="echo done")],
        )
        mock_workflow_loader.load_pipeline.return_value = mock_pipeline

        mock_execution = PipelineExecution(
            id="pe-bash-123",
            pipeline_name="bash-only-pipeline",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
        )
        mock_pipeline_executor.execute = AsyncMock(return_value=mock_execution)

        # Context with matching tool
        context = ActionContext(
            session_id="test-session",
            state=WorkflowState(
                session_id="test-session",
                workflow_name="lifecycle-workflow",
                step="on_after_tool",
                variables={"tool_name": "Bash"},
            ),
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=TemplateEngine(),
        )

        result = await action_executor_with_pipeline.execute(
            "run_pipeline",
            context,
            name="bash-only-pipeline",
            inputs={},
        )

        assert result is not None
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_await_false_runs_async(
        self, action_executor_with_pipeline, mock_pipeline_executor, mock_workflow_loader
    ) -> None:
        """Verify await=false returns immediately without storing pending state."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.pipeline_state import ApprovalRequired

        # Setup mock pipeline
        mock_pipeline = PipelineDefinition(
            name="async-pipeline",
            description="Run asynchronously",
            steps=[PipelineStep(id="step1", exec="sleep 10")],
        )
        mock_workflow_loader.load_pipeline.return_value = mock_pipeline

        # Mock executor to raise ApprovalRequired
        mock_pipeline_executor.execute = AsyncMock(
            side_effect=ApprovalRequired(
                execution_id="pe-async-123",
                step_id="approval-step",
                token="async-token",
                message="Needs approval",
            )
        )

        context = ActionContext(
            session_id="test-session",
            state=WorkflowState(
                session_id="test-session",
                workflow_name="lifecycle-workflow",
                step="on_after_tool",
                variables={},
            ),
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=TemplateEngine(),
        )

        # Run with await_completion=False (default)
        result = await action_executor_with_pipeline.execute(
            "run_pipeline",
            context,
            name="async-pipeline",
            inputs={},
            await_completion=False,
        )

        assert result is not None
        assert result["status"] == "waiting_approval"
        # pending_pipeline should NOT be stored when await_completion=False
        assert "pending_pipeline" not in context.state.variables
