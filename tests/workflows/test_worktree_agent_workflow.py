"""Tests for worktree-agent workflow.

Tests for the worktree-agent workflow that restricts tools for spawned agents:
- Allowed tools: get_task, update_task, close_task (gobby-tasks), remember, recall, forget (gobby-memory)
- Blocked tools: list_tasks, create_task, expand_task (gobby-tasks), all gobby-agents/gobby-worktrees tools
"""

from pathlib import Path

import pytest

from gobby.workflows.loader import WorkflowLoader

pytestmark = pytest.mark.integration


@pytest.fixture
def workflow_loader_with_install_dir():
    """Create a WorkflowLoader that includes the install/shared/workflows directory."""
    install_dir = (
        Path(__file__).parent.parent.parent / "src" / "gobby" / "install" / "shared" / "workflows"
    )
    return WorkflowLoader(workflow_dirs=[install_dir])


class TestWorktreeAgentWorkflowLoading:
    """Tests for loading the worktree-agent workflow."""

    def test_worktree_agent_workflow_loads(self, workflow_loader_with_install_dir):
        """Test that worktree-agent workflow can be loaded via WorkflowLoader."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("worktree-agent")

        assert workflow is not None
        assert workflow.name == "worktree-agent"
        assert workflow.type == "step"

    def test_worktree_agent_has_work_step(self, workflow_loader_with_install_dir):
        """Test that worktree-agent workflow has a 'work' step."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("worktree-agent")

        assert workflow is not None
        step_names = [s.name for s in workflow.steps]
        assert "work" in step_names


class TestWorktreeAgentAllowedTools:
    """Tests for tool allowlist filtering."""

    def test_allows_get_task(self, workflow_loader_with_install_dir):
        """Test that get_task tool is in allowed list."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("worktree-agent")
        work_step = workflow.get_step("work")

        assert work_step is not None
        # Tool allowlist should include gobby-tasks tools
        if work_step.allowed_tools != "all":
            # Check for either full MCP path or short name
            allowed = work_step.allowed_tools
            assert "get_task" in allowed or any("get_task" in t for t in allowed)

    def test_allows_update_task(self, workflow_loader_with_install_dir):
        """Test that update_task tool is in allowed list."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("worktree-agent")
        work_step = workflow.get_step("work")

        assert work_step is not None
        if work_step.allowed_tools != "all":
            allowed = work_step.allowed_tools
            assert "update_task" in allowed or any("update_task" in t for t in allowed)

    def test_allows_close_task(self, workflow_loader_with_install_dir):
        """Test that close_task tool is in allowed list."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("worktree-agent")
        work_step = workflow.get_step("work")

        assert work_step is not None
        if work_step.allowed_tools != "all":
            allowed = work_step.allowed_tools
            assert "close_task" in allowed or any("close_task" in t for t in allowed)

    def test_allows_memory_tools(self, workflow_loader_with_install_dir):
        """Test that memory tools (remember, recall, forget) are in allowed list."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("worktree-agent")
        work_step = workflow.get_step("work")

        assert work_step is not None
        if work_step.allowed_tools != "all":
            allowed = work_step.allowed_tools
            assert "remember" in allowed or any("remember" in t for t in allowed)
            assert "recall" in allowed or any("recall" in t for t in allowed)
            assert "forget" in allowed or any("forget" in t for t in allowed)


class TestWorktreeAgentBlockedTools:
    """Tests for tool blocklist."""

    def test_blocks_list_tasks(self, workflow_loader_with_install_dir):
        """Test that list_tasks is blocked."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("worktree-agent")
        work_step = workflow.get_step("work")

        assert work_step is not None
        blocked = work_step.blocked_tools
        assert "list_tasks" in blocked or any("list_tasks" in t for t in blocked)

    def test_blocks_create_task(self, workflow_loader_with_install_dir):
        """Test that create_task is blocked."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("worktree-agent")
        work_step = workflow.get_step("work")

        assert work_step is not None
        blocked = work_step.blocked_tools
        assert "create_task" in blocked or any("create_task" in t for t in blocked)

    def test_blocks_expand_task(self, workflow_loader_with_install_dir):
        """Test that expand_task is blocked."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("worktree-agent")
        work_step = workflow.get_step("work")

        assert work_step is not None
        blocked = work_step.blocked_tools
        assert "expand_task" in blocked or any("expand_task" in t for t in blocked)

    def test_blocks_gobby_agents_tools(self, workflow_loader_with_install_dir):
        """Test that gobby-agents tools are blocked."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("worktree-agent")
        work_step = workflow.get_step("work")

        assert work_step is not None
        blocked = work_step.blocked_tools

        # Should block agent spawning tools
        agent_tools = ["start_agent", "cancel_agent", "list_agents"]
        for tool in agent_tools:
            assert tool in blocked or any(tool in t for t in blocked), (
                f"Expected {tool} to be blocked"
            )

    def test_blocks_gobby_worktrees_tools(self, workflow_loader_with_install_dir):
        """Test that gobby-worktrees tools are blocked."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("worktree-agent")
        work_step = workflow.get_step("work")

        assert work_step is not None
        blocked = work_step.blocked_tools

        # Should block worktree tools
        worktree_tools = ["create_worktree", "spawn_agent_in_worktree", "list_worktrees"]
        for tool in worktree_tools:
            assert tool in blocked or any(tool in t for t in blocked), (
                f"Expected {tool} to be blocked"
            )


class TestWorktreeAgentWorkflowSettings:
    """Tests for workflow settings and auto-activation."""

    def test_has_description(self, workflow_loader_with_install_dir):
        """Test that workflow has a meaningful description."""
        loader = workflow_loader_with_install_dir
        workflow = loader.load_workflow("worktree-agent")

        assert workflow is not None
        assert workflow.description is not None
        assert len(workflow.description) > 10

    def test_is_valid_for_agent_spawning(self, workflow_loader_with_install_dir):
        """Test that workflow is valid for agent spawning (not lifecycle type)."""
        loader = workflow_loader_with_install_dir
        is_valid, error = loader.validate_workflow_for_agent("worktree-agent")

        assert is_valid is True
        assert error is None
