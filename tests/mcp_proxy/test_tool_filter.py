"""Tests for ToolFilterService."""

import pytest
from unittest.mock import MagicMock, patch

from gobby.mcp_proxy.services.tool_filter import ToolFilterService


class TestToolFilterService:
    """Tests for ToolFilterService."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        return MagicMock()

    @pytest.fixture
    def mock_state_manager(self):
        """Create a mock workflow state manager."""
        return MagicMock()

    @pytest.fixture
    def mock_loader(self):
        """Create a mock workflow loader."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db, mock_loader, mock_state_manager):
        """Create a ToolFilterService instance."""
        return ToolFilterService(
            db=mock_db,
            loader=mock_loader,
            state_manager=mock_state_manager,
        )

    @pytest.fixture
    def service_no_state_manager(self, mock_db, mock_loader):
        """Create a ToolFilterService without state manager."""
        return ToolFilterService(db=mock_db, loader=mock_loader, state_manager=None)


class TestGetPhaseRestrictions:
    """Tests for get_phase_restrictions method."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def mock_state_manager(self):
        return MagicMock()

    @pytest.fixture
    def mock_loader(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db, mock_loader, mock_state_manager):
        return ToolFilterService(
            db=mock_db,
            loader=mock_loader,
            state_manager=mock_state_manager,
        )

    def test_returns_none_without_state_manager(self, mock_db, mock_loader):
        """Test returns None when no state manager is available."""
        service = ToolFilterService(db=None, loader=mock_loader, state_manager=None)
        result = service.get_phase_restrictions("session-123")
        assert result is None

    def test_returns_none_when_no_workflow_state(self, service, mock_state_manager):
        """Test returns None when session has no workflow state."""
        mock_state_manager.get_state.return_value = None
        result = service.get_phase_restrictions("session-123")
        assert result is None
        mock_state_manager.get_state.assert_called_once_with("session-123")

    def test_returns_none_when_workflow_not_found(
        self, service, mock_state_manager, mock_loader
    ):
        """Test returns None when workflow definition is not found."""
        mock_state = MagicMock()
        mock_state.workflow_name = "unknown-workflow"
        mock_state.phase = "phase1"
        mock_state_manager.get_state.return_value = mock_state
        mock_loader.load_workflow.return_value = None

        result = service.get_phase_restrictions("session-123")
        assert result is None

    def test_returns_none_when_phase_not_found(
        self, service, mock_state_manager, mock_loader
    ):
        """Test returns None when phase is not found in workflow."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.phase = "unknown-phase"
        mock_state_manager.get_state.return_value = mock_state

        mock_definition = MagicMock()
        mock_definition.get_phase.return_value = None
        mock_loader.load_workflow.return_value = mock_definition

        result = service.get_phase_restrictions("session-123")
        assert result is None

    def test_returns_restrictions_when_found(
        self, service, mock_state_manager, mock_loader
    ):
        """Test returns phase restrictions when workflow and phase found."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.phase = "discovery"
        mock_state_manager.get_state.return_value = mock_state

        mock_phase = MagicMock()
        mock_phase.allowed_tools = ["search", "read"]
        mock_phase.blocked_tools = ["write", "delete"]

        mock_definition = MagicMock()
        mock_definition.get_phase.return_value = mock_phase
        mock_loader.load_workflow.return_value = mock_definition

        result = service.get_phase_restrictions("session-123")

        assert result == {
            "workflow_name": "test-workflow",
            "phase": "discovery",
            "allowed_tools": ["search", "read"],
            "blocked_tools": ["write", "delete"],
        }

    def test_returns_all_allowed_tools(self, service, mock_state_manager, mock_loader):
        """Test returns 'all' for allowed_tools when phase allows all."""
        mock_state = MagicMock()
        mock_state.workflow_name = "open-workflow"
        mock_state.phase = "open-phase"
        mock_state_manager.get_state.return_value = mock_state

        mock_phase = MagicMock()
        mock_phase.allowed_tools = "all"
        mock_phase.blocked_tools = []

        mock_definition = MagicMock()
        mock_definition.get_phase.return_value = mock_phase
        mock_loader.load_workflow.return_value = mock_definition

        result = service.get_phase_restrictions("session-123")

        assert result["allowed_tools"] == "all"
        assert result["blocked_tools"] == []


class TestIsToolAllowed:
    """Tests for is_tool_allowed method."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def mock_state_manager(self):
        return MagicMock()

    @pytest.fixture
    def mock_loader(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db, mock_loader, mock_state_manager):
        return ToolFilterService(
            db=mock_db,
            loader=mock_loader,
            state_manager=mock_state_manager,
        )

    def test_allowed_when_no_workflow_active(self, service, mock_state_manager):
        """Test tool is allowed when no workflow is active."""
        mock_state_manager.get_state.return_value = None

        allowed, reason = service.is_tool_allowed("any-tool", "session-123")

        assert allowed is True
        assert reason is None

    def test_blocked_when_in_blocked_list(self, service, mock_state_manager, mock_loader):
        """Test tool is blocked when in blocked_tools list."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.phase = "restricted"
        mock_state_manager.get_state.return_value = mock_state

        mock_phase = MagicMock()
        mock_phase.allowed_tools = "all"
        mock_phase.blocked_tools = ["dangerous-tool"]

        mock_definition = MagicMock()
        mock_definition.get_phase.return_value = mock_phase
        mock_loader.load_workflow.return_value = mock_definition

        allowed, reason = service.is_tool_allowed("dangerous-tool", "session-123")

        assert allowed is False
        assert "blocked" in reason.lower()
        assert "restricted" in reason

    def test_allowed_when_in_allowed_list(self, service, mock_state_manager, mock_loader):
        """Test tool is allowed when in allowed_tools list."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.phase = "discovery"
        mock_state_manager.get_state.return_value = mock_state

        mock_phase = MagicMock()
        mock_phase.allowed_tools = ["search", "read"]
        mock_phase.blocked_tools = []

        mock_definition = MagicMock()
        mock_definition.get_phase.return_value = mock_phase
        mock_loader.load_workflow.return_value = mock_definition

        allowed, reason = service.is_tool_allowed("search", "session-123")

        assert allowed is True
        assert reason is None

    def test_not_allowed_when_not_in_allowed_list(
        self, service, mock_state_manager, mock_loader
    ):
        """Test tool is not allowed when not in allowed_tools list."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.phase = "discovery"
        mock_state_manager.get_state.return_value = mock_state

        mock_phase = MagicMock()
        mock_phase.allowed_tools = ["search", "read"]
        mock_phase.blocked_tools = []

        mock_definition = MagicMock()
        mock_definition.get_phase.return_value = mock_phase
        mock_loader.load_workflow.return_value = mock_definition

        allowed, reason = service.is_tool_allowed("write", "session-123")

        assert allowed is False
        assert "not in allowed list" in reason.lower()

    def test_allowed_when_all_tools_allowed(
        self, service, mock_state_manager, mock_loader
    ):
        """Test any tool is allowed when allowed_tools is 'all'."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.phase = "open"
        mock_state_manager.get_state.return_value = mock_state

        mock_phase = MagicMock()
        mock_phase.allowed_tools = "all"
        mock_phase.blocked_tools = []

        mock_definition = MagicMock()
        mock_definition.get_phase.return_value = mock_phase
        mock_loader.load_workflow.return_value = mock_definition

        allowed, reason = service.is_tool_allowed("any-tool", "session-123")

        assert allowed is True
        assert reason is None

    def test_blocked_takes_priority_over_allowed_all(
        self, service, mock_state_manager, mock_loader
    ):
        """Test blocked list takes priority even when allowed_tools is 'all'."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.phase = "open-but-restricted"
        mock_state_manager.get_state.return_value = mock_state

        mock_phase = MagicMock()
        mock_phase.allowed_tools = "all"
        mock_phase.blocked_tools = ["dangerous"]

        mock_definition = MagicMock()
        mock_definition.get_phase.return_value = mock_phase
        mock_loader.load_workflow.return_value = mock_definition

        allowed, reason = service.is_tool_allowed("dangerous", "session-123")

        assert allowed is False
        assert "blocked" in reason.lower()


class TestFilterTools:
    """Tests for filter_tools method."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def mock_state_manager(self):
        return MagicMock()

    @pytest.fixture
    def mock_loader(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db, mock_loader, mock_state_manager):
        return ToolFilterService(
            db=mock_db,
            loader=mock_loader,
            state_manager=mock_state_manager,
        )

    def test_returns_all_tools_without_session_id(self, service):
        """Test returns all tools when no session_id provided."""
        tools = [
            {"name": "tool1", "brief": "desc1"},
            {"name": "tool2", "brief": "desc2"},
        ]

        result = service.filter_tools(tools, session_id=None)

        assert result == tools

    def test_returns_all_tools_when_no_workflow_active(
        self, service, mock_state_manager
    ):
        """Test returns all tools when no workflow is active."""
        mock_state_manager.get_state.return_value = None

        tools = [
            {"name": "tool1", "brief": "desc1"},
            {"name": "tool2", "brief": "desc2"},
        ]

        result = service.filter_tools(tools, session_id="session-123")

        assert result == tools

    def test_filters_blocked_tools(self, service, mock_state_manager, mock_loader):
        """Test filters out tools in blocked list."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.phase = "restricted"
        mock_state_manager.get_state.return_value = mock_state

        mock_phase = MagicMock()
        mock_phase.allowed_tools = "all"
        mock_phase.blocked_tools = ["tool2"]

        mock_definition = MagicMock()
        mock_definition.get_phase.return_value = mock_phase
        mock_loader.load_workflow.return_value = mock_definition

        tools = [
            {"name": "tool1", "brief": "desc1"},
            {"name": "tool2", "brief": "desc2"},
            {"name": "tool3", "brief": "desc3"},
        ]

        result = service.filter_tools(tools, session_id="session-123")

        assert len(result) == 2
        assert {"name": "tool1", "brief": "desc1"} in result
        assert {"name": "tool3", "brief": "desc3"} in result
        assert {"name": "tool2", "brief": "desc2"} not in result

    def test_filters_to_allowed_list(self, service, mock_state_manager, mock_loader):
        """Test filters to only allowed tools when list specified."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.phase = "discovery"
        mock_state_manager.get_state.return_value = mock_state

        mock_phase = MagicMock()
        mock_phase.allowed_tools = ["tool1", "tool3"]
        mock_phase.blocked_tools = []

        mock_definition = MagicMock()
        mock_definition.get_phase.return_value = mock_phase
        mock_loader.load_workflow.return_value = mock_definition

        tools = [
            {"name": "tool1", "brief": "desc1"},
            {"name": "tool2", "brief": "desc2"},
            {"name": "tool3", "brief": "desc3"},
        ]

        result = service.filter_tools(tools, session_id="session-123")

        assert len(result) == 2
        assert {"name": "tool1", "brief": "desc1"} in result
        assert {"name": "tool3", "brief": "desc3"} in result

    def test_blocked_takes_priority_in_filter(
        self, service, mock_state_manager, mock_loader
    ):
        """Test blocked tools are filtered even if in allowed list."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.phase = "mixed"
        mock_state_manager.get_state.return_value = mock_state

        mock_phase = MagicMock()
        mock_phase.allowed_tools = ["tool1", "tool2", "tool3"]
        mock_phase.blocked_tools = ["tool2"]  # Blocked takes priority

        mock_definition = MagicMock()
        mock_definition.get_phase.return_value = mock_phase
        mock_loader.load_workflow.return_value = mock_definition

        tools = [
            {"name": "tool1", "brief": "desc1"},
            {"name": "tool2", "brief": "desc2"},
            {"name": "tool3", "brief": "desc3"},
        ]

        result = service.filter_tools(tools, session_id="session-123")

        assert len(result) == 2
        assert {"name": "tool2", "brief": "desc2"} not in result


class TestFilterServersTools:
    """Tests for filter_servers_tools method."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def mock_state_manager(self):
        return MagicMock()

    @pytest.fixture
    def mock_loader(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db, mock_loader, mock_state_manager):
        return ToolFilterService(
            db=mock_db,
            loader=mock_loader,
            state_manager=mock_state_manager,
        )

    def test_returns_all_when_no_session_id(self, service):
        """Test returns all servers and tools when no session_id."""
        servers = [
            {"name": "server1", "tools": [{"name": "tool1", "brief": "d1"}]},
            {"name": "server2", "tools": [{"name": "tool2", "brief": "d2"}]},
        ]

        result = service.filter_servers_tools(servers, session_id=None)

        assert result == servers

    def test_filters_tools_across_servers(
        self, service, mock_state_manager, mock_loader
    ):
        """Test filters tools across multiple servers."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.phase = "restricted"
        mock_state_manager.get_state.return_value = mock_state

        mock_phase = MagicMock()
        mock_phase.allowed_tools = ["tool1", "tool3"]
        mock_phase.blocked_tools = []

        mock_definition = MagicMock()
        mock_definition.get_phase.return_value = mock_phase
        mock_loader.load_workflow.return_value = mock_definition

        servers = [
            {
                "name": "server1",
                "tools": [
                    {"name": "tool1", "brief": "d1"},
                    {"name": "tool2", "brief": "d2"},
                ],
            },
            {
                "name": "server2",
                "tools": [
                    {"name": "tool3", "brief": "d3"},
                    {"name": "tool4", "brief": "d4"},
                ],
            },
        ]

        result = service.filter_servers_tools(servers, session_id="session-123")

        assert len(result) == 2
        assert result[0]["name"] == "server1"
        assert len(result[0]["tools"]) == 1
        assert result[0]["tools"][0]["name"] == "tool1"

        assert result[1]["name"] == "server2"
        assert len(result[1]["tools"]) == 1
        assert result[1]["tools"][0]["name"] == "tool3"

    def test_keeps_empty_servers(self, service, mock_state_manager, mock_loader):
        """Test keeps servers even when all tools filtered out."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.phase = "very-restricted"
        mock_state_manager.get_state.return_value = mock_state

        mock_phase = MagicMock()
        mock_phase.allowed_tools = ["nonexistent"]
        mock_phase.blocked_tools = []

        mock_definition = MagicMock()
        mock_definition.get_phase.return_value = mock_phase
        mock_loader.load_workflow.return_value = mock_definition

        servers = [
            {"name": "server1", "tools": [{"name": "tool1", "brief": "d1"}]},
        ]

        result = service.filter_servers_tools(servers, session_id="session-123")

        assert len(result) == 1
        assert result[0]["name"] == "server1"
        assert result[0]["tools"] == []


class TestLazyInitialization:
    """Tests for lazy initialization of state manager and loader."""

    def test_creates_state_manager_from_db(self):
        """Test state manager is lazily created from db."""
        mock_db = MagicMock()
        service = ToolFilterService(db=mock_db, loader=None, state_manager=None)

        # Patch at source module since import happens locally in method
        with patch(
            "gobby.workflows.state_manager.WorkflowStateManager"
        ) as mock_class:
            mock_class.return_value = MagicMock()
            mock_class.return_value.get_state.return_value = None

            service.get_phase_restrictions("session-123")

            mock_class.assert_called_once_with(mock_db)

    def test_creates_loader_when_needed(self):
        """Test workflow loader is lazily created."""
        mock_db = MagicMock()
        mock_state_manager = MagicMock()
        mock_state = MagicMock()
        mock_state.workflow_name = "test"
        mock_state.phase = "phase1"
        mock_state_manager.get_state.return_value = mock_state

        service = ToolFilterService(
            db=mock_db, loader=None, state_manager=mock_state_manager
        )

        # Patch at source module since import happens locally in method
        with patch(
            "gobby.workflows.loader.WorkflowLoader"
        ) as mock_class:
            mock_loader = MagicMock()
            mock_loader.load_workflow.return_value = None
            mock_class.return_value = mock_loader

            service.get_phase_restrictions("session-123")

            mock_class.assert_called_once()

    def test_reuses_existing_state_manager(self):
        """Test existing state manager is reused."""
        mock_state_manager = MagicMock()
        mock_state_manager.get_state.return_value = None

        service = ToolFilterService(
            db=MagicMock(), loader=None, state_manager=mock_state_manager
        )

        # Patch at source module since import happens locally in method
        with patch(
            "gobby.workflows.state_manager.WorkflowStateManager"
        ) as mock_class:
            service.get_phase_restrictions("session-123")
            service.get_phase_restrictions("session-456")

            # Should not create new instance - use existing
            mock_class.assert_not_called()

    def test_reuses_existing_loader(self):
        """Test existing loader is reused."""
        mock_loader = MagicMock()
        mock_loader.load_workflow.return_value = None
        mock_state_manager = MagicMock()
        mock_state = MagicMock()
        mock_state.workflow_name = "test"
        mock_state.phase = "phase1"
        mock_state_manager.get_state.return_value = mock_state

        service = ToolFilterService(
            db=MagicMock(), loader=mock_loader, state_manager=mock_state_manager
        )

        # Patch at source module since import happens locally in method
        with patch(
            "gobby.workflows.loader.WorkflowLoader"
        ) as mock_class:
            service.get_phase_restrictions("session-123")
            service.get_phase_restrictions("session-456")

            # Should not create new instance - use existing
            mock_class.assert_not_called()
