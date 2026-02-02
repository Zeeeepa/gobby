"""Tests for pipeline action in ActionExecutor."""

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
def action_executor(
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


@pytest.fixture
def action_context(mock_db, mock_session_manager):
    """Create an action context for testing."""
    return ActionContext(
        session_id="test-session",
        state=WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="step1",
            variables={},
        ),
        db=mock_db,
        session_manager=mock_session_manager,
        template_engine=TemplateEngine(),
    )


class TestRunPipelineActionRegistration:
    """Tests for run_pipeline action registration."""

    def test_run_pipeline_action_is_registered(self, action_executor) -> None:
        """Verify run_pipeline action is registered."""
        assert "run_pipeline" in action_executor._handlers


class TestRunPipelineActionExecution:
    """Tests for run_pipeline action execution."""

    @pytest.mark.asyncio
    async def test_run_pipeline_executes_pipeline(
        self, action_executor, action_context, mock_pipeline_executor, mock_workflow_loader
    ) -> None:
        """Verify run_pipeline action executes pipeline with rendered inputs."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        # Setup mock pipeline
        mock_pipeline = PipelineDefinition(
            name="deploy",
            description="Deploy to production",
            steps=[PipelineStep(id="build", exec="npm run build")],
        )
        mock_workflow_loader.load_pipeline.return_value = mock_pipeline

        # Setup mock execution
        mock_execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
        )
        mock_pipeline_executor.execute = AsyncMock(return_value=mock_execution)

        result = await action_executor.execute(
            "run_pipeline",
            action_context,
            name="deploy",
            inputs={"env": "prod"},
        )

        assert result is not None
        assert result["execution_id"] == "pe-abc123"
        assert result["status"] == "completed"
        mock_workflow_loader.load_pipeline.assert_called_once_with("deploy")
        mock_pipeline_executor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_pipeline_stores_pending_on_approval_required(
        self, action_executor, action_context, mock_pipeline_executor, mock_workflow_loader
    ) -> None:
        """Verify run_pipeline stores pending_pipeline when approval needed."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.pipeline_state import ApprovalRequired

        # Setup mock pipeline
        mock_pipeline = PipelineDefinition(
            name="deploy",
            description="Deploy to production",
            steps=[PipelineStep(id="build", exec="npm run build")],
        )
        mock_workflow_loader.load_pipeline.return_value = mock_pipeline

        # Setup mock executor to raise ApprovalRequired
        mock_pipeline_executor.execute = AsyncMock(
            side_effect=ApprovalRequired(
                execution_id="pe-abc123",
                step_id="deploy-step",
                token="approval-token-xyz",
                message="Manual approval required",
            )
        )

        result = await action_executor.execute(
            "run_pipeline",
            action_context,
            name="deploy",
            inputs={},
            await_completion=True,
        )

        assert result is not None
        assert result["status"] == "waiting_approval"
        assert result["execution_id"] == "pe-abc123"
        assert result["token"] == "approval-token-xyz"
        # Verify pending_pipeline stored in state
        assert action_context.state.variables.get("pending_pipeline") == "pe-abc123"

    @pytest.mark.asyncio
    async def test_run_pipeline_not_found(
        self, action_executor, action_context, mock_workflow_loader
    ) -> None:
        """Verify run_pipeline returns error for unknown pipeline."""
        mock_workflow_loader.load_pipeline.return_value = None

        result = await action_executor.execute(
            "run_pipeline",
            action_context,
            name="nonexistent",
            inputs={},
        )

        assert result is not None
        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_run_pipeline_renders_inputs(
        self, action_executor, action_context, mock_pipeline_executor, mock_workflow_loader
    ) -> None:
        """Verify run_pipeline renders template variables in inputs."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        # Set a variable in the workflow state
        action_context.state.variables["environment"] = "staging"

        # Setup mock pipeline
        mock_pipeline = PipelineDefinition(
            name="deploy",
            description="Deploy to production",
            steps=[PipelineStep(id="build", exec="npm run build")],
        )
        mock_workflow_loader.load_pipeline.return_value = mock_pipeline

        # Setup mock execution
        mock_execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
        )
        mock_pipeline_executor.execute = AsyncMock(return_value=mock_execution)

        result = await action_executor.execute(
            "run_pipeline",
            action_context,
            name="deploy",
            inputs={"env": "{{ environment }}"},
        )

        assert result is not None
        # Verify inputs were rendered
        call_kwargs = mock_pipeline_executor.execute.call_args
        passed_inputs = call_kwargs.kwargs.get("inputs", {})
        assert passed_inputs.get("env") == "staging"
