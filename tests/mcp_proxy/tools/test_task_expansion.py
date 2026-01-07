"""Tests for task expansion MCP tools module.

TDD Green Phase: These tests verify the extracted task_expansion module works correctly.

Tools tested:
- expand_task: Expand task into subtasks via AI
- expand_all: Expand multiple unexpanded tasks
- expand_from_spec: Create tasks from spec file
- expand_from_prompt: Create tasks from user prompt
- analyze_complexity: Analyze task complexity

Task: gt-91bf1d -> gt-c372d8
Parent: gt-30cebd (Decompose tasks.py)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import from NEW module location
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
    # Mock config for expand_from_spec which accesses task_expander.config.pattern_criteria
    expander.config = MagicMock()
    expander.config.pattern_criteria = {}
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

        # Mock expander returns subtask_ids (agent creates tasks via MCP calls)
        mock_task_expander.expand_task.return_value = {
            "subtask_ids": ["t1-1", "t1-2", "t1-3"],
        }

        # Mock getting created subtasks
        created_tasks = [
            Task(id="t1-1", title="Create user model", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
            Task(id="t1-2", title="Add login endpoint", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
            Task(id="t1-3", title="Add registration endpoint", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
        ]

        def get_task_side_effect(tid):
            if tid == "t1":
                return parent_task
            for t in created_tasks:
                if t.id == tid:
                    return t
            return None

        mock_task_manager.get_task.side_effect = get_task_side_effect

        result = await expansion_registry.call("expand_task", {"task_id": "t1"})

        assert result["task_id"] == "t1"
        assert result["tasks_created"] == 3
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
        mock_task_expander.expand_task.return_value = {"subtask_ids": []}

        await expansion_registry.call(
            "expand_task",
            {"task_id": "t1", "context": "This is a Python project using FastAPI"},
        )

        # Verify context was passed to expander
        mock_task_expander.expand_task.assert_called_once()
        call_kwargs = mock_task_expander.expand_task.call_args.kwargs
        assert call_kwargs.get("context") == "This is a Python project using FastAPI"

    @pytest.mark.asyncio
    async def test_expand_task_handles_error(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_task handles expander errors gracefully."""
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
        mock_task_expander.expand_task.return_value = {"error": "Expansion failed"}

        result = await expansion_registry.call("expand_task", {"task_id": "t1"})

        assert "error" in result
        assert result["subtask_ids"] == []

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
        """Test expand_task creates dependencies to parent task."""
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

        # Expander returns subtask IDs
        mock_task_expander.expand_task.return_value = {
            "subtask_ids": ["t1-1", "t1-2"],
        }

        result = await expansion_registry.call("expand_task", {"task_id": "t1"})

        assert result["tasks_created"] == 2


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
        spec_content = """# Feature: User Authentication

## Tasks
- [ ] Create user model
- [ ] Add login endpoint
- [ ] Add registration endpoint
"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=spec_content):
                    with patch("gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}):
                        # Create enough tasks for the hierarchy (parent + heading + checkboxes)
                        task_counter = [0]

                        def create_task_factory(**kwargs):
                            task_counter[0] += 1
                            return Task(
                                id=f"t{task_counter[0]}",
                                title=kwargs.get("title", f"Task {task_counter[0]}"),
                                project_id="p1",
                                status="open",
                                priority=2,
                                task_type=kwargs.get("task_type", "task"),
                                created_at="now",
                                updated_at="now",
                            )

                        mock_task_manager.create_task.side_effect = create_task_factory
                        mock_task_manager.get_task.return_value = None

                        result = await expansion_registry.call(
                            "expand_from_spec",
                            {"spec_path": "/path/to/spec.md"},
                        )

                        assert result["tasks_created"] >= 0
                        assert "parent_task_id" in result

    @pytest.mark.asyncio
    async def test_expand_from_spec_creates_hierarchy(
        self, mock_task_manager, expansion_registry
    ):
        """Test expand_from_spec creates parent-child relationships."""
        spec_content = """# Epic: Authentication System

## Feature: Login
- [ ] Create login form
- [ ] Add validation

## Feature: Registration
- [ ] Create registration form
"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=spec_content):
                    with patch("gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}):
                        created_tasks = [
                            Task(id=f"t{i}", title=f"Task {i}", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now")
                            for i in range(10)
                        ]
                        mock_task_manager.create_task.side_effect = created_tasks
                        mock_task_manager.get_task.side_effect = lambda tid: next((t for t in created_tasks if t.id == tid), None)

                        result = await expansion_registry.call(
                            "expand_from_spec",
                            {"spec_path": "/path/to/spec.md"},
                        )

                        assert "parent_task_id" in result
                        assert "mode_used" in result

    @pytest.mark.asyncio
    async def test_expand_from_spec_file_not_found(
        self, mock_task_manager, expansion_registry
    ):
        """Test expand_from_spec with non-existent file."""
        with patch("pathlib.Path.exists", return_value=False):
            result = await expansion_registry.call(
                "expand_from_spec",
                {"spec_path": "/nonexistent/spec.md"},
            )

            assert "error" in result

    @pytest.mark.asyncio
    async def test_expand_from_spec_with_parent_task(
        self, mock_task_manager, expansion_registry
    ):
        """Test expand_from_spec creates tasks under specified parent."""
        spec_content = "- [ ] Subtask 1\n- [ ] Subtask 2"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=spec_content):
                    with patch("gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}):
                        created_tasks = [
                            Task(id=f"t{i}", title=f"Task {i}", project_id="p1", status="open", priority=2, task_type="task", parent_task_id="parent", created_at="now", updated_at="now")
                            for i in range(3)
                        ]
                        mock_task_manager.create_task.side_effect = created_tasks
                        mock_task_manager.get_task.side_effect = lambda tid: next((t for t in created_tasks if t.id == tid), None)

                        result = await expansion_registry.call(
                            "expand_from_spec",
                            {
                                "spec_path": "/path/to/spec.md",
                                "parent_task_id": "parent",
                            },
                        )

                        # Verify parent_task_id passed in
                        assert "parent_task_id" in result


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
        # Mock expander returns subtask_ids
        mock_task_expander.expand_task.return_value = {
            "subtask_ids": ["t1", "t2"],
        }

        created_tasks = [
            Task(id="parent", title="Create a REST API", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
            Task(id="t1", title="Setup database", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
            Task(id="t2", title="Create models", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"),
        ]
        mock_task_manager.create_task.return_value = created_tasks[0]
        mock_task_manager.get_task.side_effect = lambda tid: next((t for t in created_tasks if t.id == tid), None)

        with patch("gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}):
            result = await expansion_registry.call(
                "expand_from_prompt",
                {
                    "prompt": "Create a REST API with database integration",
                },
            )

        assert result["tasks_created"] == 2
        assert "parent_task_id" in result

    @pytest.mark.asyncio
    async def test_expand_from_prompt_with_context(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt uses code context."""
        mock_task_expander.expand_task.return_value = {"subtask_ids": []}
        mock_task_manager.create_task.return_value = Task(
            id="parent", title="Add tests", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"
        )

        with patch("gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}):
            await expansion_registry.call(
                "expand_from_prompt",
                {
                    "prompt": "Add tests",
                },
            )

        # Verify expander was called with enable_code_context
        mock_task_expander.expand_task.assert_called_once()
        call_kwargs = mock_task_expander.expand_task.call_args.kwargs
        assert call_kwargs.get("enable_code_context") is True

    @pytest.mark.asyncio
    async def test_expand_from_prompt_empty_result(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt handles empty expansion result."""
        mock_task_expander.expand_task.return_value = {"subtask_ids": []}
        mock_task_manager.create_task.return_value = Task(
            id="parent", title="Vague request", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now"
        )

        with patch("gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}):
            result = await expansion_registry.call(
                "expand_from_prompt",
                {"prompt": "Vague request"},
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

        def list_tasks_side_effect(**kwargs):
            if kwargs.get("parent_task_id"):
                return []  # No children
            return unexpanded_tasks

        mock_task_manager.list_tasks.side_effect = list_tasks_side_effect
        mock_task_manager.get_task.side_effect = lambda tid: next((t for t in unexpanded_tasks if t.id == tid), None)

        # Each task expands to 1 subtask
        mock_task_expander.expand_task.return_value = {
            "subtask_ids": ["sub1"],
        }

        result = await expansion_registry.call("expand_all", {})

        assert result["expanded_count"] >= 0
        assert "results" in result

    @pytest.mark.asyncio
    async def test_expand_all_skips_already_expanded(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_all skips tasks that already have subtasks."""
        # Task with existing subtasks
        parent_task = Task(id="t1", title="Already expanded", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now")
        subtask = Task(id="t1-1", title="Existing subtask", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now")

        def list_tasks_side_effect(**kwargs):
            if kwargs.get("parent_task_id") == "t1":
                return [subtask]  # Has children - should be skipped
            return [parent_task]

        mock_task_manager.list_tasks.side_effect = list_tasks_side_effect
        mock_task_manager.get_task.return_value = parent_task

        result = await expansion_registry.call("expand_all", {})

        # Task with children should be filtered out before expansion
        assert result["total_attempted"] == 0


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
            description="A multi-part feature with many requirements that spans multiple paragraphs and has detailed specifications for implementation.",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task
        mock_task_manager.list_tasks.return_value = []  # No existing subtasks

        result = await expansion_registry.call("analyze_complexity", {"task_id": "t1"})

        assert "complexity_score" in result
        assert "recommended_subtasks" in result
        assert "reasoning" in result

    @pytest.mark.asyncio
    async def test_analyze_complexity_not_found(
        self, mock_task_manager, expansion_registry
    ):
        """Test analyze_complexity with non-existent task."""
        mock_task_manager.get_task.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await expansion_registry.call("analyze_complexity", {"task_id": "nonexistent"})

    @pytest.mark.asyncio
    async def test_analyze_complexity_with_existing_subtasks(
        self, mock_task_manager, expansion_registry
    ):
        """Test analyze_complexity uses existing subtask count."""
        task = Task(
            id="t1",
            title="Task with subtasks",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task
        # 4 existing subtasks
        mock_task_manager.list_tasks.return_value = [
            Task(id=f"sub{i}", title=f"Subtask {i}", project_id="p1", status="open", priority=2, task_type="task", created_at="now", updated_at="now")
            for i in range(4)
        ]

        result = await expansion_registry.call("analyze_complexity", {"task_id": "t1"})

        assert result["existing_subtasks"] == 4


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

    def test_expand_from_prompt_schema(self, expansion_registry):
        """Test expand_from_prompt has correct input schema."""
        schema = expansion_registry.get_schema("expand_from_prompt")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        assert "prompt" in input_schema["properties"]
