from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.tasks import create_task_registry
from gobby.storage.tasks import LocalTaskManager
from gobby.sync.tasks import TaskSyncManager


@pytest.fixture
def mock_task_manager():
    manager = MagicMock(spec=LocalTaskManager)
    manager.db = MagicMock()
    return manager


@pytest.fixture
def mock_sync_manager():
    return MagicMock(spec=TaskSyncManager)


@pytest.fixture
def task_registry(mock_task_manager, mock_sync_manager):
    return create_task_registry(mock_task_manager, mock_sync_manager)


def test_create_task_registry_returns_registry(task_registry):
    """Test that create_task_registry returns an InternalToolRegistry."""
    assert isinstance(task_registry, InternalToolRegistry)
    assert task_registry.name == "gobby-tasks"


def test_create_task_registry_has_all_tools(task_registry):
    """Test that all expected tools are registered."""
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

    tools_list = task_registry.list_tools()
    tool_names = [t["name"] for t in tools_list]

    for tool_name in expected_tools:
        assert tool_name in tool_names, f"Missing tool: {tool_name}"


def test_task_registry_get_schema(task_registry):
    """Test that schemas can be retrieved from the registry."""
    schema = task_registry.get_schema("create_task")

    assert schema is not None
    assert schema["name"] == "create_task"
    assert "description" in schema
    assert "inputSchema" in schema
    assert schema["inputSchema"]["type"] == "object"
    assert "title" in schema["inputSchema"]["properties"]


@pytest.mark.asyncio
async def test_create_task(mock_task_manager, mock_sync_manager):
    """Test create_task tool execution."""
    registry = create_task_registry(mock_task_manager, mock_sync_manager)

    # Mock return value
    mock_task = MagicMock()
    mock_task.id = "t1"
    mock_task.to_dict.return_value = {"id": "t1", "title": "Test Task"}
    mock_task_manager.create_task.return_value = mock_task

    # Mock get_project_context
    with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
        mock_ctx.return_value = {"id": "test-project-id"}

        result = await registry.call("create_task", {"title": "Test Task", "priority": 1})

        mock_task_manager.create_task.assert_called_with(
            project_id="test-project-id",
            title="Test Task",
            description=None,
            priority=1,
            task_type="task",
            parent_task_id=None,
            labels=None,
            test_strategy=None,
            validation_criteria=None,
            created_in_session_id=None,
        )
    assert result == {"id": "t1"}


@pytest.mark.asyncio
async def test_create_task_with_session_id(mock_task_manager, mock_sync_manager):
    """Test create_task tool captures session_id as created_in_session_id."""
    registry = create_task_registry(mock_task_manager, mock_sync_manager)

    # Mock return value
    mock_task = MagicMock()
    mock_task.id = "t1"
    mock_task.to_dict.return_value = {"id": "t1", "title": "Test Task"}
    mock_task_manager.create_task.return_value = mock_task

    # Mock get_project_context
    with patch("gobby.mcp_proxy.tools.tasks.get_project_context") as mock_ctx:
        mock_ctx.return_value = {"id": "test-project-id"}

        result = await registry.call(
            "create_task",
            {"title": "Test Task", "session_id": "session-abc123"},
        )

        mock_task_manager.create_task.assert_called_with(
            project_id="test-project-id",
            title="Test Task",
            description=None,
            priority=2,
            task_type="task",
            parent_task_id=None,
            labels=None,
            test_strategy=None,
            validation_criteria=None,
            created_in_session_id="session-abc123",
        )
    assert result == {"id": "t1"}


@pytest.mark.asyncio
async def test_get_task_not_found(mock_task_manager, mock_sync_manager):
    """Test get_task returns error when task not found."""
    registry = create_task_registry(mock_task_manager, mock_sync_manager)

    mock_task_manager.get_task.return_value = None

    result = await registry.call("get_task", {"task_id": "nonexistent"})

    assert "error" in result
    assert result["found"] is False


@pytest.mark.asyncio
async def test_list_ready_tasks(mock_task_manager, mock_sync_manager):
    """Test list_ready_tasks tool execution."""
    registry = create_task_registry(mock_task_manager, mock_sync_manager)

    mock_t1 = MagicMock()
    mock_t1.to_dict.return_value = {"id": "t1"}
    mock_task_manager.list_ready_tasks.return_value = [mock_t1]

    result = await registry.call("list_ready_tasks", {"limit": 5})

    mock_task_manager.list_ready_tasks.assert_called_with(
        priority=None, task_type=None, assignee=None, parent_task_id=None, limit=5
    )
    assert result["count"] == 1
    assert result["tasks"][0]["id"] == "t1"


@pytest.mark.asyncio
async def test_sync_tasks(mock_task_manager, mock_sync_manager):
    """Test sync_tasks tool execution."""
    registry = create_task_registry(mock_task_manager, mock_sync_manager)

    result = await registry.call("sync_tasks", {"direction": "both"})

    mock_sync_manager.import_from_jsonl.assert_called_once()
    mock_sync_manager.export_to_jsonl.assert_called_once()
    assert result["import"] == "completed"
    assert result["export"] == "completed"


@pytest.mark.asyncio
async def test_expand_task_integration(mock_task_manager, mock_sync_manager):
    """Test expand_task tool execution with expander registered."""
    mock_expander = MagicMock()
    # Return new format with subtask_ids (created by agent via tool calls)
    mock_expander.expand_task = AsyncMock(
        return_value={
            "subtask_ids": ["sub1", "sub2"],
            "tool_calls": 2,
            "text": "Created 2 subtasks",
        }
    )

    # Mock dependency manager
    with patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager") as MockDepManager:
        mock_dep_instance = MockDepManager.return_value

        registry = create_task_registry(
            mock_task_manager, mock_sync_manager, task_expander=mock_expander
        )

        msg_task = MagicMock()
        msg_task.id = "t1"
        msg_task.project_id = "p1"
        mock_task_manager.get_task.return_value = msg_task

        # Mock fetching created subtasks
        sub1 = MagicMock()
        sub1.id = "sub1"
        sub1.title = "Subtask 1"
        sub1.status = "open"
        sub2 = MagicMock()
        sub2.id = "sub2"
        sub2.title = "Subtask 2"
        sub2.status = "open"
        mock_task_manager.get_task.side_effect = [msg_task, sub1, sub2]

        result = await registry.call("expand_task", {"task_id": "t1", "context": "extra info"})

        mock_expander.expand_task.assert_called_once()
        assert result["task_id"] == "t1"
        assert result["subtask_ids"] == ["sub1", "sub2"]
        assert result["tool_calls"] == 2
        assert len(result["subtasks"]) == 2

        # Verify parent -> subtask dependencies are wired
        mock_dep_instance.add_dependency.assert_any_call(
            task_id="t1", depends_on="sub1", dep_type="blocks"
        )
        mock_dep_instance.add_dependency.assert_any_call(
            task_id="t1", depends_on="sub2", dep_type="blocks"
        )


@pytest.mark.asyncio
async def test_expand_task_with_flags(mock_task_manager, mock_sync_manager):
    """Test expand_task tool passes feature flags to TaskExpander."""
    mock_expander = MagicMock()
    # Minimal response
    mock_expander.expand_task = AsyncMock(return_value={"complexity_analysis": {}, "phases": []})

    with patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager"):
        registry = create_task_registry(
            mock_task_manager, mock_sync_manager, task_expander=mock_expander
        )

        mock_task = MagicMock()
        mock_task.id = "t1"
        mock_task_manager.get_task.return_value = mock_task

        # Call with explicit flags
        await registry.call(
            "expand_task",
            {
                "task_id": "t1",
                "enable_web_research": True,
                "enable_code_context": False,
            },
        )

        mock_expander.expand_task.assert_called_with(
            task_id="t1",
            title=mock_task.title,
            description=mock_task.description,
            context=None,
            enable_web_research=True,
            enable_code_context=False,
        )


# =============================================================================
# Commit Linking MCP Tools Tests
# =============================================================================


def test_task_registry_has_commit_linking_tools(task_registry):
    """Test that commit linking tools are registered."""
    expected_tools = [
        "link_commit",
        "unlink_commit",
        "auto_link_commits",
        "get_task_diff",
    ]

    tools_list = task_registry.list_tools()
    tool_names = [t["name"] for t in tools_list]

    for tool_name in expected_tools:
        assert tool_name in tool_names, f"Missing commit linking tool: {tool_name}"


def test_link_commit_schema(task_registry):
    """Test link_commit tool schema."""
    schema = task_registry.get_schema("link_commit")

    assert schema is not None
    assert schema["name"] == "link_commit"
    assert "inputSchema" in schema

    properties = schema["inputSchema"]["properties"]
    assert "task_id" in properties
    assert "commit_sha" in properties


def test_unlink_commit_schema(task_registry):
    """Test unlink_commit tool schema."""
    schema = task_registry.get_schema("unlink_commit")

    assert schema is not None
    assert schema["name"] == "unlink_commit"
    assert "inputSchema" in schema

    properties = schema["inputSchema"]["properties"]
    assert "task_id" in properties
    assert "commit_sha" in properties


def test_auto_link_commits_schema(task_registry):
    """Test auto_link_commits tool schema."""
    schema = task_registry.get_schema("auto_link_commits")

    assert schema is not None
    assert schema["name"] == "auto_link_commits"
    assert "inputSchema" in schema

    properties = schema["inputSchema"]["properties"]
    # Optional parameters
    assert "task_id" in properties or "since" in properties


def test_get_task_diff_schema(task_registry):
    """Test get_task_diff tool schema."""
    schema = task_registry.get_schema("get_task_diff")

    assert schema is not None
    assert schema["name"] == "get_task_diff"
    assert "inputSchema" in schema

    properties = schema["inputSchema"]["properties"]
    assert "task_id" in properties


@pytest.mark.asyncio
async def test_link_commit_tool(mock_task_manager, mock_sync_manager):
    """Test link_commit tool execution."""
    registry = create_task_registry(mock_task_manager, mock_sync_manager)

    mock_task = MagicMock()
    mock_task.id = "t1"
    mock_task.commits = ["abc123"]
    mock_task.to_dict.return_value = {"id": "t1", "commits": ["abc123"]}
    mock_task_manager.link_commit.return_value = mock_task

    result = await registry.call(
        "link_commit",
        {"task_id": "t1", "commit_sha": "abc123"},
    )

    mock_task_manager.link_commit.assert_called_with("t1", "abc123")
    assert result["task_id"] == "t1"
    assert "abc123" in result["commits"]


@pytest.mark.asyncio
async def test_unlink_commit_tool(mock_task_manager, mock_sync_manager):
    """Test unlink_commit tool execution."""
    registry = create_task_registry(mock_task_manager, mock_sync_manager)

    mock_task = MagicMock()
    mock_task.id = "t1"
    mock_task.commits = []
    mock_task.to_dict.return_value = {"id": "t1", "commits": []}
    mock_task_manager.unlink_commit.return_value = mock_task

    result = await registry.call(
        "unlink_commit",
        {"task_id": "t1", "commit_sha": "abc123"},
    )

    mock_task_manager.unlink_commit.assert_called_with("t1", "abc123")
    assert result["task_id"] == "t1"


@pytest.mark.asyncio
async def test_get_task_diff_tool(mock_task_manager, mock_sync_manager):
    """Test get_task_diff tool execution."""
    registry = create_task_registry(mock_task_manager, mock_sync_manager)

    mock_task = MagicMock()
    mock_task.id = "t1"
    mock_task.commits = ["abc123"]
    mock_task_manager.get_task.return_value = mock_task

    with patch("gobby.mcp_proxy.tools.tasks.get_task_diff") as mock_diff:
        from gobby.tasks.commits import TaskDiffResult

        mock_diff.return_value = TaskDiffResult(
            diff="diff content",
            commits=["abc123"],
            has_uncommitted_changes=False,
            file_count=2,
        )

        result = await registry.call(
            "get_task_diff",
            {"task_id": "t1", "include_uncommitted": False},
        )

        assert result["diff"] == "diff content"
        assert result["commits"] == ["abc123"]
        assert result["file_count"] == 2


@pytest.mark.asyncio
async def test_auto_link_commits_tool(mock_task_manager, mock_sync_manager):
    """Test auto_link_commits tool execution."""
    registry = create_task_registry(mock_task_manager, mock_sync_manager)

    with patch("gobby.mcp_proxy.tools.tasks.auto_link_commits_fn") as mock_auto_link:
        from gobby.tasks.commits import AutoLinkResult

        mock_auto_link.return_value = AutoLinkResult(
            linked_tasks={"t1": ["abc123", "def456"]},
            total_linked=2,
            skipped=0,
        )

        result = await registry.call(
            "auto_link_commits",
            {"since": "1 week ago"},
        )

        assert result["total_linked"] == 2
        assert "t1" in result["linked_tasks"]


@pytest.mark.asyncio
async def test_link_commit_invalid_task(mock_task_manager, mock_sync_manager):
    """Test link_commit with non-existent task."""
    registry = create_task_registry(mock_task_manager, mock_sync_manager)

    mock_task_manager.link_commit.side_effect = ValueError("Task not found")

    result = await registry.call(
        "link_commit",
        {"task_id": "nonexistent", "commit_sha": "abc123"},
    )

    assert "error" in result


@pytest.mark.asyncio
async def test_get_task_diff_no_commits(mock_task_manager, mock_sync_manager):
    """Test get_task_diff when task has no commits."""
    registry = create_task_registry(mock_task_manager, mock_sync_manager)

    mock_task = MagicMock()
    mock_task.id = "t1"
    mock_task.commits = []
    mock_task_manager.get_task.return_value = mock_task

    with patch("gobby.mcp_proxy.tools.tasks.get_task_diff") as mock_diff:
        from gobby.tasks.commits import TaskDiffResult

        mock_diff.return_value = TaskDiffResult(
            diff="",
            commits=[],
            has_uncommitted_changes=False,
            file_count=0,
        )

        result = await registry.call(
            "get_task_diff",
            {"task_id": "t1"},
        )

        assert result["diff"] == ""
        assert result["commits"] == []
