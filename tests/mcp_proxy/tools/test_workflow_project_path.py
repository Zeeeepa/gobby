"""Tests for workflow tools with optional project_path and auto-discovery.

These tests verify that workflow tools work with:
1. Explicit project_path parameter provided
2. No project_path provided - auto-discovery kicks in
3. Auto-discovery in worktree context finds parent project
4. Clear error when auto-discovery fails and no project_path given
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from gobby.mcp_proxy.tools.workflows import create_workflows_registry


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = MagicMock()
    return db


@pytest.fixture
def mock_state_manager():
    """Create a mock workflow state manager."""
    return MagicMock()


@pytest.fixture
def mock_session_manager():
    """Create a mock session manager."""
    return MagicMock()


@pytest.fixture
def mock_loader():
    """Create a mock workflow loader."""
    loader = MagicMock()
    loader.global_dirs = []
    return loader


@pytest.fixture
def registry(mock_loader, mock_state_manager, mock_session_manager, mock_db):
    """Create workflow registry for testing."""
    return create_workflows_registry(
        loader=mock_loader,
        state_manager=mock_state_manager,
        session_manager=mock_session_manager,
        db=mock_db,
    )


def call_tool(registry, tool_name: str, **kwargs):
    """Helper to call a tool from the registry synchronously."""
    tool = registry._tools.get(tool_name)
    if not tool:
        raise ValueError(f"Tool '{tool_name}' not found")
    return tool.func(**kwargs)


class TestGetWorkflowWithProjectPath:
    """Tests for get_workflow with project_path parameter."""

    def test_with_explicit_project_path(self, registry, mock_loader, tmp_path):
        """Verify get_workflow works with explicit project_path."""
        # Setup mock workflow
        mock_workflow = MagicMock()
        mock_workflow.name = "test-workflow"
        mock_workflow.type = "step"
        mock_workflow.description = "Test workflow"
        mock_workflow.version = "1.0"
        mock_workflow.steps = []
        mock_workflow.triggers = {}
        mock_workflow.settings = {}
        mock_loader.load_workflow.return_value = mock_workflow

        # Call with explicit project_path
        result = call_tool(
            registry, "get_workflow", name="test-workflow", project_path=str(tmp_path)
        )

        assert result["success"] is True
        assert result["name"] == "test-workflow"
        mock_loader.load_workflow.assert_called_once_with("test-workflow", tmp_path)

    def test_with_auto_discovery(self, registry, mock_loader, tmp_path):
        """Verify get_workflow uses auto-discovery when project_path not provided."""
        # Setup project structure
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        (gobby_dir / "project.json").write_text(json.dumps({"id": "test-id"}))

        # Setup mock workflow
        mock_workflow = MagicMock()
        mock_workflow.name = "test-workflow"
        mock_workflow.type = "step"
        mock_workflow.description = "Test"
        mock_workflow.version = "1.0"
        mock_workflow.steps = []
        mock_workflow.triggers = {}
        mock_workflow.settings = {}
        mock_loader.load_workflow.return_value = mock_workflow

        # Patch get_workflow_project_path to return our tmp_path
        with patch("gobby.mcp_proxy.tools.workflows.get_workflow_project_path") as mock_discover:
            mock_discover.return_value = tmp_path

            result = call_tool(registry, "get_workflow", name="test-workflow")

            assert result["success"] is True
            mock_discover.assert_called_once()
            mock_loader.load_workflow.assert_called_once_with("test-workflow", tmp_path)

    def test_auto_discovery_fails_gracefully(self, registry, mock_loader):
        """Verify get_workflow handles auto-discovery failure gracefully."""
        mock_loader.load_workflow.return_value = None

        with patch("gobby.mcp_proxy.tools.workflows.get_workflow_project_path") as mock_discover:
            mock_discover.return_value = None

            result = call_tool(registry, "get_workflow", name="nonexistent-workflow")

            # Should still call load_workflow with None path
            assert result["success"] is False
            assert "not found" in result["error"]


class TestListWorkflowsWithProjectPath:
    """Tests for list_workflows with project_path parameter."""

    def test_with_explicit_project_path(self, registry, mock_loader, tmp_path):
        """Verify list_workflows works with explicit project_path."""
        # Create workflows directory with a workflow file
        workflows_dir = tmp_path / ".gobby" / "workflows"
        workflows_dir.mkdir(parents=True)
        (workflows_dir / "test.yaml").write_text("name: test\ntype: step\n")

        result = call_tool(registry, "list_workflows", project_path=str(tmp_path))

        assert "workflows" in result
        assert "count" in result

    def test_with_auto_discovery(self, registry, mock_loader, tmp_path):
        """Verify list_workflows uses auto-discovery when project_path not provided."""
        with patch("gobby.mcp_proxy.tools.workflows.get_workflow_project_path") as mock_discover:
            mock_discover.return_value = tmp_path

            result = call_tool(registry, "list_workflows")

            mock_discover.assert_called_once()
            assert "workflows" in result

    def test_no_project_path_no_discovery(self, registry, mock_loader):
        """Verify list_workflows works without project even when discovery fails."""
        with patch("gobby.mcp_proxy.tools.workflows.get_workflow_project_path") as mock_discover:
            mock_discover.return_value = None

            result = call_tool(registry, "list_workflows")

            # Should still return results (from global workflows)
            assert "workflows" in result
            assert "count" in result


class TestActivateWorkflowWithProjectPath:
    """Tests for activate_workflow with project_path parameter."""

    def test_with_explicit_project_path(self, registry, mock_loader, mock_state_manager, tmp_path):
        """Verify activate_workflow works with explicit project_path."""
        # Setup mock workflow
        mock_step = MagicMock()
        mock_step.name = "plan"
        mock_workflow = MagicMock()
        mock_workflow.name = "plan-execute"
        mock_workflow.type = "step"
        mock_workflow.steps = [mock_step]
        mock_workflow.variables = {}
        mock_loader.load_workflow.return_value = mock_workflow
        mock_state_manager.get_state.return_value = None

        result = call_tool(
            registry,
            "activate_workflow",
            name="plan-execute",
            session_id="test-session",
            project_path=str(tmp_path),
        )

        assert result["success"] is True
        mock_loader.load_workflow.assert_called_once_with("plan-execute", tmp_path)

    def test_with_auto_discovery(self, registry, mock_loader, mock_state_manager, tmp_path):
        """Verify activate_workflow uses auto-discovery when project_path not provided."""
        mock_step = MagicMock()
        mock_step.name = "work"
        mock_workflow = MagicMock()
        mock_workflow.name = "auto-task"
        mock_workflow.type = "step"
        mock_workflow.steps = [mock_step]
        mock_workflow.variables = {}
        mock_loader.load_workflow.return_value = mock_workflow
        mock_state_manager.get_state.return_value = None

        with patch("gobby.mcp_proxy.tools.workflows.get_workflow_project_path") as mock_discover:
            mock_discover.return_value = tmp_path

            result = call_tool(
                registry,
                "activate_workflow",
                name="auto-task",
                session_id="test-session",
            )

            assert result["success"] is True
            mock_discover.assert_called_once()


class TestRequestStepTransitionWithProjectPath:
    """Tests for request_step_transition with project_path parameter."""

    def test_with_explicit_project_path(self, registry, mock_loader, mock_state_manager, tmp_path):
        """Verify request_step_transition works with explicit project_path."""
        # Setup mock state
        mock_state = MagicMock()
        mock_state.workflow_name = "plan-execute"
        mock_state.step = "plan"
        mock_state_manager.get_state.return_value = mock_state

        # Setup mock workflow
        mock_step1 = MagicMock()
        mock_step1.name = "plan"
        mock_step2 = MagicMock()
        mock_step2.name = "execute"
        mock_workflow = MagicMock()
        mock_workflow.steps = [mock_step1, mock_step2]
        mock_loader.load_workflow.return_value = mock_workflow

        result = call_tool(
            registry,
            "request_step_transition",
            to_step="execute",
            session_id="test-session",
            project_path=str(tmp_path),
        )

        assert result["success"] is True
        assert result["to_step"] == "execute"
        mock_loader.load_workflow.assert_called_once_with("plan-execute", tmp_path)

    def test_with_auto_discovery(self, registry, mock_loader, mock_state_manager, tmp_path):
        """Verify request_step_transition uses auto-discovery."""
        mock_state = MagicMock()
        mock_state.workflow_name = "plan-execute"
        mock_state.step = "plan"
        mock_state_manager.get_state.return_value = mock_state

        mock_step1 = MagicMock()
        mock_step1.name = "plan"
        mock_step2 = MagicMock()
        mock_step2.name = "execute"
        mock_workflow = MagicMock()
        mock_workflow.steps = [mock_step1, mock_step2]
        mock_loader.load_workflow.return_value = mock_workflow

        with patch("gobby.mcp_proxy.tools.workflows.get_workflow_project_path") as mock_discover:
            mock_discover.return_value = tmp_path

            result = call_tool(
                registry,
                "request_step_transition",
                to_step="execute",
                session_id="test-session",
            )

            assert result["success"] is True
            mock_discover.assert_called_once()


class TestImportWorkflowWithProjectPath:
    """Tests for import_workflow with project_path parameter."""

    def test_with_explicit_project_path(self, registry, mock_loader, tmp_path):
        """Verify import_workflow works with explicit project_path."""
        # Create source workflow file
        source_file = tmp_path / "source" / "test.yaml"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("name: test-workflow\ntype: step\n")

        # Create project directory
        project = tmp_path / "project"
        project.mkdir()

        result = call_tool(
            registry,
            "import_workflow",
            source_path=str(source_file),
            project_path=str(project),
        )

        assert result["success"] is True
        assert (project / ".gobby" / "workflows" / "test-workflow.yaml").exists()

    def test_with_auto_discovery(self, registry, mock_loader, tmp_path):
        """Verify import_workflow uses auto-discovery when project_path not provided."""
        # Create source workflow file
        source_file = tmp_path / "source.yaml"
        source_file.write_text("name: discovered-workflow\ntype: step\n")

        project = tmp_path / "project"
        project.mkdir()

        with patch("gobby.mcp_proxy.tools.workflows.get_workflow_project_path") as mock_discover:
            mock_discover.return_value = project

            result = call_tool(
                registry,
                "import_workflow",
                source_path=str(source_file),
            )

            assert result["success"] is True
            mock_discover.assert_called_once()
            assert (project / ".gobby" / "workflows" / "discovered-workflow.yaml").exists()

    def test_auto_discovery_fails_returns_error(self, registry, mock_loader, tmp_path):
        """Verify import_workflow returns error when auto-discovery fails."""
        source_file = tmp_path / "source.yaml"
        source_file.write_text("name: test\ntype: step\n")

        with patch("gobby.mcp_proxy.tools.workflows.get_workflow_project_path") as mock_discover:
            mock_discover.return_value = None

            result = call_tool(
                registry,
                "import_workflow",
                source_path=str(source_file),
            )

            assert result["success"] is False
            assert "project_path required" in result["error"]


class TestWorktreeAutoDiscovery:
    """Tests for auto-discovery in worktree context."""

    def test_worktree_discovers_parent_project(self, registry, mock_loader, tmp_path):
        """Verify auto-discovery finds parent project from worktree."""
        # Setup parent project
        parent_project = tmp_path / "parent"
        parent_project.mkdir()
        parent_gobby = parent_project / ".gobby"
        parent_gobby.mkdir()
        (parent_gobby / "project.json").write_text(json.dumps({"id": "parent-id"}))

        # Setup worktree with parent reference
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        worktree_gobby = worktree / ".gobby"
        worktree_gobby.mkdir()
        (worktree_gobby / "project.json").write_text(
            json.dumps({"id": "worktree-id", "parent_project_path": str(parent_project)})
        )

        # Mock workflow
        mock_workflow = MagicMock()
        mock_workflow.name = "test"
        mock_workflow.type = "step"
        mock_workflow.description = ""
        mock_workflow.version = "1.0"
        mock_workflow.steps = []
        mock_workflow.triggers = {}
        mock_workflow.settings = {}
        mock_loader.load_workflow.return_value = mock_workflow

        # get_workflow_project_path should return parent when in worktree
        with patch("gobby.mcp_proxy.tools.workflows.get_workflow_project_path") as mock_discover:
            mock_discover.return_value = parent_project

            result = call_tool(registry, "get_workflow", name="test")

            assert result["success"] is True
            # Should use parent project path
            mock_loader.load_workflow.assert_called_once_with("test", parent_project)
