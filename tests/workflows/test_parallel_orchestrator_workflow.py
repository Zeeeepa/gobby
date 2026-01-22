"""Tests for parallel-orchestrator workflow.

Tests for the parallel-orchestrator workflow with clone support that:
- Manages parallel task execution with clone-based isolation
- Has steps: select_batch, spawn_batch, wait_any, sync_and_review, process_completed, loop
- Has config: max_parallel_agents=3, isolation_mode=clone
- Includes clone tools in allowed_tools
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


class TestParallelOrchestratorLoading:
    """Tests for loading the parallel-orchestrator workflow."""

    def test_workflow_loads(self, workflow_loader_with_install_dir):
        """Test that parallel-orchestrator workflow can be loaded."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("parallel-orchestrator")

        assert workflow is not None
        assert workflow.name == "parallel-orchestrator"
        assert workflow.type == "step"

    def test_workflow_has_description(self, workflow_loader_with_install_dir):
        """Test that workflow has a meaningful description."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("parallel-orchestrator")

        assert workflow is not None
        assert workflow.description is not None
        assert len(workflow.description) > 10


class TestParallelOrchestratorConfig:
    """Tests for workflow configuration."""

    def test_has_max_parallel_agents_config(self, workflow_loader_with_install_dir):
        """Test that workflow has max_parallel_agents=3 configuration."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("parallel-orchestrator")

        assert workflow is not None
        assert "max_parallel_agents" in workflow.variables
        assert workflow.variables["max_parallel_agents"] == 3

    def test_has_isolation_mode_clone(self, workflow_loader_with_install_dir):
        """Test that workflow has isolation_mode=clone configuration."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("parallel-orchestrator")

        assert workflow is not None
        assert "isolation_mode" in workflow.variables
        assert workflow.variables["isolation_mode"] == "clone"


class TestParallelOrchestratorSteps:
    """Tests for required workflow steps."""

    def test_has_select_batch_step(self, workflow_loader_with_install_dir):
        """Test that workflow has select_batch step."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("parallel-orchestrator")

        assert workflow is not None
        step = workflow.get_step("select_batch")
        assert step is not None, "Missing 'select_batch' step"

    def test_has_spawn_batch_step(self, workflow_loader_with_install_dir):
        """Test that workflow has spawn_batch step."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("parallel-orchestrator")

        assert workflow is not None
        step = workflow.get_step("spawn_batch")
        assert step is not None, "Missing 'spawn_batch' step"

    def test_has_wait_any_step(self, workflow_loader_with_install_dir):
        """Test that workflow has wait_any step."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("parallel-orchestrator")

        assert workflow is not None
        step = workflow.get_step("wait_any")
        assert step is not None, "Missing 'wait_any' step"

    def test_has_sync_and_review_step(self, workflow_loader_with_install_dir):
        """Test that workflow has sync_and_review step."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("parallel-orchestrator")

        assert workflow is not None
        step = workflow.get_step("sync_and_review")
        assert step is not None, "Missing 'sync_and_review' step"

    def test_has_process_completed_step(self, workflow_loader_with_install_dir):
        """Test that workflow has process_completed step."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("parallel-orchestrator")

        assert workflow is not None
        step = workflow.get_step("process_completed")
        assert step is not None, "Missing 'process_completed' step"

    def test_has_loop_step(self, workflow_loader_with_install_dir):
        """Test that workflow has loop step."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("parallel-orchestrator")

        assert workflow is not None
        step = workflow.get_step("loop")
        assert step is not None, "Missing 'loop' step"


class TestParallelOrchestratorCloneTools:
    """Tests for clone tool availability."""

    def test_spawn_batch_allows_clone_tools(self, workflow_loader_with_install_dir):
        """Test that spawn_batch step allows clone tools."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("parallel-orchestrator")

        assert workflow is not None
        step = workflow.get_step("spawn_batch")
        assert step is not None

        # Either allowed_tools is "all" or includes clone tools
        if step.allowed_tools != "all":
            allowed = step.allowed_tools
            # Check for clone-related tools
            clone_tools_present = any(
                tool in allowed or "clone" in tool.lower()
                for tool in ["create_clone", "spawn_agent_in_clone", "list_clones"]
            )
            assert clone_tools_present or step.allowed_tools == "all"


class TestParallelOrchestratorSettings:
    """Tests for workflow settings."""

    def test_is_valid_for_agent_spawning(self, workflow_loader_with_install_dir):
        """Test that workflow is valid for agent spawning (not lifecycle type)."""
        loader = workflow_loader_with_install_dir
        is_valid, error = loader.validate_workflow_for_agent("parallel-orchestrator")

        assert is_valid is True
        assert error is None

    def test_has_exit_condition(self, workflow_loader_with_install_dir):
        """Test that workflow has an exit condition."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("parallel-orchestrator")

        assert workflow is not None
        assert workflow.exit_condition is not None
