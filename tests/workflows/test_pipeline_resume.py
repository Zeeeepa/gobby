"""Tests for pipeline resume functionality."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.workflows.definitions import PipelineApproval, PipelineDefinition, PipelineStep
from gobby.workflows.pipeline_executor import PipelineExecutor
from gobby.workflows.pipeline_state import ExecutionStatus, StepStatus

pytestmark = [pytest.mark.unit, pytest.mark.no_config_protection]


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_execution_manager():
    manager = MagicMock()
    # Default execution
    mock_execution = MagicMock()
    mock_execution.id = "pe-test-123"
    mock_execution.status = ExecutionStatus.PENDING
    mock_execution.inputs_json = "{}"
    manager.create_execution.return_value = mock_execution
    manager.get_execution.return_value = mock_execution
    manager.update_execution_status.return_value = mock_execution

    # Default step
    mock_step = MagicMock()
    mock_step.id = 1
    mock_step.status = StepStatus.PENDING
    manager.create_step_execution.return_value = mock_step
    manager.update_step_execution.return_value = mock_step

    # Mock get_steps_for_execution to return empty list by default
    manager.get_steps_for_execution.return_value = []

    return manager


@pytest.fixture
def mock_llm_service():
    return AsyncMock()


@pytest.fixture
def mock_loader():
    loader = MagicMock()
    loader.load_pipeline = AsyncMock()
    return loader


class TestPipelineResume:
    """Tests for resuming pipeline execution."""

    @pytest.mark.asyncio
    async def test_approve_resumes_execution_and_runs_next_step(
        self, mock_db, mock_execution_manager, mock_llm_service, mock_loader
    ) -> None:
        """Test that approve() resumes pipeline execution and runs subsequent steps."""

        # 1. Setup Pipeline with 2 steps: 1st needs approval, 2nd is simple exec
        pipeline = PipelineDefinition(
            name="resume-pipeline",
            steps=[
                PipelineStep(
                    id="step1", exec="echo step1", approval=PipelineApproval(required=True)
                ),
                PipelineStep(id="step2", exec="echo step2"),
            ],
        )
        mock_loader.load_pipeline.return_value = pipeline

        # 2. Setup state for approve() call
        # The step waiting for approval
        waiting_step = MagicMock()
        waiting_step.id = 101
        waiting_step.execution_id = "pe-resume-123"
        waiting_step.step_id = "step1"
        waiting_step.approval_token = "valid-token"
        waiting_step.status = StepStatus.WAITING_APPROVAL

        mock_execution_manager.get_step_by_approval_token.return_value = waiting_step

        # The execution record
        execution = MagicMock()
        execution.id = "pe-resume-123"
        execution.pipeline_name = "resume-pipeline"
        execution.status = ExecutionStatus.WAITING_APPROVAL
        execution.inputs_json = json.dumps({"env": "prod"})

        mock_execution_manager.get_execution.return_value = execution

        # Mock get_steps_for_execution to return the history so execute() can skip completed steps
        # When execute() runs, it should see step1 is COMPLETED (because approve() marks it so)

        # Create the completed step object that execute() will see
        completed_step1 = MagicMock()
        completed_step1.id = 101
        completed_step1.step_id = "step1"
        completed_step1.status = StepStatus.COMPLETED
        completed_step1.output_json = json.dumps({"status": "approved"})

        # Configure the mock to return this step when execute() checks for existing steps
        mock_execution_manager.get_steps_for_execution.return_value = [completed_step1]

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            loader=mock_loader,
        )

        # 3. Call approve()
        await executor.approve("valid-token")

        # 4. Assertions

        # Verify step1 was marked approved
        mock_execution_manager.update_step_execution.assert_any_call(
            step_execution_id=101, status=StepStatus.COMPLETED, approved_by=None
        )

        # Verify step2 was executed (create_step_execution called for step2)
        # currently this fails because approve() just returns
        calls = mock_execution_manager.create_step_execution.call_args_list
        step2_calls = [c for c in calls if c.kwargs.get("step_id") == "step2"]

        assert len(step2_calls) > 0, "Pipeline execution did not resume to step2 after approval"
