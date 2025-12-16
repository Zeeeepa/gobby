import pytest
from unittest.mock import MagicMock, ANY

from gobby.mcp_proxy.tools.tasks import register_task_tools
from gobby.storage.tasks import LocalTaskManager
from gobby.sync.tasks import TaskSyncManager


class MockFastMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


@pytest.fixture
def mock_mcp():
    return MockFastMCP()


@pytest.fixture
def mock_task_manager():
    return MagicMock(spec=LocalTaskManager)


@pytest.fixture
def mock_sync_manager():
    return MagicMock(spec=TaskSyncManager)


def test_register_task_tools(mock_mcp, mock_task_manager, mock_sync_manager):
    # Setup mock attributes needed by register_task_tools helpers
    mock_task_manager.db = MagicMock()

    register_task_tools(mock_mcp, mock_task_manager, mock_sync_manager)

    expected_tools = [
        "create_task",
        "get_task",
        "update_task",
        "close_task",
        "delete_task",
        "list_tasks",
        "add_dependency",
        "remove_dependency",
        "get_dependency_tree",
        "check_dependency_cycles",
        "list_ready_tasks",
        "list_blocked_tasks",
        "link_task_to_session",
        "get_session_tasks",
        "get_task_sessions",
        "sync_tasks",
        "get_sync_status",
    ]

    for tool_name in expected_tools:
        assert tool_name in mock_mcp.tools


def test_create_task(mock_mcp, mock_task_manager, mock_sync_manager):
    mock_task_manager.db = MagicMock()
    register_task_tools(mock_mcp, mock_task_manager, mock_sync_manager)

    # Mock return value
    mock_task = MagicMock()
    mock_task.to_dict.return_value = {"id": "t1", "title": "Test Task"}
    mock_task_manager.create_task.return_value = mock_task

    result = mock_mcp.tools["create_task"](title="Test Task", priority=1)

    mock_task_manager.create_task.assert_called_with(
        title="Test Task",
        description=None,
        priority=1,
        task_type="task",
        parent_task_id=None,
        labels=None,
    )
    assert result == {"id": "t1", "title": "Test Task"}


def test_get_task_not_found(mock_mcp, mock_task_manager, mock_sync_manager):
    mock_task_manager.db = MagicMock()
    register_task_tools(mock_mcp, mock_task_manager, mock_sync_manager)

    mock_task_manager.get_task.return_value = None

    result = mock_mcp.tools["get_task"](task_id="nonexistent")

    assert "error" in result
    assert result["found"] is False


def test_list_ready_tasks(mock_mcp, mock_task_manager, mock_sync_manager):
    mock_task_manager.db = MagicMock()
    register_task_tools(mock_mcp, mock_task_manager, mock_sync_manager)

    mock_t1 = MagicMock()
    mock_t1.to_dict.return_value = {"id": "t1"}
    mock_task_manager.list_ready_tasks.return_value = [mock_t1]

    result = mock_mcp.tools["list_ready_tasks"](limit=5)

    mock_task_manager.list_ready_tasks.assert_called_with(
        priority=None, task_type=None, assignee=None, limit=5
    )
    assert result["count"] == 1
    assert result["tasks"][0]["id"] == "t1"


def test_sync_tasks(mock_mcp, mock_task_manager, mock_sync_manager):
    mock_task_manager.db = MagicMock()
    register_task_tools(mock_mcp, mock_task_manager, mock_sync_manager)

    result = mock_mcp.tools["sync_tasks"](direction="both")

    mock_sync_manager.import_from_jsonl.assert_called_once()
    mock_sync_manager.export_to_jsonl.assert_called_once()
    assert result["import"] == "completed"
    assert result["export"] == "completed"
