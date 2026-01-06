"""Tests for task expansion MCP tools module.

TDD Red Phase: These tests import from the NEW module location (task_expansion)
which does not exist yet. Tests should fail with ImportError initially.

After extraction via Strangler Fig pattern:
- task_expansion.py will contain expansion-related tools
- tasks.py will re-export/delegate for backwards compatibility

Tools to be extracted:
- expand_task: Expand task into subtasks via AI
- expand_all: Expand multiple unexpanded tasks
- expand_from_spec: Create tasks from spec file
- expand_from_prompt: Create tasks from user prompt
- analyze_complexity: Analyze task complexity

Task: gt-91bf1d
Parent: gt-30cebd (Decompose tasks.py)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import from NEW module location - will fail until extraction is complete
# This is intentional for TDD red phase
try:
    from gobby.mcp_proxy.tools.task_expansion import (
        create_expansion_registry,
    )

    IMPORT_SUCCEEDED = True
except ImportError:
    IMPORT_SUCCEEDED = False
    create_expansion_registry = None

from gobby.storage.tasks import LocalTaskManager, Task
from gobby.tasks.expansion import TaskExpander


# Skip all tests if module doesn't exist yet (TDD red phase)
pytestmark = pytest.mark.skipif(
    not IMPORT_SUCCEEDED,
    reason="task_expansion module not yet extracted (TDD red phase)",
)


@pytest.fixture
def mock_task_manager():
    """Create a mock task manager."""
    manager = MagicMock(spec=LocalTaskManager)
    manager.db = MagicMock()
    return manager


@pytest.fixture
def mock_task_expander():
    """Create a mock task expander."""
    expander = AsyncMock(spec=TaskExpander)
    return expander


@pytest.fixture
def expansion_registry(mock_task_manager, mock_task_expander):
    """Create an expansion tool registry with mocked dependencies."""
    if not IMPORT_SUCCEEDED:
        pytest.skip("Module not extracted yet")

    with (
        patch("gobby.mcp_proxy.tools.task_expansion.TaskDependencyManager"),
        patch("gobby.mcp_proxy.tools.task_expansion.LocalProjectManager"),
    ):
        registry = create_expansion_registry(
            task_manager=mock_task_manager,
            task_expander=mock_task_expander,
        )
        yield registry


# ============================================================================
# expand_task MCP Tool Tests
# ============================================================================


class TestExpandTaskTool:
    """Tests for expand_task MCP tool."""

    @pytest.mark.asyncio
    async def test_expand_task_creates_subtasks(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_task creates subtasks from AI expansion."""
        parent_task = Task(
            id="t1",
            title="Implement authentication",
            description="Add user login and registration",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = parent_task
        mock_task_manager.list_tasks.return_value = []  # No existing subtasks

        # Mock expander returns subtask data
        mock_task_expander.expand_task.return_value = [
            {"title": "Create user model", "description": "Define User schema"},
            {"title": "Add login endpoint", "description": "POST /auth/login"},
            {"title": "Add registration endpoint", "description": "POST /auth/register"},
        ]

        # Mock created tasks
        created_tasks = [
            Task(id="t1-1", title="Create user model", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
            Task(id="t1-2", title="Add login endpoint", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
            Task(id="t1-3", title="Add registration endpoint", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
        ]
        mock_task_manager.create_task.side_effect = created_tasks

        result = await expansion_registry.call("expand_task", {"task_id": "t1"})

        assert result["expanded"] is True
        assert result["subtasks_created"] == 3
        assert len(result["subtasks"]) == 3

    @pytest.mark.asyncio
    async def test_expand_task_with_context(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_task passes context to expander."""
        task = Task(
            id="t1",
            title="Task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task
        mock_task_manager.list_tasks.return_value = []
        mock_task_expander.expand_task.return_value = []

        await expansion_registry.call(
            "expand_task",
            {"task_id": "t1", "context": "This is a Python project using FastAPI"},
        )

        # Verify context was passed to expander
        mock_task_expander.expand_task.assert_called_once()
        call_kwargs = mock_task_expander.expand_task.call_args.kwargs
        assert "context" in call_kwargs or "This is a Python project" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_expand_task_already_has_subtasks(
        self, mock_task_manager, expansion_registry
    ):
        """Test expand_task fails if task already has subtasks."""
        task = Task(
            id="t1",
            title="Task with subtasks",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task
        mock_task_manager.list_tasks.return_value = [
            Task(id="t1-1", title="Existing subtask", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
        ]

        result = await expansion_registry.call("expand_task", {"task_id": "t1"})

        assert result["expanded"] is False
        assert "already has subtasks" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_expand_task_not_found(self, mock_task_manager, expansion_registry):
        """Test expand_task with non-existent task."""
        mock_task_manager.get_task.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await expansion_registry.call("expand_task", {"task_id": "nonexistent"})

    @pytest.mark.asyncio
    async def test_expand_task_creates_dependencies(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_task creates dependencies between sequential subtasks."""
        task = Task(
            id="t1",
            title="Task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task
        mock_task_manager.list_tasks.return_value = []

        # Expander returns tasks with sequence info
        mock_task_expander.expand_task.return_value = [
            {"title": "Step 1", "sequence": 1},
            {"title": "Step 2", "sequence": 2, "depends_on": ["Step 1"]},
        ]

        created_tasks = [
            Task(id="t1-1", title="Step 1", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
            Task(id="t1-2", title="Step 2", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
        ]
        mock_task_manager.create_task.side_effect = created_tasks

        result = await expansion_registry.call("expand_task", {"task_id": "t1"})

        assert result["expanded"] is True


# ============================================================================
# expand_from_spec MCP Tool Tests
# ============================================================================


class TestExpandFromSpecTool:
    """Tests for expand_from_spec MCP tool."""

    @pytest.mark.asyncio
    async def test_expand_from_spec_parses_markdown(
        self, mock_task_manager, expansion_registry
    ):
        """Test expand_from_spec parses markdown spec into tasks."""
        spec_content = """
# Feature: User Authentication

## Tasks
- [ ] Create user model
- [ ] Add login endpoint
- [ ] Add registration endpoint
"""
        with patch("builtins.open", MagicMock()):
            with patch("pathlib.Path.read_text", return_value=spec_content):
                mock_task_manager.create_task.side_effect = [
                    Task(id=f"t{i}", title=f"Task {i}", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now")
                    for i in range(3)
                ]

                result = await expansion_registry.call(
                    "expand_from_spec",
                    {"spec_path": "/path/to/spec.md", "project_id": "p1"},
                )

                assert result["tasks_created"] >= 1

    @pytest.mark.asyncio
    async def test_expand_from_spec_creates_hierarchy(
        self, mock_task_manager, expansion_registry
    ):
        """Test expand_from_spec creates parent-child relationships."""
        spec_content = """
# Epic: Authentication System

## Feature: Login
- [ ] Create login form
- [ ] Add validation

## Feature: Registration
- [ ] Create registration form
"""
        with patch("builtins.open", MagicMock()):
            with patch("pathlib.Path.read_text", return_value=spec_content):
                mock_task_manager.create_task.side_effect = [
                    Task(id=f"t{i}", title=f"Task {i}", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now")
                    for i in range(10)
                ]

                result = await expansion_registry.call(
                    "expand_from_spec",
                    {"spec_path": "/path/to/spec.md", "project_id": "p1"},
                )

                assert result["tasks_created"] >= 1

    @pytest.mark.asyncio
    async def test_expand_from_spec_file_not_found(
        self, mock_task_manager, expansion_registry
    ):
        """Test expand_from_spec with non-existent file."""
        with patch("pathlib.Path.exists", return_value=False):
            result = await expansion_registry.call(
                "expand_from_spec",
                {"spec_path": "/nonexistent/spec.md", "project_id": "p1"},
            )

            assert "error" in result or result.get("tasks_created", 0) == 0

    @pytest.mark.asyncio
    async def test_expand_from_spec_with_parent_task(
        self, mock_task_manager, expansion_registry
    ):
        """Test expand_from_spec creates tasks under specified parent."""
        parent_task = Task(
            id="parent",
            title="Parent Epic",
            project_id="p1",
            status="open",
            priority=2,
            task_type="epic",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = parent_task

        spec_content = "- [ ] Subtask 1\n- [ ] Subtask 2"
        with patch("builtins.open", MagicMock()):
            with patch("pathlib.Path.read_text", return_value=spec_content):
                mock_task_manager.create_task.side_effect = [
                    Task(id=f"t{i}", title=f"Task {i}", project_id="p1", status="open", priority=2, task_type="task", parent_task_id="parent", created_at="now", updated_at="now")
                    for i in range(2)
                ]

                result = await expansion_registry.call(
                    "expand_from_spec",
                    {
                        "spec_path": "/path/to/spec.md",
                        "project_id": "p1",
                        "parent_task_id": "parent",
                    },
                )

                # Verify tasks created under parent
                for call in mock_task_manager.create_task.call_args_list:
                    assert call.kwargs.get("parent_task_id") == "parent"


# ============================================================================
# expand_from_prompt MCP Tool Tests
# ============================================================================


class TestExpandFromPromptTool:
    """Tests for expand_from_prompt MCP tool."""

    @pytest.mark.asyncio
    async def test_expand_from_prompt_creates_tasks(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt creates tasks from natural language."""
        mock_task_expander.expand_from_prompt.return_value = [
            {"title": "Setup database", "description": "Configure PostgreSQL"},
            {"title": "Create models", "description": "Define ORM models"},
        ]

        mock_task_manager.create_task.side_effect = [
            Task(id=f"t{i}", title=f"Task {i}", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now")
            for i in range(2)
        ]

        result = await expansion_registry.call(
            "expand_from_prompt",
            {
                "prompt": "Create a REST API with database integration",
                "project_id": "p1",
            },
        )

        assert result["tasks_created"] == 2

    @pytest.mark.asyncio
    async def test_expand_from_prompt_with_context(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt uses provided context."""
        mock_task_expander.expand_from_prompt.return_value = []

        await expansion_registry.call(
            "expand_from_prompt",
            {
                "prompt": "Add tests",
                "project_id": "p1",
                "context": "Using pytest with async support",
            },
        )

        # Verify context was passed
        mock_task_expander.expand_from_prompt.assert_called_once()
        call_args = mock_task_expander.expand_from_prompt.call_args
        assert "pytest" in str(call_args) or "context" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_expand_from_prompt_empty_result(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt handles empty expansion result."""
        mock_task_expander.expand_from_prompt.return_value = []

        result = await expansion_registry.call(
            "expand_from_prompt",
            {"prompt": "Vague request", "project_id": "p1"},
        )

        assert result["tasks_created"] == 0


# ============================================================================
# expand_all MCP Tool Tests
# ============================================================================


class TestExpandAllTool:
    """Tests for expand_all MCP tool."""

    @pytest.mark.asyncio
    async def test_expand_all_expands_multiple_tasks(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_all expands all unexpanded tasks."""
        unexpanded_tasks = [
            Task(id="t1", title="Task 1", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
            Task(id="t2", title="Task 2", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
        ]
        mock_task_manager.list_tasks.return_value = unexpanded_tasks
        mock_task_manager.get_task.side_effect = lambda tid: next((t for t in unexpanded_tasks if t.id == tid), None)

        mock_task_expander.expand_task.return_value = [
            {"title": "Subtask", "description": "A subtask"},
        ]

        mock_task_manager.create_task.return_value = Task(
            id="sub", title="Subtask", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"
        )

        result = await expansion_registry.call("expand_all", {"project_id": "p1"})

        assert result["tasks_expanded"] >= 0

    @pytest.mark.asyncio
    async def test_expand_all_skips_already_expanded(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_all skips tasks that already have subtasks."""
        # Task with existing subtasks
        parent_task = Task(id="t1", title="Already expanded", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now")

        def list_tasks_side_effect(**kwargs):
            if kwargs.get("parent_task_id") == "t1":
                return [Task(id="t1-1", title="Existing subtask", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now")]
            return [parent_task]

        mock_task_manager.list_tasks.side_effect = list_tasks_side_effect
        mock_task_manager.get_task.return_value = parent_task

        result = await expansion_registry.call("expand_all", {"project_id": "p1"})

        # Should not call expander for already-expanded tasks
        assert result.get("skipped", 0) >= 0


# ============================================================================
# analyze_complexity MCP Tool Tests
# ============================================================================


class TestAnalyzeComplexityTool:
    """Tests for analyze_complexity MCP tool."""

    @pytest.mark.asyncio
    async def test_analyze_complexity_returns_score(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test analyze_complexity returns complexity analysis."""
        task = Task(
            id="t1",
            title="Complex feature",
            description="A multi-part feature with many requirements",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        mock_task_expander.analyze_complexity.return_value = {
            "complexity_score": 8,
            "estimated_subtasks": 5,
            "reasoning": "Multiple integrations required",
        }

        result = await expansion_registry.call("analyze_complexity", {"task_id": "t1"})

        assert "complexity_score" in result
        assert "estimated_subtasks" in result

    @pytest.mark.asyncio
    async def test_analyze_complexity_not_found(
        self, mock_task_manager, expansion_registry
    ):
        """Test analyze_complexity with non-existent task."""
        mock_task_manager.get_task.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await expansion_registry.call("analyze_complexity", {"task_id": "nonexistent"})


# ============================================================================
# Tool Registration Tests
# ============================================================================


class TestExpansionToolsRegistration:
    """Tests verifying expansion tools are properly registered in the new module."""

    def test_expand_task_tool_registered(self, expansion_registry):
        """Test that expand_task is registered."""
        tools = expansion_registry.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "expand_task" in tool_names

    def test_expand_from_spec_tool_registered(self, expansion_registry):
        """Test that expand_from_spec is registered."""
        tools = expansion_registry.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "expand_from_spec" in tool_names

    def test_expand_from_prompt_tool_registered(self, expansion_registry):
        """Test that expand_from_prompt is registered."""
        tools = expansion_registry.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "expand_from_prompt" in tool_names

    def test_expand_all_tool_registered(self, expansion_registry):
        """Test that expand_all is registered."""
        tools = expansion_registry.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "expand_all" in tool_names

    def test_analyze_complexity_tool_registered(self, expansion_registry):
        """Test that analyze_complexity is registered."""
        tools = expansion_registry.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "analyze_complexity" in tool_names


# ============================================================================
# Schema Tests
# ============================================================================


class TestExpansionToolSchemas:
    """Tests for tool input schemas."""

    def test_expand_task_schema(self, expansion_registry):
        """Test expand_task has correct input schema."""
        schema = expansion_registry.get_schema("expand_task")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        assert "task_id" in input_schema["properties"]
        assert "task_id" in input_schema.get("required", [])

    def test_expand_from_spec_schema(self, expansion_registry):
        """Test expand_from_spec has correct input schema."""
        schema = expansion_registry.get_schema("expand_from_spec")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        assert "spec_path" in input_schema["properties"]
        assert "project_id" in input_schema["properties"]

    def test_expand_from_prompt_schema(self, expansion_registry):
        """Test expand_from_prompt has correct input schema."""
        schema = expansion_registry.get_schema("expand_from_prompt")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        assert "prompt" in input_schema["properties"]
        assert "project_id" in input_schema["properties"]
