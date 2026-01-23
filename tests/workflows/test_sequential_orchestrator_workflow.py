"""Tests for sequential-orchestrator workflow.

Tests for the sequential-orchestrator workflow that:
- Manages sequential task execution in worktrees
- Has steps: select_task, spawn_agent, wait, review, decide, loop
- Transitions correctly between steps
"""

from pathlib import Path

import pytest

from gobby.workflows.loader import WorkflowLoader

pytestmark = pytest.mark.integration


@pytest.fixture
def workflow_loader_with_install_dir():
    """Create a WorkflowLoader that includes the install/shared/workflows directory."""
    install_dir = Path(__file__).parent.parent.parent / "src" / "gobby" / "install" / "shared" / "workflows"
    return WorkflowLoader(workflow_dirs=[install_dir])


class TestSequentialOrchestratorLoading:
    """Tests for loading the sequential-orchestrator workflow."""

    def test_workflow_loads(self, workflow_loader_with_install_dir):
        """Test that sequential-orchestrator workflow can be loaded."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("sequential-orchestrator")

        assert workflow is not None
        assert workflow.name == "sequential-orchestrator"
        assert workflow.type == "step"

    def test_workflow_has_description(self, workflow_loader_with_install_dir):
        """Test that workflow has a meaningful description."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("sequential-orchestrator")

        assert workflow is not None
        assert workflow.description is not None
        assert len(workflow.description) > 10


class TestSequentialOrchestratorSteps:
    """Tests for required workflow steps."""

    def test_has_select_task_step(self, workflow_loader_with_install_dir):
        """Test that workflow has select_task step."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("sequential-orchestrator")

        assert workflow is not None
        step = workflow.get_step("select_task")
        assert step is not None, "Missing 'select_task' step"

    def test_has_spawn_agent_step(self, workflow_loader_with_install_dir):
        """Test that workflow has spawn_agent step."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("sequential-orchestrator")

        assert workflow is not None
        step = workflow.get_step("spawn_agent")
        assert step is not None, "Missing 'spawn_agent' step"

    def test_has_wait_step(self, workflow_loader_with_install_dir):
        """Test that workflow has wait step."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("sequential-orchestrator")

        assert workflow is not None
        step = workflow.get_step("wait")
        assert step is not None, "Missing 'wait' step"

    def test_has_review_step(self, workflow_loader_with_install_dir):
        """Test that workflow has review step."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("sequential-orchestrator")

        assert workflow is not None
        step = workflow.get_step("review")
        assert step is not None, "Missing 'review' step"

    def test_has_decide_step(self, workflow_loader_with_install_dir):
        """Test that workflow has decide step."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("sequential-orchestrator")

        assert workflow is not None
        step = workflow.get_step("decide")
        assert step is not None, "Missing 'decide' step"

    def test_has_loop_step(self, workflow_loader_with_install_dir):
        """Test that workflow has loop step."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("sequential-orchestrator")

        assert workflow is not None
        step = workflow.get_step("loop")
        assert step is not None, "Missing 'loop' step"


class TestSequentialOrchestratorTransitions:
    """Tests for workflow transitions."""

    def test_loop_to_select_task_transition(self, workflow_loader_with_install_dir):
        """Test that loop step has transition to select_task when has_ready_tasks."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("sequential-orchestrator")

        assert workflow is not None
        loop_step = workflow.get_step("loop")
        assert loop_step is not None

        # Check that there's a transition to select_task
        transition_targets = [t.to for t in loop_step.transitions]
        assert "select_task" in transition_targets, "Missing loop→select_task transition"

    def test_loop_to_complete_transition(self, workflow_loader_with_install_dir):
        """Test that loop step has transition to complete when no_ready_tasks."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("sequential-orchestrator")

        assert workflow is not None
        loop_step = workflow.get_step("loop")
        assert loop_step is not None

        # Check that there's a transition to complete
        transition_targets = [t.to for t in loop_step.transitions]
        assert "complete" in transition_targets, "Missing loop→complete transition"


class TestSequentialOrchestratorSettings:
    """Tests for workflow settings."""

    def test_is_valid_for_agent_spawning(self, workflow_loader_with_install_dir):
        """Test that workflow is valid for agent spawning (not lifecycle type)."""
        loader = workflow_loader_with_install_dir
        is_valid, error = loader.validate_workflow_for_agent("sequential-orchestrator")

        assert is_valid is True
        assert error is None

    def test_has_exit_condition(self, workflow_loader_with_install_dir):
        """Test that workflow has an exit condition."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("sequential-orchestrator")

        assert workflow is not None
        assert workflow.exit_condition is not None
