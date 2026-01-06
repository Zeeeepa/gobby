"""Integration tests for workflow tool filtering.

These tests verify the full workflow tool filtering flow with real database
operations and real workflow definitions.
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from gobby.mcp_proxy.services.tool_filter import ToolFilterService
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.projects import LocalProjectManager
from gobby.storage.sessions import LocalSessionManager
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = LocalDatabase(str(db_path))
        run_migrations(db)
        yield db


@pytest.fixture
def project(temp_db):
    """Create a test project."""
    project_manager = LocalProjectManager(temp_db)
    return project_manager.create(
        name="test-project",
        repo_path="/tmp/test-repo",
    )


@pytest.fixture
def session_storage(temp_db):
    """Create a session storage."""
    return LocalSessionManager(temp_db)


def create_session(session_storage, project, session_id: str):
    """Helper to create a session with a specific ID pattern."""
    session = session_storage.register(
        machine_id="test-machine",
        source="claude",
        project_id=project.id,
        external_id=f"ext-{session_id}",
        title=f"Test Session {session_id}",
    )
    return session


@pytest.fixture
def workflow_dir():
    """Create a temporary directory with test workflow files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_path = Path(tmpdir)

        # Create a restrictive workflow
        restrictive_workflow = {
            "name": "restrictive-workflow",
            "type": "step",
            "version": "1.0",
            "steps": [
                {
                    "name": "discovery",
                    "description": "Research and discovery phase",
                    "allowed_tools": ["read_file", "glob", "grep", "web_search"],
                    "blocked_tools": [],
                },
                {
                    "name": "planning",
                    "description": "Planning phase",
                    "allowed_tools": ["read_file", "write_plan"],
                    "blocked_tools": ["edit", "write", "bash"],
                },
                {
                    "name": "execution",
                    "description": "Implementation phase",
                    "allowed_tools": "all",
                    "blocked_tools": ["delete_file", "rm"],
                },
            ],
        }

        with open(workflow_path / "restrictive-workflow.yaml", "w") as f:
            yaml.dump(restrictive_workflow, f)

        # Create an open workflow (all tools allowed)
        open_workflow = {
            "name": "open-workflow",
            "type": "step",
            "version": "1.0",
            "steps": [
                {
                    "name": "open",
                    "description": "All tools allowed",
                    "allowed_tools": "all",
                    "blocked_tools": [],
                },
            ],
        }

        with open(workflow_path / "open-workflow.yaml", "w") as f:
            yaml.dump(open_workflow, f)

        # Create a minimal step workflow
        minimal_workflow = {
            "name": "minimal-workflow",
            "type": "step",
            "version": "1.0",
            "steps": [
                {
                    "name": "read-only",
                    "description": "Only read operations",
                    "allowed_tools": ["read"],
                    "blocked_tools": [],
                },
            ],
        }

        with open(workflow_path / "minimal-workflow.yaml", "w") as f:
            yaml.dump(minimal_workflow, f)

        yield workflow_path


@pytest.fixture
def loader(workflow_dir):
    """Create a workflow loader with test workflow directory."""
    return WorkflowLoader(workflow_dirs=[workflow_dir])


@pytest.fixture
def state_manager(temp_db):
    """Create a workflow state manager."""
    return WorkflowStateManager(temp_db)


@pytest.fixture
def filter_service(temp_db, loader, state_manager):
    """Create a ToolFilterService with real dependencies."""
    return ToolFilterService(
        db=temp_db,
        loader=loader,
        state_manager=state_manager,
    )


@pytest.fixture
def session_factory(session_storage, project):
    """Factory to create sessions for tests."""
    def _create(session_id: str):
        return create_session(session_storage, project, session_id)
    return _create


class TestToolFilteringWithRealWorkflows:
    """Tests for tool filtering with real workflow definitions."""

    def test_no_filtering_without_workflow_state(self, filter_service):
        """Tools are not filtered when no workflow state exists."""
        tools = [
            {"name": "read_file", "brief": "Read a file"},
            {"name": "write_file", "brief": "Write a file"},
            {"name": "delete_file", "brief": "Delete a file"},
        ]

        result = filter_service.filter_tools(tools, session_id="nonexistent-session")

        assert len(result) == 3
        assert result == tools

    def test_filtering_with_allowed_list(
        self, filter_service, state_manager, session_factory
    ):
        """Tools are filtered to allowed list when workflow active."""
        # Create session first (FK constraint)
        session = session_factory("allowed")

        # Set up workflow state
        state = WorkflowState(
            session_id=session.id,
            workflow_name="restrictive-workflow",
            step="discovery",
        )
        state_manager.save_state(state)

        tools = [
            {"name": "read_file", "brief": "Read a file"},
            {"name": "glob", "brief": "Search files"},
            {"name": "grep", "brief": "Search content"},
            {"name": "web_search", "brief": "Search web"},
            {"name": "edit", "brief": "Edit a file"},
            {"name": "write", "brief": "Write a file"},
            {"name": "bash", "brief": "Run command"},
        ]

        result = filter_service.filter_tools(tools, session_id=session.id)

        # Only allowed tools should remain
        assert len(result) == 4
        names = [t["name"] for t in result]
        assert "read_file" in names
        assert "glob" in names
        assert "grep" in names
        assert "web_search" in names
        assert "edit" not in names
        assert "write" not in names
        assert "bash" not in names

    def test_filtering_with_blocked_list(
        self, filter_service, state_manager, session_factory
    ):
        """Blocked tools are removed even when all tools allowed."""
        session = session_factory("blocked")

        # Set up workflow state in execution step
        state = WorkflowState(
            session_id=session.id,
            workflow_name="restrictive-workflow",
            step="execution",
        )
        state_manager.save_state(state)

        tools = [
            {"name": "read_file", "brief": "Read a file"},
            {"name": "edit", "brief": "Edit a file"},
            {"name": "write", "brief": "Write a file"},
            {"name": "delete_file", "brief": "Delete a file"},
            {"name": "rm", "brief": "Remove file"},
            {"name": "bash", "brief": "Run command"},
        ]

        result = filter_service.filter_tools(tools, session_id=session.id)

        # All except blocked tools should remain
        assert len(result) == 4
        names = [t["name"] for t in result]
        assert "read_file" in names
        assert "edit" in names
        assert "write" in names
        assert "bash" in names
        assert "delete_file" not in names
        assert "rm" not in names

    def test_filtering_with_both_allowed_and_blocked(
        self, filter_service, state_manager, session_factory
    ):
        """Combined allowed and blocked lists work correctly."""
        session = session_factory("combined")

        # Set up workflow state in planning step
        state = WorkflowState(
            session_id=session.id,
            workflow_name="restrictive-workflow",
            step="planning",
        )
        state_manager.save_state(state)

        tools = [
            {"name": "read_file", "brief": "Read a file"},
            {"name": "write_plan", "brief": "Write plan"},
            {"name": "edit", "brief": "Edit a file"},
            {"name": "write", "brief": "Write a file"},
            {"name": "bash", "brief": "Run command"},
            {"name": "glob", "brief": "Search files"},
        ]

        result = filter_service.filter_tools(tools, session_id=session.id)

        # Only read_file and write_plan allowed; edit, write, bash blocked
        assert len(result) == 2
        names = [t["name"] for t in result]
        assert "read_file" in names
        assert "write_plan" in names

    def test_no_filtering_with_open_workflow(
        self, filter_service, state_manager, session_factory
    ):
        """Open workflow allows all tools."""
        session = session_factory("open")

        state = WorkflowState(
            session_id=session.id,
            workflow_name="open-workflow",
            step="open",
        )
        state_manager.save_state(state)

        tools = [
            {"name": "read_file", "brief": "Read"},
            {"name": "edit", "brief": "Edit"},
            {"name": "write", "brief": "Write"},
            {"name": "bash", "brief": "Bash"},
            {"name": "delete", "brief": "Delete"},
        ]

        result = filter_service.filter_tools(tools, session_id=session.id)

        assert len(result) == 5
        assert result == tools


class TestIsToolAllowedWithRealWorkflows:
    """Tests for is_tool_allowed with real workflows."""

    def test_tool_allowed_no_workflow(self, filter_service):
        """Any tool is allowed when no workflow active."""
        allowed, reason = filter_service.is_tool_allowed("any_tool", "no-workflow-session")

        assert allowed is True
        assert reason is None

    def test_tool_allowed_in_allowed_list(
        self, filter_service, state_manager, session_factory
    ):
        """Tool in allowed list is permitted."""
        session = session_factory("check")

        state = WorkflowState(
            session_id=session.id,
            workflow_name="restrictive-workflow",
            step="discovery",
        )
        state_manager.save_state(state)

        allowed, reason = filter_service.is_tool_allowed("read_file", session.id)

        assert allowed is True
        assert reason is None

    def test_tool_not_in_allowed_list(
        self, filter_service, state_manager, session_factory
    ):
        """Tool not in allowed list is blocked."""
        session = session_factory("check2")

        state = WorkflowState(
            session_id=session.id,
            workflow_name="restrictive-workflow",
            step="discovery",
        )
        state_manager.save_state(state)

        allowed, reason = filter_service.is_tool_allowed("edit", session.id)

        assert allowed is False
        assert "not in allowed list" in reason.lower()

    def test_tool_in_blocked_list(
        self, filter_service, state_manager, session_factory
    ):
        """Tool in blocked list is blocked even with 'all' allowed."""
        session = session_factory("check3")

        state = WorkflowState(
            session_id=session.id,
            workflow_name="restrictive-workflow",
            step="execution",
        )
        state_manager.save_state(state)

        allowed, reason = filter_service.is_tool_allowed("delete_file", session.id)

        assert allowed is False
        assert "blocked" in reason.lower()

    def test_tool_allowed_when_all_allowed(
        self, filter_service, state_manager, session_factory
    ):
        """Any non-blocked tool is allowed when allowed_tools is 'all'."""
        session = session_factory("check4")

        state = WorkflowState(
            session_id=session.id,
            workflow_name="restrictive-workflow",
            step="execution",
        )
        state_manager.save_state(state)

        allowed, reason = filter_service.is_tool_allowed("bash", session.id)

        assert allowed is True
        assert reason is None


class TestGetStepRestrictionsWithRealWorkflows:
    """Tests for get_step_restrictions with real workflows."""

    def test_returns_none_for_nonexistent_session(self, filter_service):
        """Returns None when session has no workflow state."""
        result = filter_service.get_step_restrictions("nonexistent")

        assert result is None

    def test_returns_restrictions_for_active_workflow(
        self, filter_service, state_manager, session_factory
    ):
        """Returns restrictions when workflow is active."""
        session = session_factory("restrictions")

        state = WorkflowState(
            session_id=session.id,
            workflow_name="restrictive-workflow",
            step="discovery",
        )
        state_manager.save_state(state)

        result = filter_service.get_step_restrictions(session.id)

        assert result is not None
        assert result["workflow_name"] == "restrictive-workflow"
        assert result["step"] == "discovery"
        assert "read_file" in result["allowed_tools"]
        assert result["blocked_tools"] == []

    def test_returns_all_for_open_step(
        self, filter_service, state_manager, session_factory
    ):
        """Returns 'all' for allowed_tools when step allows all."""
        session = session_factory("open-step")

        state = WorkflowState(
            session_id=session.id,
            workflow_name="restrictive-workflow",
            step="execution",
        )
        state_manager.save_state(state)

        result = filter_service.get_step_restrictions(session.id)

        assert result["allowed_tools"] == "all"
        assert "delete_file" in result["blocked_tools"]


class TestFilterServersToolsWithRealWorkflows:
    """Tests for filter_servers_tools with real workflows."""

    def test_filters_across_multiple_servers(
        self, filter_service, state_manager, session_factory
    ):
        """Filters tools across multiple servers correctly."""
        session = session_factory("multi")

        state = WorkflowState(
            session_id=session.id,
            workflow_name="minimal-workflow",
            step="read-only",
        )
        state_manager.save_state(state)

        servers = [
            {
                "name": "file-tools",
                "tools": [
                    {"name": "read", "brief": "Read file"},
                    {"name": "write", "brief": "Write file"},
                    {"name": "edit", "brief": "Edit file"},
                ],
            },
            {
                "name": "search-tools",
                "tools": [
                    {"name": "glob", "brief": "Search"},
                    {"name": "grep", "brief": "Grep"},
                ],
            },
        ]

        result = filter_service.filter_servers_tools(servers, session_id=session.id)

        assert len(result) == 2

        # First server should only have 'read'
        assert result[0]["name"] == "file-tools"
        assert len(result[0]["tools"]) == 1
        assert result[0]["tools"][0]["name"] == "read"

        # Second server should be empty (no allowed tools)
        assert result[1]["name"] == "search-tools"
        assert result[1]["tools"] == []

    def test_no_filtering_without_session(self, filter_service):
        """Returns all servers and tools when no session_id."""
        servers = [
            {"name": "server1", "tools": [{"name": "tool1", "brief": "d1"}]},
            {"name": "server2", "tools": [{"name": "tool2", "brief": "d2"}]},
        ]

        result = filter_service.filter_servers_tools(servers, session_id=None)

        assert result == servers


class TestWorkflowStateTransitions:
    """Tests for tool filtering after workflow step transitions."""

    def test_filtering_changes_after_step_transition(
        self, filter_service, state_manager, session_factory
    ):
        """Tool filtering changes when workflow step changes."""
        session = session_factory("transition")

        # Start in discovery step
        state = WorkflowState(
            session_id=session.id,
            workflow_name="restrictive-workflow",
            step="discovery",
        )
        state_manager.save_state(state)

        tools = [
            {"name": "read_file", "brief": "Read"},
            {"name": "edit", "brief": "Edit"},
            {"name": "delete_file", "brief": "Delete"},
        ]

        # Discovery step: only read_file allowed
        result = filter_service.filter_tools(tools, session_id=session.id)
        assert len(result) == 1
        assert result[0]["name"] == "read_file"

        # Transition to execution step
        state.step = "execution"
        state_manager.save_state(state)

        # Execution step: all except delete_file allowed
        result = filter_service.filter_tools(tools, session_id=session.id)
        assert len(result) == 2
        names = [t["name"] for t in result]
        assert "read_file" in names
        assert "edit" in names
        assert "delete_file" not in names


class TestMultipleSessions:
    """Tests for tool filtering with multiple concurrent sessions."""

    def test_different_sessions_different_workflows(
        self, filter_service, state_manager, session_factory
    ):
        """Different sessions can have different workflow states."""
        session1 = session_factory("s1")
        session2 = session_factory("s2")

        # Session 1: restrictive workflow
        state1 = WorkflowState(
            session_id=session1.id,
            workflow_name="restrictive-workflow",
            step="discovery",
        )
        state_manager.save_state(state1)

        # Session 2: open workflow
        state2 = WorkflowState(
            session_id=session2.id,
            workflow_name="open-workflow",
            step="open",
        )
        state_manager.save_state(state2)

        tools = [
            {"name": "read_file", "brief": "Read"},
            {"name": "edit", "brief": "Edit"},
            {"name": "write", "brief": "Write"},
        ]

        # Session 1: only discovery tools
        result1 = filter_service.filter_tools(tools, session_id=session1.id)
        assert len(result1) == 1
        assert result1[0]["name"] == "read_file"

        # Session 2: all tools
        result2 = filter_service.filter_tools(tools, session_id=session2.id)
        assert len(result2) == 3

    def test_sessions_with_different_steps(
        self, filter_service, state_manager, session_factory
    ):
        """Same workflow but different steps have different filtering."""
        session_disc = session_factory("disc")
        session_exec = session_factory("exec")

        # Session 1: discovery step
        state1 = WorkflowState(
            session_id=session_disc.id,
            workflow_name="restrictive-workflow",
            step="discovery",
        )
        state_manager.save_state(state1)

        # Session 2: execution step
        state2 = WorkflowState(
            session_id=session_exec.id,
            workflow_name="restrictive-workflow",
            step="execution",
        )
        state_manager.save_state(state2)

        tools = [
            {"name": "read_file", "brief": "Read"},
            {"name": "bash", "brief": "Bash"},
            {"name": "delete_file", "brief": "Delete"},
        ]

        # Session 1 (discovery): only read_file
        result1 = filter_service.filter_tools(tools, session_id=session_disc.id)
        names1 = [t["name"] for t in result1]
        assert "read_file" in names1
        assert "bash" not in names1

        # Session 2 (execution): read_file and bash (delete_file blocked)
        result2 = filter_service.filter_tools(tools, session_id=session_exec.id)
        names2 = [t["name"] for t in result2]
        assert "read_file" in names2
        assert "bash" in names2
        assert "delete_file" not in names2


class TestEdgeCases:
    """Tests for edge cases in tool filtering."""

    def test_empty_tools_list(self, filter_service, state_manager, session_factory):
        """Empty tools list returns empty list."""
        session = session_factory("empty")

        state = WorkflowState(
            session_id=session.id,
            workflow_name="restrictive-workflow",
            step="discovery",
        )
        state_manager.save_state(state)

        result = filter_service.filter_tools([], session_id=session.id)

        assert result == []

    def test_tool_with_missing_name(self, filter_service, state_manager, session_factory):
        """Tools without name are filtered out."""
        session = session_factory("noname")

        state = WorkflowState(
            session_id=session.id,
            workflow_name="minimal-workflow",
            step="read-only",
        )
        state_manager.save_state(state)

        tools = [
            {"name": "read", "brief": "Read"},
            {"brief": "No name tool"},  # Missing name
            {"name": "", "brief": "Empty name"},
        ]

        result = filter_service.filter_tools(tools, session_id=session.id)

        # Only "read" should remain
        assert len(result) == 1
        assert result[0]["name"] == "read"

    def test_nonexistent_workflow_returns_none(
        self, filter_service, state_manager, session_factory
    ):
        """Nonexistent workflow in state returns None restrictions."""
        session = session_factory("bad-workflow")

        state = WorkflowState(
            session_id=session.id,
            workflow_name="nonexistent-workflow",
            step="any-step",
        )
        state_manager.save_state(state)

        result = filter_service.get_step_restrictions(session.id)

        assert result is None

    def test_nonexistent_step_returns_none(
        self, filter_service, state_manager, session_factory
    ):
        """Nonexistent step in workflow returns None restrictions."""
        session = session_factory("bad-step")

        state = WorkflowState(
            session_id=session.id,
            workflow_name="restrictive-workflow",
            step="nonexistent-step",
        )
        state_manager.save_state(state)

        result = filter_service.get_step_restrictions(session.id)

        assert result is None
