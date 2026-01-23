"""Tests for Claude Code Task Interop Adapter."""

from unittest.mock import MagicMock, patch

import pytest

from gobby.adapters.claude_code_tasks import (
    CC_TASK_TOOLS,
    CC_TO_GOBBY_STATUS,
    GOBBY_TO_CC_STATUS,
    ClaudeCodeTaskAdapter,
)


class TestStatusMappings:
    """Test status mapping constants."""

    def test_cc_to_gobby_status_mapping(self):
        """Test Claude Code to Gobby status mapping."""
        assert CC_TO_GOBBY_STATUS["pending"] == "open"
        assert CC_TO_GOBBY_STATUS["in_progress"] == "in_progress"
        assert CC_TO_GOBBY_STATUS["completed"] == "closed"

    def test_gobby_to_cc_status_mapping(self):
        """Test Gobby to Claude Code status mapping."""
        assert GOBBY_TO_CC_STATUS["open"] == "pending"
        assert GOBBY_TO_CC_STATUS["in_progress"] == "in_progress"
        assert GOBBY_TO_CC_STATUS["closed"] == "completed"
        assert GOBBY_TO_CC_STATUS["review"] == "in_progress"

    def test_cc_task_tools_set(self):
        """Test CC task tools are defined."""
        assert "TaskCreate" in CC_TASK_TOOLS
        assert "TaskUpdate" in CC_TASK_TOOLS
        assert "TaskList" in CC_TASK_TOOLS
        assert "TaskGet" in CC_TASK_TOOLS
        assert len(CC_TASK_TOOLS) == 4


class TestClaudeCodeTaskAdapter:
    """Test ClaudeCodeTaskAdapter class."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock task manager."""
        manager = MagicMock()
        return manager

    @pytest.fixture
    def adapter(self, mock_task_manager):
        """Create an adapter instance."""
        return ClaudeCodeTaskAdapter(
            task_manager=mock_task_manager,
            session_id="test-session-123",
            project_id="test-project-456",
        )

    def test_is_cc_task_tool(self):
        """Test is_cc_task_tool static method."""
        assert ClaudeCodeTaskAdapter.is_cc_task_tool("TaskCreate") is True
        assert ClaudeCodeTaskAdapter.is_cc_task_tool("TaskUpdate") is True
        assert ClaudeCodeTaskAdapter.is_cc_task_tool("TaskList") is True
        assert ClaudeCodeTaskAdapter.is_cc_task_tool("TaskGet") is True
        assert ClaudeCodeTaskAdapter.is_cc_task_tool("Edit") is False
        assert ClaudeCodeTaskAdapter.is_cc_task_tool("Write") is False

    def test_get_cc_status(self):
        """Test get_cc_status static method."""
        assert ClaudeCodeTaskAdapter.get_cc_status("open") == "pending"
        assert ClaudeCodeTaskAdapter.get_cc_status("closed") == "completed"
        assert ClaudeCodeTaskAdapter.get_cc_status("unknown") == "pending"

    def test_get_gobby_status(self):
        """Test get_gobby_status static method."""
        assert ClaudeCodeTaskAdapter.get_gobby_status("pending") == "open"
        assert ClaudeCodeTaskAdapter.get_gobby_status("completed") == "closed"
        assert ClaudeCodeTaskAdapter.get_gobby_status("unknown") == "open"


class TestSyncTaskCreate:
    """Test sync_task_create method."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock task manager."""
        manager = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "gobby-task-uuid"
        mock_task.seq_num = 42
        manager.create_task.return_value = mock_task
        return manager

    @pytest.fixture
    def adapter(self, mock_task_manager):
        """Create an adapter instance."""
        return ClaudeCodeTaskAdapter(
            task_manager=mock_task_manager,
            session_id="test-session-123",
            project_id="test-project-456",
        )

    def test_sync_task_create_success(self, adapter, mock_task_manager):
        """Test successful task creation sync."""
        tool_input = {
            "subject": "Test Task",
            "description": "A test description",
            "activeForm": "Testing task",
        }
        tool_result = {"id": "cc-task-1"}

        result = adapter.sync_task_create(tool_input, tool_result)

        assert result is not None
        assert result["gobby_id"] == "gobby-task-uuid"
        assert result["seq_num"] == 42
        assert result["ref"] == "#42"

        mock_task_manager.create_task.assert_called_once()
        call_kwargs = mock_task_manager.create_task.call_args.kwargs
        assert call_kwargs["title"] == "Test Task"
        # Description includes cc_task_id marker for later lookup
        assert "A test description" in call_kwargs["description"]
        assert "<!-- cc_task_id: cc-task-1 -->" in call_kwargs["description"]
        assert call_kwargs["project_id"] == "test-project-456"
        assert call_kwargs["created_in_session_id"] == "test-session-123"

    def test_sync_task_create_with_gobby_metadata(self, adapter, mock_task_manager):
        """Test task creation with Gobby-specific metadata."""
        tool_input = {
            "subject": "Feature Task",
            "metadata": {
                "gobby": {
                    "task_type": "feature",
                    "priority": 1,
                    "validation_criteria": "All tests pass",
                    "category": "code",
                }
            },
        }
        tool_result = {"id": "cc-task-2"}

        result = adapter.sync_task_create(tool_input, tool_result)

        assert result is not None
        call_kwargs = mock_task_manager.create_task.call_args.kwargs
        assert call_kwargs["task_type"] == "feature"
        assert call_kwargs["priority"] == 1
        assert call_kwargs["validation_criteria"] == "All tests pass"
        assert call_kwargs["category"] == "code"

    def test_sync_task_create_no_result(self, adapter, mock_task_manager):
        """Test task creation with no result."""
        result = adapter.sync_task_create({"subject": "Test"}, None)
        assert result is None
        mock_task_manager.create_task.assert_not_called()

    def test_sync_task_create_no_id_in_result(self, adapter, mock_task_manager):
        """Test task creation with result missing id."""
        result = adapter.sync_task_create({"subject": "Test"}, {"status": "pending"})
        assert result is None
        mock_task_manager.create_task.assert_not_called()


class TestSyncTaskUpdate:
    """Test sync_task_update method."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock task manager."""
        manager = MagicMock()
        return manager

    @pytest.fixture
    def adapter(self, mock_task_manager):
        """Create an adapter instance."""
        adapter = ClaudeCodeTaskAdapter(
            task_manager=mock_task_manager,
            session_id="test-session-123",
            project_id="test-project-456",
        )
        return adapter

    def test_sync_task_update_no_task_id(self, adapter):
        """Test update with no task ID."""
        result = adapter.sync_task_update({"status": "completed"}, {})
        assert result is None

    def test_sync_task_update_task_not_found(self, adapter, mock_task_manager):
        """Test update when Gobby task not found."""
        mock_task_manager.list_tasks.return_value = []

        result = adapter.sync_task_update({"taskId": "cc-task-1", "status": "completed"}, {})
        assert result is None


class TestHandlePostTool:
    """Test handle_post_tool method."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock task manager."""
        manager = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "gobby-task-uuid"
        mock_task.seq_num = 42
        manager.create_task.return_value = mock_task
        return manager

    @pytest.fixture
    def adapter(self, mock_task_manager):
        """Create an adapter instance."""
        return ClaudeCodeTaskAdapter(
            task_manager=mock_task_manager,
            session_id="test-session-123",
            project_id="test-project-456",
        )

    def test_handle_post_tool_task_create(self, adapter):
        """Test handling TaskCreate tool."""
        result = adapter.handle_post_tool(
            "TaskCreate",
            {"subject": "New Task"},
            {"id": "cc-123"},
        )
        assert result is not None
        assert "gobby_id" in result

    def test_handle_post_tool_non_task_tool(self, adapter):
        """Test handling non-task tool returns None."""
        result = adapter.handle_post_tool("Edit", {}, {})
        assert result is None

    def test_handle_post_tool_task_list(self, adapter):
        """Test TaskList doesn't sync (read-only)."""
        result = adapter.handle_post_tool("TaskList", {}, {"tasks": []})
        assert result is None

    def test_handle_post_tool_task_get(self, adapter):
        """Test TaskGet doesn't sync (read-only)."""
        result = adapter.handle_post_tool("TaskGet", {"taskId": "1"}, {"id": "1"})
        assert result is None


class TestEnrichTaskData:
    """Test enrich_task_data method."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock task manager."""
        manager = MagicMock()
        return manager

    @pytest.fixture
    def adapter(self, mock_task_manager):
        """Create an adapter instance."""
        return ClaudeCodeTaskAdapter(
            task_manager=mock_task_manager,
            session_id="test-session-123",
            project_id="test-project-456",
        )

    def test_enrich_task_data_no_id(self, adapter):
        """Test enrichment with no task ID."""
        data = {"subject": "Test"}
        result = adapter.enrich_task_data(data)
        assert "gobby" not in result

    def test_enrich_task_data_task_not_found(self, adapter, mock_task_manager):
        """Test enrichment when Gobby task not found."""
        mock_task_manager.list_tasks.return_value = []

        data = {"id": "cc-task-1", "subject": "Test"}
        result = adapter.enrich_task_data(data)
        assert "gobby" not in result
