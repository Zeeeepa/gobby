"""Tests for pipeline integration with step workflows."""

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


class TestStepWorkflowPipelineTriggers:
    """Tests for pipeline execution in step workflow on_enter/on_exit."""

    @pytest.mark.asyncio
    async def test_run_pipeline_in_on_enter_trigger(
        self, action_executor_with_pipeline, mock_pipeline_executor, mock_workflow_loader
    ) -> None:
        """Verify run_pipeline action works in step on_enter context."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        # Setup mock pipeline
        mock_pipeline = PipelineDefinition(
            name="on-enter-pipeline",
            description="Run when entering step",
            steps=[PipelineStep(id="setup", exec="setup-environment")],
        )
        mock_workflow_loader.load_pipeline.return_value = mock_pipeline

        # Setup mock execution
        mock_execution = PipelineExecution(
            id="pe-enter-123",
            pipeline_name="on-enter-pipeline",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
        )
        mock_pipeline_executor.execute = AsyncMock(return_value=mock_execution)

        # Create context simulating a step on_enter trigger
        context = ActionContext(
            session_id="test-session",
            state=WorkflowState(
                session_id="test-session",
                workflow_name="step-workflow",
                step="build",
                variables={"step_name": "build"},
            ),
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=TemplateEngine(),
        )

        # Execute run_pipeline action
        result = await action_executor_with_pipeline.execute(
            "run_pipeline",
            context,
            name="on-enter-pipeline",
            inputs={"current_step": "{{ step_name }}"},
        )

        # Verify pipeline was executed
        assert result is not None
        assert result["status"] == "completed"
        assert result["execution_id"] == "pe-enter-123"
        mock_workflow_loader.load_pipeline.assert_called_once_with("on-enter-pipeline")
        mock_pipeline_executor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_pipeline_in_on_exit_trigger(
        self, action_executor_with_pipeline, mock_pipeline_executor, mock_workflow_loader
    ) -> None:
        """Verify run_pipeline action works in step on_exit context."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        # Setup mock pipeline
        mock_pipeline = PipelineDefinition(
            name="cleanup-pipeline",
            description="Run when exiting step",
            steps=[PipelineStep(id="cleanup", exec="cleanup-resources")],
        )
        mock_workflow_loader.load_pipeline.return_value = mock_pipeline

        # Setup mock execution
        mock_execution = PipelineExecution(
            id="pe-exit-456",
            pipeline_name="cleanup-pipeline",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:02:00Z",
        )
        mock_pipeline_executor.execute = AsyncMock(return_value=mock_execution)

        # Create context simulating a step on_exit trigger
        context = ActionContext(
            session_id="test-session",
            state=WorkflowState(
                session_id="test-session",
                workflow_name="step-workflow",
                step="build",
                variables={"previous_step": "setup"},
            ),
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=TemplateEngine(),
        )

        # Execute run_pipeline action
        result = await action_executor_with_pipeline.execute(
            "run_pipeline",
            context,
            name="cleanup-pipeline",
            inputs={},
        )

        # Verify pipeline was executed
        assert result is not None
        assert result["status"] == "completed"
        assert result["execution_id"] == "pe-exit-456"

    @pytest.mark.asyncio
    async def test_await_true_blocks_until_completion(
        self, action_executor_with_pipeline, mock_pipeline_executor, mock_workflow_loader
    ) -> None:
        """Verify await=true stores pending_pipeline when approval needed."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.pipeline_state import ApprovalRequired

        # Setup mock pipeline
        mock_pipeline = PipelineDefinition(
            name="deploy-pipeline",
            description="Deploy with approval gate",
            steps=[PipelineStep(id="deploy", exec="deploy-app")],
        )
        mock_workflow_loader.load_pipeline.return_value = mock_pipeline

        # Setup mock executor to raise ApprovalRequired
        mock_pipeline_executor.execute = AsyncMock(
            side_effect=ApprovalRequired(
                execution_id="pe-deploy-789",
                step_id="approval-gate",
                token="approval-token-abc",
                message="Approval required for production deploy",
            )
        )

        # Create context
        context = ActionContext(
            session_id="test-session",
            state=WorkflowState(
                session_id="test-session",
                workflow_name="step-workflow",
                step="deploy",
                variables={},
            ),
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=TemplateEngine(),
        )

        # Execute with await_completion=True
        result = await action_executor_with_pipeline.execute(
            "run_pipeline",
            context,
            name="deploy-pipeline",
            inputs={},
            await_completion=True,
        )

        # Verify waiting state and pending_pipeline stored
        assert result is not None
        assert result["status"] == "waiting_approval"
        assert result["execution_id"] == "pe-deploy-789"
        assert result["token"] == "approval-token-abc"
        # pending_pipeline should be stored when await_completion=True
        assert context.state.variables.get("pending_pipeline") == "pe-deploy-789"


class TestWorkflowEngineStepPipelineContext:
    """Tests for WorkflowEngine passing pipeline context to ActionContext."""

    @pytest.mark.asyncio
    async def test_execute_actions_includes_pipeline_executor(
        self, mock_db, mock_session_manager, mock_pipeline_executor, mock_workflow_loader
    ) -> None:
        """Verify WorkflowEngine._execute_actions passes pipeline_executor to ActionContext."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.engine import WorkflowEngine
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution
        from gobby.workflows.state_manager import WorkflowStateManager

        # Setup action executor with pipeline support
        action_executor = ActionExecutor(
            db=mock_db,
            session_manager=mock_session_manager,
            template_engine=TemplateEngine(),
            pipeline_executor=mock_pipeline_executor,
            workflow_loader=mock_workflow_loader,
        )

        # Create workflow engine
        mock_loader = MagicMock()
        mock_state_manager = MagicMock(spec=WorkflowStateManager)
        engine = WorkflowEngine(
            loader=mock_loader,
            state_manager=mock_state_manager,
            action_executor=action_executor,
        )

        # Setup mock pipeline
        mock_pipeline = PipelineDefinition(
            name="test-pipeline",
            description="Test",
            steps=[PipelineStep(id="step1", exec="echo test")],
        )
        mock_workflow_loader.load_pipeline.return_value = mock_pipeline

        # Setup mock execution
        mock_execution = PipelineExecution(
            id="pe-engine-test",
            pipeline_name="test-pipeline",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
        )
        mock_pipeline_executor.execute = AsyncMock(return_value=mock_execution)

        # Create workflow state
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            variables={},
        )

        # Define actions with run_pipeline
        actions = [{"action": "run_pipeline", "name": "test-pipeline", "inputs": {}}]

        # Execute actions through engine
        await engine._execute_actions(actions, state)

        # Verify pipeline was executed (this will fail if pipeline_executor not passed)
        mock_pipeline_executor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_actions_includes_workflow_loader(
        self, mock_db, mock_session_manager, mock_pipeline_executor, mock_workflow_loader
    ) -> None:
        """Verify WorkflowEngine._execute_actions passes workflow_loader to ActionContext."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.engine import WorkflowEngine
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution
        from gobby.workflows.state_manager import WorkflowStateManager

        # Setup action executor with pipeline support
        action_executor = ActionExecutor(
            db=mock_db,
            session_manager=mock_session_manager,
            template_engine=TemplateEngine(),
            pipeline_executor=mock_pipeline_executor,
            workflow_loader=mock_workflow_loader,
        )

        # Create workflow engine
        mock_loader = MagicMock()
        mock_state_manager = MagicMock(spec=WorkflowStateManager)
        engine = WorkflowEngine(
            loader=mock_loader,
            state_manager=mock_state_manager,
            action_executor=action_executor,
        )

        # Setup mock pipeline
        mock_pipeline = PipelineDefinition(
            name="loader-test-pipeline",
            description="Test loader",
            steps=[PipelineStep(id="step1", exec="echo test")],
        )
        mock_workflow_loader.load_pipeline.return_value = mock_pipeline

        # Setup mock execution
        mock_execution = PipelineExecution(
            id="pe-loader-test",
            pipeline_name="loader-test-pipeline",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
        )
        mock_pipeline_executor.execute = AsyncMock(return_value=mock_execution)

        # Create workflow state
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            variables={},
        )

        # Define actions with run_pipeline
        actions = [{"action": "run_pipeline", "name": "loader-test-pipeline", "inputs": {}}]

        # Execute actions through engine
        await engine._execute_actions(actions, state)

        # Verify loader was called (this will fail if workflow_loader not passed)
        mock_workflow_loader.load_pipeline.assert_called_once_with("loader-test-pipeline")
