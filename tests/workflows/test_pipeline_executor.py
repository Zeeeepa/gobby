"""Tests for PipelineExecutor class.

TDD tests for executing pipeline workflows.
"""

import json
from unittest.mock import MagicMock, AsyncMock

import pytest

from gobby.workflows.definitions import PipelineDefinition, PipelineStep
from gobby.workflows.pipeline_state import ExecutionStatus, StepStatus

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_db():
    """Create a mock database."""
    return MagicMock()


@pytest.fixture
def mock_execution_manager():
    """Create a mock LocalPipelineExecutionManager."""
    manager = MagicMock()
    # Default: create_execution returns a mock execution
    mock_execution = MagicMock()
    mock_execution.id = "pe-test-123"
    mock_execution.status = ExecutionStatus.PENDING
    manager.create_execution.return_value = mock_execution
    manager.get_execution.return_value = mock_execution
    manager.update_execution_status.return_value = mock_execution
    # Default: create_step_execution returns a mock step
    mock_step = MagicMock()
    mock_step.id = 1
    mock_step.status = StepStatus.PENDING
    manager.create_step_execution.return_value = mock_step
    manager.update_step_execution.return_value = mock_step
    return manager


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service."""
    service = AsyncMock()
    service.generate.return_value = "LLM response"
    return service


@pytest.fixture
def mock_template_engine():
    """Create a mock template engine."""
    engine = MagicMock()
    # Default: render returns the template unchanged
    engine.render.side_effect = lambda template, context: template
    return engine


@pytest.fixture
def mock_webhook_notifier():
    """Create a mock webhook notifier."""
    notifier = AsyncMock()
    return notifier


@pytest.fixture
def simple_pipeline():
    """Create a simple pipeline definition."""
    return PipelineDefinition(
        name="test-pipeline",
        description="A test pipeline",
        steps=[
            PipelineStep(id="step1", exec="echo hello"),
            PipelineStep(id="step2", exec="echo world"),
        ],
    )


@pytest.fixture
def pipeline_with_prompt():
    """Create a pipeline with a prompt step."""
    return PipelineDefinition(
        name="prompt-pipeline",
        steps=[
            PipelineStep(id="analyze", exec="./analyze.sh"),
            PipelineStep(id="report", prompt="Generate report from $analyze.output"),
        ],
    )


@pytest.fixture
def pipeline_with_inputs():
    """Create a pipeline with inputs."""
    return PipelineDefinition(
        name="input-pipeline",
        inputs={
            "target": {"type": "string", "description": "Target to process"},
            "mode": {"type": "string", "default": "fast"},
        },
        steps=[
            PipelineStep(id="process", exec="./process.sh $inputs.target"),
        ],
    )


class TestPipelineExecutorInit:
    """Tests for PipelineExecutor initialization."""

    def test_init_with_required_dependencies(
        self, mock_db, mock_execution_manager, mock_llm_service
    ) -> None:
        """Test that executor initializes with required dependencies."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
        )

        assert executor.db is mock_db
        assert executor.execution_manager is mock_execution_manager
        assert executor.llm_service is mock_llm_service

    def test_init_with_optional_dependencies(
        self,
        mock_db,
        mock_execution_manager,
        mock_llm_service,
        mock_template_engine,
        mock_webhook_notifier,
    ) -> None:
        """Test that executor initializes with optional dependencies."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            webhook_notifier=mock_webhook_notifier,
        )

        assert executor.template_engine is mock_template_engine
        assert executor.webhook_notifier is mock_webhook_notifier


class TestPipelineExecutorExecute:
    """Tests for PipelineExecutor.execute() method."""

    @pytest.mark.asyncio
    async def test_execute_creates_execution_record(
        self, mock_db, mock_execution_manager, mock_llm_service, simple_pipeline
    ) -> None:
        """Test that execute() creates a PipelineExecution record."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
        )

        await executor.execute(
            pipeline=simple_pipeline,
            inputs={},
            project_id="proj-123",
        )

        mock_execution_manager.create_execution.assert_called_once()
        call_kwargs = mock_execution_manager.create_execution.call_args
        assert call_kwargs.kwargs["pipeline_name"] == "test-pipeline"
        assert call_kwargs.kwargs["inputs_json"] is not None

    @pytest.mark.asyncio
    async def test_execute_with_existing_execution_id(
        self, mock_db, mock_execution_manager, mock_llm_service, simple_pipeline
    ) -> None:
        """Test that execute() uses existing execution ID if provided."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
        )

        await executor.execute(
            pipeline=simple_pipeline,
            inputs={},
            project_id="proj-123",
            execution_id="pe-existing-456",
        )

        # Should get existing execution, not create new one
        mock_execution_manager.get_execution.assert_called_with("pe-existing-456")

    @pytest.mark.asyncio
    async def test_execute_builds_context_with_inputs(
        self, mock_db, mock_execution_manager, mock_llm_service, pipeline_with_inputs
    ) -> None:
        """Test that execute() builds context with input values."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
        )

        inputs = {"target": "/path/to/file", "mode": "thorough"}

        await executor.execute(
            pipeline=pipeline_with_inputs,
            inputs=inputs,
            project_id="proj-123",
        )

        # Verify inputs were serialized in execution record
        call_kwargs = mock_execution_manager.create_execution.call_args.kwargs
        inputs_json = call_kwargs["inputs_json"]
        assert json.loads(inputs_json) == inputs

    @pytest.mark.asyncio
    async def test_execute_iterates_steps_in_order(
        self, mock_db, mock_execution_manager, mock_llm_service, simple_pipeline
    ) -> None:
        """Test that execute() iterates through steps in order."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
        )

        await executor.execute(
            pipeline=simple_pipeline,
            inputs={},
            project_id="proj-123",
        )

        # Should create step executions for each step
        assert mock_execution_manager.create_step_execution.call_count == 2
        calls = mock_execution_manager.create_step_execution.call_args_list
        assert calls[0].kwargs["step_id"] == "step1"
        assert calls[1].kwargs["step_id"] == "step2"

    @pytest.mark.asyncio
    async def test_execute_returns_execution_with_status(
        self, mock_db, mock_execution_manager, mock_llm_service, simple_pipeline
    ) -> None:
        """Test that execute() returns execution with final status."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        # Configure mock to return completed status
        completed_execution = MagicMock()
        completed_execution.id = "pe-test-123"
        completed_execution.status = ExecutionStatus.COMPLETED
        mock_execution_manager.update_execution_status.return_value = completed_execution

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
        )

        result = await executor.execute(
            pipeline=simple_pipeline,
            inputs={},
            project_id="proj-123",
        )

        assert result is not None
        assert result.status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_updates_status_to_running(
        self, mock_db, mock_execution_manager, mock_llm_service, simple_pipeline
    ) -> None:
        """Test that execute() updates status to RUNNING when starting."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
        )

        await executor.execute(
            pipeline=simple_pipeline,
            inputs={},
            project_id="proj-123",
        )

        # First status update should be to RUNNING
        calls = mock_execution_manager.update_execution_status.call_args_list
        first_call = calls[0]
        assert first_call.kwargs["status"] == ExecutionStatus.RUNNING


class TestPipelineExecutorStepExecution:
    """Tests for step execution within PipelineExecutor."""

    @pytest.mark.asyncio
    async def test_execute_step_updates_step_status(
        self, mock_db, mock_execution_manager, mock_llm_service, simple_pipeline
    ) -> None:
        """Test that step execution updates step status."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
        )

        await executor.execute(
            pipeline=simple_pipeline,
            inputs={},
            project_id="proj-123",
        )

        # Step status should be updated to RUNNING then COMPLETED
        update_calls = mock_execution_manager.update_step_execution.call_args_list
        # At least some calls should set status to RUNNING or COMPLETED
        statuses = [call.kwargs.get("status") for call in update_calls if call.kwargs.get("status")]
        assert StepStatus.RUNNING in statuses or StepStatus.COMPLETED in statuses

    @pytest.mark.asyncio
    async def test_execute_stores_step_output(
        self, mock_db, mock_execution_manager, mock_llm_service, simple_pipeline
    ) -> None:
        """Test that step execution stores output in step record."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
        )

        await executor.execute(
            pipeline=simple_pipeline,
            inputs={},
            project_id="proj-123",
        )

        # At least one call should include output_json
        update_calls = mock_execution_manager.update_step_execution.call_args_list
        has_output = any(call.kwargs.get("output_json") is not None for call in update_calls)
        assert has_output
