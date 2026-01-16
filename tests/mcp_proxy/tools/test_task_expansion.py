"""Tests for task expansion MCP tools module.

TDD Green Phase: These tests verify the extracted task_expansion module works correctly.

Tools tested:
- expand_task: Expand task into subtasks via AI
- analyze_complexity: Analyze task complexity
- apply_tdd: Transform task into TDD triplets

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
    expander.config = MagicMock()
    expander.config.pattern_criteria = {}
    return expander


@pytest.fixture
def mock_task_validator():
    """Create a mock task validator."""
    validator = AsyncMock()
    validator.generate_criteria = AsyncMock(return_value="- [ ] Check A\n- [ ] Check B")
    return validator


@pytest.fixture
def expansion_registry(mock_task_manager, mock_task_expander):
    """Create an expansion tool registry with mocked dependencies."""
    if not IMPORT_SUCCEEDED:
        pytest.skip("Module not extracted yet")

    with patch("gobby.mcp_proxy.tools.task_expansion.TaskDependencyManager"):
        registry = create_expansion_registry(
            task_manager=mock_task_manager,
            task_expander=mock_task_expander,
        )
        yield registry


@pytest.fixture
def expansion_registry_no_expander(mock_task_manager):
    """Create an expansion registry without task_expander (disabled)."""
    if not IMPORT_SUCCEEDED:
        pytest.skip("Module not extracted yet")

    with (
        patch("gobby.mcp_proxy.tools.task_expansion.TaskDependencyManager"),
    ):
        registry = create_expansion_registry(
            task_manager=mock_task_manager,
            task_expander=None,  # Expansion disabled
        )
        yield registry


@pytest.fixture
def expansion_registry_with_validator(mock_task_manager, mock_task_expander, mock_task_validator):
    """Create an expansion registry with task_validator for auto-generation."""
    if not IMPORT_SUCCEEDED:
        pytest.skip("Module not extracted yet")

    with (
        patch("gobby.mcp_proxy.tools.task_expansion.TaskDependencyManager"),
    ):
        registry = create_expansion_registry(
            task_manager=mock_task_manager,
            task_expander=mock_task_expander,
            task_validator=mock_task_validator,
            auto_generate_on_expand=True,
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
            Task(
                id="t1-1",
                title="Create user model",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            ),
            Task(
                id="t1-2",
                title="Add login endpoint",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            ),
            Task(
                id="t1-3",
                title="Add registration endpoint",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            ),
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

        # Verify context was passed to expander (may be wrapped in structure)
        mock_task_expander.expand_task.assert_called_once()
        call_args = mock_task_expander.expand_task.call_args
        # Check both positional and keyword arguments for context
        context = None
        if call_args.kwargs and "context" in call_args.kwargs:
            context = call_args.kwargs["context"]
        elif call_args.args:
            # Check positional args (context might be passed positionally)
            for arg in call_args.args:
                if isinstance(arg, str) and "FastAPI" in arg:
                    context = arg
                    break
                elif isinstance(arg, dict) and "context" in arg:
                    context = arg.get("context")
                    break
        # Coerce context to string since it may be a dict/list
        context_str = str(context) if context and not isinstance(context, str) else (context or "")
        assert "This is a Python project using FastAPI" in context_str, (
            f"Expected context to contain 'This is a Python project using FastAPI', "
            f"got: {context_str!r}"
        )

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
        assert result.get("subtasks", []) == []  # No subtasks created on error

    @pytest.mark.asyncio
    async def test_expand_task_not_found(self, mock_task_manager, expansion_registry):
        """Test expand_task with non-existent task."""
        mock_task_manager.get_task.return_value = None

        result = await expansion_registry.call("expand_task", {"task_id": "nonexistent"})
        assert "error" in result
        assert "invalid" in result["error"].lower()

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

    @pytest.mark.asyncio
    async def test_expand_task_no_expander_returns_error(
        self, mock_task_manager, expansion_registry_no_expander
    ):
        """Test expand_task returns error dict when task_expander is not configured."""
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

        result = await expansion_registry_no_expander.call("expand_task", {"task_id": "t1"})
        assert "error" in result
        assert "not enabled" in result["error"]

    @pytest.mark.asyncio
    async def test_expand_task_handles_dependency_cycle_error(
        self, mock_task_manager, mock_task_expander
    ):
        """Test expand_task handles dependency cycle errors gracefully."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

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

        mock_dep_manager = MagicMock()
        mock_dep_manager.add_dependency.side_effect = ValueError("Cycle detected")

        with (
            patch(
                "gobby.mcp_proxy.tools.task_expansion.TaskDependencyManager",
                return_value=mock_dep_manager,
            ),
            ):
            registry = create_expansion_registry(
                task_manager=mock_task_manager,
                task_expander=mock_task_expander,
            )

            mock_task_manager.get_task.return_value = task
            mock_task_expander.expand_task.return_value = {"subtask_ids": ["t1-1"]}

            # Should not raise - cycles are ignored
            result = await registry.call("expand_task", {"task_id": "t1"})
            assert result["tasks_created"] == 1

    @pytest.mark.asyncio
    async def test_expand_task_with_validation_generation(
        self,
        mock_task_manager,
        mock_task_expander,
        mock_task_validator,
        expansion_registry_with_validator,
    ):
        """Test expand_task auto-generates validation criteria for subtasks."""
        parent_task = Task(
            id="t1",
            title="Parent task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )

        subtask = Task(
            id="t1-1",
            title="Subtask 1",
            description="Do something",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            validation_criteria=None,  # No criteria yet
            created_at="now",
            updated_at="now",
        )

        def get_task_effect(tid):
            if tid == "t1":
                return parent_task
            if tid == "t1-1":
                return subtask
            return None

        mock_task_manager.get_task.side_effect = get_task_effect
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["t1-1"]}

        result = await expansion_registry_with_validator.call(
            "expand_task", {"task_id": "t1", "generate_validation": True}
        )

        assert result["tasks_created"] == 1
        assert result.get("validation_criteria_generated") == 1
        mock_task_validator.generate_criteria.assert_called_once()

    @pytest.mark.asyncio
    async def test_expand_task_skips_epic_validation(
        self,
        mock_task_manager,
        mock_task_expander,
        mock_task_validator,
        expansion_registry_with_validator,
    ):
        """Test expand_task skips validation criteria generation for epics."""
        parent_task = Task(
            id="t1",
            title="Parent task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )

        epic_subtask = Task(
            id="t1-1",
            title="Epic subtask",
            project_id="p1",
            status="open",
            priority=2,
            task_type="epic",  # Epic - should be skipped
            validation_criteria=None,
            created_at="now",
            updated_at="now",
        )

        def get_task_effect(tid):
            if tid == "t1":
                return parent_task
            if tid == "t1-1":
                return epic_subtask
            return None

        mock_task_manager.get_task.side_effect = get_task_effect
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["t1-1"]}

        result = await expansion_registry_with_validator.call(
            "expand_task", {"task_id": "t1", "generate_validation": True}
        )

        # Epics should be skipped
        assert (
            "validation_criteria_generated" not in result
            or result.get("validation_criteria_generated", 0) == 0
        )
        mock_task_validator.generate_criteria.assert_not_called()

    @pytest.mark.asyncio
    async def test_expand_task_validation_without_validator(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_task logs warning when validation enabled but validator not configured."""
        task = Task(
            id="t1",
            title="Task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )

        subtask = Task(
            id="t1-1",
            title="Subtask 1",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )

        def get_task_effect(tid):
            if tid == "t1":
                return task
            if tid == "t1-1":
                return subtask
            return None

        mock_task_manager.get_task.side_effect = get_task_effect
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["t1-1"]}

        # Registry without validator
        result = await expansion_registry.call(
            "expand_task", {"task_id": "t1", "generate_validation": True}
        )

        assert result.get("validation_skipped_reason") == "task_validator not configured"

    @pytest.mark.asyncio
    async def test_expand_task_validation_generation_failure(
        self,
        mock_task_manager,
        mock_task_expander,
        mock_task_validator,
        expansion_registry_with_validator,
    ):
        """Test expand_task handles validation criteria generation failure gracefully."""
        parent_task = Task(
            id="t1",
            title="Parent task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )

        subtask = Task(
            id="t1-1",
            title="Subtask 1",
            description="Do something",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            validation_criteria=None,
            created_at="now",
            updated_at="now",
        )

        def get_task_effect(tid):
            if tid == "t1":
                return parent_task
            if tid == "t1-1":
                return subtask
            return None

        mock_task_manager.get_task.side_effect = get_task_effect
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["t1-1"]}

        # Make validator raise an error
        mock_task_validator.generate_criteria.side_effect = Exception("LLM error")

        # Should not raise - failures are logged but don't stop expansion
        result = await expansion_registry_with_validator.call(
            "expand_task", {"task_id": "t1", "generate_validation": True}
        )

        assert result["tasks_created"] == 1
        # No criteria generated due to error
        assert result.get("validation_criteria_generated", 0) == 0


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
    async def test_analyze_complexity_not_found(self, mock_task_manager, expansion_registry):
        """Test analyze_complexity with non-existent task."""
        mock_task_manager.get_task.return_value = None

        result = await expansion_registry.call("analyze_complexity", {"task_id": "nonexistent"})
        assert "error" in result
        assert "invalid" in result["error"].lower()

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
            Task(
                id=f"sub{i}",
                title=f"Subtask {i}",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            )
            for i in range(4)
        ]

        result = await expansion_registry.call("analyze_complexity", {"task_id": "t1"})

        assert result["existing_subtasks"] == 4

    @pytest.mark.asyncio
    async def test_analyze_complexity_short_description(
        self, mock_task_manager, expansion_registry
    ):
        """Test analyze_complexity with short description (simple task)."""
        task = Task(
            id="t1",
            title="Fix bug",
            description="Fix typo",  # Very short - < 100 chars
            project_id="p1",
            status="open",
            priority=2,
            task_type="bug",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task
        mock_task_manager.list_tasks.return_value = []  # No subtasks

        result = await expansion_registry.call("analyze_complexity", {"task_id": "t1"})

        assert result["complexity_score"] == 2
        assert "simple" in result["reasoning"].lower()

    @pytest.mark.asyncio
    async def test_analyze_complexity_medium_description(
        self, mock_task_manager, expansion_registry
    ):
        """Test analyze_complexity with medium description (moderate complexity)."""
        task = Task(
            id="t1",
            title="Add feature",
            description="A" * 200,  # 200 chars - between 100 and 500
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task
        mock_task_manager.list_tasks.return_value = []

        result = await expansion_registry.call("analyze_complexity", {"task_id": "t1"})

        assert result["complexity_score"] == 5
        assert "moderate" in result["reasoning"].lower()

    @pytest.mark.asyncio
    async def test_analyze_complexity_long_description(self, mock_task_manager, expansion_registry):
        """Test analyze_complexity with long description (complex task)."""
        task = Task(
            id="t1",
            title="Major refactoring",
            description="A" * 600,  # > 500 chars
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task
        mock_task_manager.list_tasks.return_value = []

        result = await expansion_registry.call("analyze_complexity", {"task_id": "t1"})

        assert result["complexity_score"] == 8
        assert "complex" in result["reasoning"].lower()

    @pytest.mark.asyncio
    async def test_analyze_complexity_no_description(self, mock_task_manager, expansion_registry):
        """Test analyze_complexity with no description (treated as short)."""
        task = Task(
            id="t1",
            title="Task without description",
            description=None,  # No description
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task
        mock_task_manager.list_tasks.return_value = []

        result = await expansion_registry.call("analyze_complexity", {"task_id": "t1"})

        # None description should be treated as empty (0 chars < 100)
        assert result["complexity_score"] == 2

    @pytest.mark.asyncio
    async def test_analyze_complexity_many_subtasks(self, mock_task_manager, expansion_registry):
        """Test analyze_complexity caps score at 10 for many subtasks."""
        task = Task(
            id="t1",
            title="Epic task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="epic",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task
        # 20 existing subtasks
        mock_task_manager.list_tasks.return_value = [
            Task(
                id=f"sub{i}",
                title=f"Subtask {i}",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            )
            for i in range(20)
        ]

        result = await expansion_registry.call("analyze_complexity", {"task_id": "t1"})

        # Score should be capped at 10
        assert result["complexity_score"] == 10
        assert result["existing_subtasks"] == 20

    @pytest.mark.asyncio
    async def test_analyze_complexity_updates_task(self, mock_task_manager, expansion_registry):
        """Test analyze_complexity updates task with complexity score."""
        task = Task(
            id="t1",
            title="Task",
            description="Medium length description that is somewhat detailed",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task
        mock_task_manager.list_tasks.return_value = []

        await expansion_registry.call("analyze_complexity", {"task_id": "t1"})

        # Verify update_task was called
        mock_task_manager.update_task.assert_called_once()
        call_args = mock_task_manager.update_task.call_args
        assert call_args[0][0] == "t1"
        assert "complexity_score" in call_args.kwargs
        assert "estimated_subtasks" in call_args.kwargs


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
        # task_id and task_ids are optional (one or the other required at runtime)
        assert "task_id" in input_schema["properties"]
        assert "task_ids" in input_schema["properties"]

    def test_analyze_complexity_schema(self, expansion_registry):
        """Test analyze_complexity has correct input schema."""
        schema = expansion_registry.get_schema("analyze_complexity")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        assert "task_id" in input_schema["properties"]
        assert "task_id" in input_schema.get("required", [])


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestExpansionEdgeCases:
    """Tests for edge cases in task expansion."""

    @pytest.mark.asyncio
    async def test_expand_task_with_web_research(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_task passes enable_web_research flag."""
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
        mock_task_expander.expand_task.return_value = {"subtask_ids": []}

        await expansion_registry.call(
            "expand_task",
            {"task_id": "t1", "enable_web_research": True},
        )

        call_kwargs = mock_task_expander.expand_task.call_args.kwargs
        assert call_kwargs.get("enable_web_research") is True

    @pytest.mark.asyncio
    async def test_expand_task_disables_code_context(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_task can disable code context."""
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
        mock_task_expander.expand_task.return_value = {"subtask_ids": []}

        await expansion_registry.call(
            "expand_task",
            {"task_id": "t1", "enable_code_context": False},
        )

        call_kwargs = mock_task_expander.expand_task.call_args.kwargs
        assert call_kwargs.get("enable_code_context") is False

    @pytest.mark.asyncio
    async def test_registry_creation_without_validator(self, mock_task_manager, mock_task_expander):
        """Test registry creation without task_validator."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

        with (
            patch("gobby.mcp_proxy.tools.task_expansion.TaskDependencyManager"),
            ):
            registry = create_expansion_registry(
                task_manager=mock_task_manager,
                task_expander=mock_task_expander,
                task_validator=None,  # No validator
                auto_generate_on_expand=True,
            )

            # Should still work, just won't generate criteria
            # Verify all expected tools are present (more robust than exact count)
            tools = registry.list_tools()
            # list_tools() returns dicts with "name" key, not objects
            tool_names = {t["name"] for t in tools}
            expected_tools = {
                "expand_task",
                "analyze_complexity",
                "apply_tdd",
            }
            assert expected_tools.issubset(tool_names), (
                f"Missing expected tools. Expected: {expected_tools}, Got: {tool_names}"
            )

# ============================================================================
# Single-Level Expansion Tests
# ============================================================================


class TestSingleLevelExpansion:
    """Tests verifying expand_task is single-level only (no recursive expansion).

    The MCP tool should only create direct children of the parent task.
    Recursive/cascade expansion is handled by the CLI, not the MCP layer.
    """

    @pytest.mark.asyncio
    async def test_expand_task_only_creates_direct_children(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that expand_task only creates one level of subtasks."""
        parent_task = Task(
            id="parent",
            title="Build authentication system",
            description="Complete auth with login, registration, password reset",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = parent_task
        mock_task_manager.list_tasks.return_value = []

        # Expander returns 3 subtask IDs (simulating direct children)
        mock_task_expander.expand_task.return_value = {
            "subtask_ids": ["sub1", "sub2", "sub3"],
        }

        # Mock created subtasks
        created_subtasks = [
            Task(
                id=f"sub{i}",
                title=f"Subtask {i}",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            )
            for i in range(1, 4)
        ]

        def get_task_side_effect(tid):
            if tid == "parent":
                return parent_task
            return next((t for t in created_subtasks if t.id == tid), None)

        mock_task_manager.get_task.side_effect = get_task_side_effect

        result = await expansion_registry.call("expand_task", {"task_id": "parent"})

        # Verify only one call to expand_task (no recursive calls)
        assert mock_task_expander.expand_task.call_count == 1
        assert result["tasks_created"] == 3

    @pytest.mark.asyncio
    async def test_expand_task_does_not_auto_expand_subtasks(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that expand_task does NOT automatically expand created subtasks."""
        parent_task = Task(
            id="parent",
            title="Complex feature",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )

        # First subtask is complex (could theoretically be expanded further)
        complex_subtask = Task(
            id="sub1",
            title="Complex subtask that could be expanded",
            description="This has multiple parts: A, B, C, D, E that could become sub-subtasks",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            complexity_score=8,  # High complexity
            created_at="now",
            updated_at="now",
        )

        def get_task_side_effect(tid):
            if tid == "parent":
                return parent_task
            if tid == "sub1":
                return complex_subtask
            return None

        mock_task_manager.get_task.side_effect = get_task_side_effect
        mock_task_manager.list_tasks.return_value = []
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["sub1"]}

        result = await expansion_registry.call("expand_task", {"task_id": "parent"})

        # Only ONE call - the parent expansion. Subtasks are NOT auto-expanded.
        assert mock_task_expander.expand_task.call_count == 1

        # The call should have been for the parent task, not sub1
        call_kwargs = mock_task_expander.expand_task.call_args.kwargs
        assert call_kwargs.get("task_id") == "parent"

    @pytest.mark.asyncio
    async def test_expand_task_returns_immediate_children_only(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_task response only contains immediate children, not grandchildren."""
        parent_task = Task(
            id="parent",
            title="Epic task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="epic",
            created_at="now",
            updated_at="now",
        )

        child_tasks = [
            Task(
                id=f"child{i}",
                title=f"Child {i}",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            )
            for i in range(1, 4)
        ]

        def get_task_side_effect(tid):
            if tid == "parent":
                return parent_task
            return next((t for t in child_tasks if t.id == tid), None)

        mock_task_manager.get_task.side_effect = get_task_side_effect
        mock_task_manager.list_tasks.return_value = []
        mock_task_expander.expand_task.return_value = {
            "subtask_ids": ["child1", "child2", "child3"],
        }

        result = await expansion_registry.call("expand_task", {"task_id": "parent"})

        # Response should only list the 3 immediate children
        assert result["tasks_created"] == 3
        assert len(result["subtasks"]) == 3
        child_ids = {s["id"] for s in result["subtasks"]}
        assert child_ids == {"child1", "child2", "child3"}

    @pytest.mark.asyncio
    async def test_expand_task_non_recursive_across_calls(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that calling expand_task multiple times does not create nested levels or recursive expansion."""
        parent_task = Task(
            id="parent",
            title="Parent task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )

        def get_task_side_effect(tid):
            if tid == "parent":
                return parent_task
            return None

        mock_task_manager.get_task.side_effect = get_task_side_effect
        mock_task_manager.list_tasks.return_value = []

        # First expansion creates subtasks
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["sub1", "sub2"]}

        result1 = await expansion_registry.call("expand_task", {"task_id": "parent"})
        assert result1["tasks_created"] == 2

        # Each call is independent - no accumulation of nested levels
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["sub3"]}
        result2 = await expansion_registry.call("expand_task", {"task_id": "parent"})
        assert result2["tasks_created"] == 1

        # Both calls were for the same parent - no recursive descent
        assert mock_task_expander.expand_task.call_count == 2
        for call in mock_task_expander.expand_task.call_args_list:
            assert call.kwargs.get("task_id") == "parent"

    @pytest.mark.asyncio
    async def test_expand_task_subtasks_have_correct_parent(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that subtasks are direct children of the expanded task."""
        parent_task = Task(
            id="parent",
            title="Parent task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )

        # Subtasks should be created as direct children
        subtask = Task(
            id="sub1",
            title="Subtask 1",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            parent_task_id="parent",  # Direct child of parent
            created_at="now",
            updated_at="now",
        )

        def get_task_side_effect(tid):
            if tid == "parent":
                return parent_task
            if tid == "sub1":
                return subtask
            return None

        mock_task_manager.get_task.side_effect = get_task_side_effect
        mock_task_manager.list_tasks.return_value = []
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["sub1"]}

        result = await expansion_registry.call("expand_task", {"task_id": "parent"})

        # Verify only immediate children returned
        assert result["tasks_created"] == 1
        assert result["subtasks"][0]["id"] == "sub1"


# ============================================================================
# Expansion Context Usage Tests
# ============================================================================


class TestExpansionContextUsage:
    """Tests for using stored expansion_context from prior operations.

    When a task has expansion_context populated,
    expand_task should read and use this data to inform expansion decisions.
    """

    @pytest.mark.asyncio
    async def test_expand_task_uses_stored_expansion_context(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that expand_task reads and uses stored expansion_context."""
        import json

        # Task that was previously enriched
        enrichment_data = {
            "task_id": "parent",
            "domain_category": "code",
            "complexity_level": 3,
            "research_findings": "Found relevant auth patterns in auth_service.py",
            "suggested_subtask_count": 5,
            "validation_criteria": "- [ ] Tests pass\n- [ ] Auth flow works end-to-end",
            "mcp_tools_used": ["context7"],
        }

        enriched_task = Task(
            id="parent",
            title="Implement authentication",
            description="Add user login functionality",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            expansion_context=json.dumps(enrichment_data),
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = enriched_task
        mock_task_manager.list_tasks.return_value = []
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["sub1"]}

        await expansion_registry.call("expand_task", {"task_id": "parent"})

        # Verify expand_task was called (enriched tasks should still expand)
        mock_task_expander.expand_task.assert_called_once()

        # Verify enrichment data was passed as context
        call_kwargs = mock_task_expander.expand_task.call_args.kwargs
        raw_context = call_kwargs.get("context")
        # Coerce to string to handle any type safely
        context = str(raw_context) if raw_context is not None else ""

        # Research findings should be included in context
        assert context, "Context should not be empty when task has enrichment data"
        assert "auth patterns" in context.lower() or "auth_service.py" in context

        # Validation criteria from enrichment should be included
        assert "Tests pass" in context or "Auth flow" in context

    @pytest.mark.asyncio
    async def test_expand_task_passes_enrichment_context_to_expander(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that enrichment research findings are passed as context."""
        import json

        enrichment_data = {
            "task_id": "parent",
            "domain_category": "code",
            "complexity_level": 2,
            "research_findings": "Auth module uses JWT tokens. Session handling in session.py.",
            "suggested_subtask_count": 3,
        }

        enriched_task = Task(
            id="parent",
            title="Fix auth bug",
            description="Fix login issues",
            project_id="p1",
            status="open",
            priority=2,
            task_type="bug",
            expansion_context=json.dumps(enrichment_data),
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = enriched_task
        mock_task_manager.list_tasks.return_value = []
        mock_task_expander.expand_task.return_value = {"subtask_ids": []}

        # Call with additional context
        await expansion_registry.call(
            "expand_task",
            {"task_id": "parent", "context": "Additional user context"},
        )

        # Verify context was passed to expander including enrichment research
        call_kwargs = mock_task_expander.expand_task.call_args.kwargs
        raw_context = call_kwargs.get("context")
        # Coerce to string to handle any type safely
        context = str(raw_context) if raw_context is not None else ""

        # User context should be included
        assert "Additional user context" in context

        # Enrichment research findings should ALSO be included in the context
        assert "Auth module uses JWT tokens" in context, (
            f"Expected enrichment research in context, got: {context}"
        )
        assert "Session handling in session.py" in context

    @pytest.mark.asyncio
    async def test_expand_task_works_without_expansion_context(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that expand_task works normally when task has no expansion_context."""
        # Task without enrichment
        unenriched_task = Task(
            id="parent",
            title="Simple task",
            description="Do something",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            expansion_context=None,
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = unenriched_task
        mock_task_manager.list_tasks.return_value = []
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["sub1"]}

        result = await expansion_registry.call("expand_task", {"task_id": "parent"})

        # Should work normally
        assert result["tasks_created"] == 1
        mock_task_expander.expand_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_expand_task_handles_invalid_expansion_context_json(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that expand_task handles malformed expansion_context gracefully."""
        # Task with invalid JSON in expansion_context
        task_with_bad_context = Task(
            id="parent",
            title="Task with bad context",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            expansion_context="not valid json {{{",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task_with_bad_context
        mock_task_manager.list_tasks.return_value = []
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["sub1"]}

        # Should not crash - fallback to normal expansion
        result = await expansion_registry.call("expand_task", {"task_id": "parent"})

        # Should still work
        assert result["tasks_created"] == 1

    @pytest.mark.asyncio
    async def test_expand_task_uses_complexity_from_enrichment(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that complexity_score from enrichment influences expansion."""
        import json

        # High complexity task
        enrichment_data = {
            "task_id": "parent",
            "complexity_score": 3,  # High complexity
            "suggested_subtask_count": 7,
        }

        complex_task = Task(
            id="parent",
            title="Complex refactoring",
            description="Major overhaul",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            complexity_score=3,  # Also stored on task
            expansion_context=json.dumps(enrichment_data),
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = complex_task
        mock_task_manager.list_tasks.return_value = []
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["s1", "s2", "s3"]}

        result = await expansion_registry.call("expand_task", {"task_id": "parent"})

        # Expansion should complete normally
        assert result["tasks_created"] == 3

        # Complexity info from enrichment should be passed as context
        call_kwargs = mock_task_expander.expand_task.call_args.kwargs
        context = call_kwargs.get("context") or ""
        # Coerce context to string since it may be a dict/list
        context_str = str(context) if context and not isinstance(context, str) else (context or "")

        # Enrichment complexity info should be in context
        assert context_str, "Context should contain enrichment data for complex tasks"
        assert "complexity" in context_str.lower() or "subtask" in context_str.lower(), (
            f"Expected complexity info in context, got: {context_str}"
        )

    @pytest.mark.asyncio
    async def test_expand_task_with_empty_expansion_context(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that expand_task handles empty expansion_context string."""
        task_with_empty_context = Task(
            id="parent",
            title="Task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            expansion_context="",  # Empty string
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task_with_empty_context
        mock_task_manager.list_tasks.return_value = []
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["sub1"]}

        # Should work normally
        result = await expansion_registry.call("expand_task", {"task_id": "parent"})
        assert result["tasks_created"] == 1


class TestBatchParallelExpansion:
    """Tests for batch parallel expansion via task_ids parameter."""

    @pytest.mark.asyncio
    async def test_expand_task_batch_multiple_tasks(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expanding multiple tasks in parallel with task_ids."""
        task1 = Task(
            id="t1",
            title="Task 1",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        task2 = Task(
            id="t2",
            title="Task 2",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )

        def get_task_fn(task_id):
            return {"t1": task1, "t2": task2}.get(task_id)

        mock_task_manager.get_task.side_effect = get_task_fn
        mock_task_manager.list_tasks.return_value = []
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["sub1"]}

        # Call with task_ids parameter for batch expansion
        result = await expansion_registry.call(
            "expand_task", {"task_ids": ["t1", "t2"]}
        )

        # Should return results for both tasks
        assert "results" in result, "Batch mode should return 'results' list"
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    async def test_expand_task_batch_mixed_results(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test batch expansion with some tasks failing."""
        task1 = Task(
            id="t1",
            title="Task 1",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        # t2 doesn't exist

        def get_task_fn(task_id):
            if task_id == "t1":
                return task1
            return None

        mock_task_manager.get_task.side_effect = get_task_fn
        mock_task_manager.list_tasks.return_value = []
        mock_task_expander.expand_task.return_value = {"subtask_ids": ["sub1"]}

        # Call with task_ids where one task doesn't exist
        result = await expansion_registry.call(
            "expand_task", {"task_ids": ["t1", "nonexistent"]}
        )

        # Should return results for both (one success, one error)
        assert "results" in result
        assert len(result["results"]) == 2
        # At least one should have error
        errors = [r for r in result["results"] if "error" in r]
        successes = [r for r in result["results"] if "tasks_created" in r]
        assert len(errors) == 1
        assert len(successes) == 1

    @pytest.mark.asyncio
    async def test_expand_task_batch_empty_list_error(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that empty task_ids list returns error."""
        result = await expansion_registry.call(
            "expand_task", {"task_ids": []}
        )

        # Empty list should return error
        assert "error" in result

    @pytest.mark.asyncio
    async def test_expand_task_single_and_batch_mutually_exclusive(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that task_id and task_ids are mutually exclusive."""
        mock_task_manager.get_task.return_value = None
        mock_task_manager.list_tasks.return_value = []

        # Call with both task_id and task_ids
        result = await expansion_registry.call(
            "expand_task", {"task_id": "t1", "task_ids": ["t2"]}
        )

        # Should return error about mutual exclusion
        assert "error" in result
        assert "mutually exclusive" in result["error"].lower() or "one of" in result["error"].lower()


# ============================================================================
# IsExpanded Flag Tests
# ============================================================================


class TestIsExpandedFlag:
    """Tests for is_expanded flag being set after task expansion."""

    @pytest.mark.asyncio
    async def test_expand_task_sets_is_expanded_true(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that expand_task sets is_expanded=True on parent task after expansion."""
        parent_task = Task(
            id="parent-1",
            title="Implement feature",
            description="A feature to implement",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
            is_expanded=False,
        )
        mock_task_manager.get_task.return_value = parent_task
        mock_task_manager.list_tasks.return_value = []

        # Mock expander returns subtask_ids
        mock_task_expander.expand_task.return_value = {
            "subtask_ids": ["sub-1", "sub-2"],
        }

        result = await expansion_registry.call(
            "expand_task", {"task_id": "parent-1"}
        )

        # Should succeed
        assert "error" not in result
        assert result["tasks_created"] == 2

        # Verify is_expanded=True was set via update_task
        update_calls = mock_task_manager.update_task.call_args_list
        is_expanded_set = any(
            call.kwargs.get("is_expanded") is True or
            (len(call.args) > 1 and call.args[1:] and any(a is True for a in call.args))
            for call in update_calls
        )
        assert is_expanded_set, "is_expanded=True should be set after expansion"

    @pytest.mark.asyncio
    async def test_expand_task_batch_sets_is_expanded_true_for_all(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that batch expand_task sets is_expanded=True on all parent tasks."""
        task1 = Task(
            id="t1",
            title="Feature A",
            description="First feature",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
            is_expanded=False,
        )
        task2 = Task(
            id="t2",
            title="Feature B",
            description="Second feature",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
            is_expanded=False,
        )

        def get_task_side_effect(tid):
            return {"t1": task1, "t2": task2}.get(tid)

        mock_task_manager.get_task.side_effect = get_task_side_effect
        mock_task_manager.list_tasks.return_value = []

        # Mock expander returns subtask_ids for each task
        mock_task_expander.expand_task.return_value = {
            "subtask_ids": ["sub-1"],
        }

        result = await expansion_registry.call(
            "expand_task", {"task_ids": ["t1", "t2"]}
        )

        # Should succeed for both
        assert "results" in result
        assert len(result["results"]) == 2

        # Verify is_expanded=True was set for both tasks
        update_calls = mock_task_manager.update_task.call_args_list
        tasks_with_is_expanded = set()
        for call in update_calls:
            task_id = call.args[0] if call.args else None
            if call.kwargs.get("is_expanded") is True:
                tasks_with_is_expanded.add(task_id)
        assert "t1" in tasks_with_is_expanded, "is_expanded should be set for t1"
        assert "t2" in tasks_with_is_expanded, "is_expanded should be set for t2"

    @pytest.mark.asyncio
    async def test_expand_task_returns_is_expanded_in_response(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that expand_task returns is_expanded=True in response."""
        parent_task = Task(
            id="parent-1",
            title="Implement feature",
            description="A feature to implement",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
            is_expanded=False,
        )
        mock_task_manager.get_task.return_value = parent_task
        mock_task_manager.list_tasks.return_value = []

        mock_task_expander.expand_task.return_value = {
            "subtask_ids": ["sub-1"],
        }

        result = await expansion_registry.call(
            "expand_task", {"task_id": "parent-1"}
        )

        # Response should include is_expanded=True
        assert "error" not in result
        assert result.get("is_expanded") is True, "Response should include is_expanded=True"


# ============================================================================
# Seq_num in Response Tests
# ============================================================================


class TestSeqNumsInResponse:
    """Tests for returning seq_nums in expand_task response."""

    @pytest.mark.asyncio
    async def test_expand_task_returns_seq_num_for_subtasks(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that expand_task returns seq_num for each created subtask."""
        parent_task = Task(
            id="parent-1",
            title="Implement feature",
            description="A feature to implement",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
            seq_num=100,
        )
        subtask1 = Task(
            id="sub-1",
            title="Subtask 1",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            seq_num=101,
        )
        subtask2 = Task(
            id="sub-2",
            title="Subtask 2",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            seq_num=102,
        )

        def get_task_side_effect(tid):
            return {"parent-1": parent_task, "sub-1": subtask1, "sub-2": subtask2}.get(tid)

        mock_task_manager.get_task.side_effect = get_task_side_effect
        mock_task_manager.list_tasks.return_value = []

        mock_task_expander.expand_task.return_value = {
            "subtask_ids": ["sub-1", "sub-2"],
        }

        result = await expansion_registry.call(
            "expand_task", {"task_id": "parent-1"}
        )

        # Should succeed
        assert "error" not in result
        assert result["tasks_created"] == 2

        # Each subtask should have seq_num
        for subtask in result["subtasks"]:
            assert "seq_num" in subtask, "Subtask should include seq_num"
            assert isinstance(subtask["seq_num"], int), "seq_num should be an integer"

        # Verify specific seq_nums
        seq_nums = [s["seq_num"] for s in result["subtasks"]]
        assert 101 in seq_nums
        assert 102 in seq_nums

    @pytest.mark.asyncio
    async def test_expand_task_returns_ref_for_subtasks(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that expand_task returns ref (#N format) for each subtask."""
        parent_task = Task(
            id="parent-1",
            title="Implement feature",
            description="A feature to implement",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
            seq_num=100,
        )
        subtask1 = Task(
            id="sub-1",
            title="Subtask 1",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            seq_num=101,
        )

        def get_task_side_effect(tid):
            return {"parent-1": parent_task, "sub-1": subtask1}.get(tid)

        mock_task_manager.get_task.side_effect = get_task_side_effect
        mock_task_manager.list_tasks.return_value = []

        mock_task_expander.expand_task.return_value = {
            "subtask_ids": ["sub-1"],
        }

        result = await expansion_registry.call(
            "expand_task", {"task_id": "parent-1"}
        )

        # Should succeed
        assert "error" not in result

        # Each subtask should have ref in #N format
        for subtask in result["subtasks"]:
            assert "ref" in subtask, "Subtask should include ref"
            assert subtask["ref"].startswith("#"), "ref should start with #"

        # Verify specific ref
        assert result["subtasks"][0]["ref"] == "#101"

    @pytest.mark.asyncio
    async def test_expand_task_returns_parent_seq_num(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that expand_task returns parent_seq_num in response."""
        parent_task = Task(
            id="parent-1",
            title="Implement feature",
            description="A feature to implement",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
            seq_num=100,
        )

        mock_task_manager.get_task.return_value = parent_task
        mock_task_manager.list_tasks.return_value = []

        mock_task_expander.expand_task.return_value = {
            "subtask_ids": ["sub-1"],
        }

        result = await expansion_registry.call(
            "expand_task", {"task_id": "parent-1"}
        )

        # Response should include parent_seq_num
        assert "error" not in result
        assert result.get("parent_seq_num") == 100, "Response should include parent_seq_num"
        assert result.get("parent_ref") == "#100", "Response should include parent_ref"


# ============================================================================
# apply_tdd Tool Tests
# ============================================================================


class TestApplyTddTool:
    """Tests for apply_tdd MCP tool that transforms tasks into TDD triplets."""

    @pytest.mark.asyncio
    async def test_apply_tdd_tool_exists(self, expansion_registry):
        """Test that apply_tdd tool is registered."""
        tools = expansion_registry.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "apply_tdd" in tool_names, "apply_tdd tool should be registered"

    @pytest.mark.asyncio
    async def test_apply_tdd_creates_triplet(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that apply_tdd creates test, implement, refactor triplet."""
        parent_task = Task(
            id="parent-1",
            title="Add user authentication",
            description="Implement login functionality",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            is_tdd_applied=False,
        )
        mock_task_manager.get_task.return_value = parent_task
        mock_task_manager.create_task.side_effect = [
            Task(id="test-1", title="Write tests for: Add user authentication",
                 project_id="p1", status="open", priority=2, task_type="task",
                 created_at="now", updated_at="now", seq_num=101),
            Task(id="impl-1", title="Implement: Add user authentication",
                 project_id="p1", status="open", priority=2, task_type="task",
                 created_at="now", updated_at="now", seq_num=102),
            Task(id="refactor-1", title="Refactor: Add user authentication",
                 project_id="p1", status="open", priority=2, task_type="task",
                 created_at="now", updated_at="now", seq_num=103),
        ]

        result = await expansion_registry.call(
            "apply_tdd", {"task_id": "parent-1"}
        )

        # Should create 3 subtasks
        assert "error" not in result
        assert result.get("tasks_created") == 3

        # Verify subtask titles follow TDD pattern
        subtask_titles = [s.get("title") for s in result.get("subtasks", [])]
        assert any("Write tests for:" in t for t in subtask_titles if t)
        assert any("Implement:" in t for t in subtask_titles if t)
        assert any("Refactor:" in t for t in subtask_titles if t)

    @pytest.mark.asyncio
    async def test_apply_tdd_skips_already_applied(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that apply_tdd skips tasks with is_tdd_applied=True."""
        parent_task = Task(
            id="parent-1",
            title="Add user authentication",
            description="Implement login functionality",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            is_tdd_applied=True,  # Already applied
        )
        mock_task_manager.get_task.return_value = parent_task

        result = await expansion_registry.call(
            "apply_tdd", {"task_id": "parent-1"}
        )

        # Should skip and return message
        assert result.get("skipped") is True or "already applied" in str(result).lower()

    @pytest.mark.asyncio
    async def test_apply_tdd_sets_is_tdd_applied(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that apply_tdd sets is_tdd_applied=True after transformation."""
        parent_task = Task(
            id="parent-1",
            title="Add user authentication",
            description="Implement login functionality",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            is_tdd_applied=False,
        )
        mock_task_manager.get_task.return_value = parent_task
        mock_task_manager.create_task.side_effect = [
            Task(id="test-1", title="Write tests for: Add user authentication",
                 project_id="p1", status="open", priority=2, task_type="task",
                 created_at="now", updated_at="now", seq_num=101),
            Task(id="impl-1", title="Implement: Add user authentication",
                 project_id="p1", status="open", priority=2, task_type="task",
                 created_at="now", updated_at="now", seq_num=102),
            Task(id="refactor-1", title="Refactor: Add user authentication",
                 project_id="p1", status="open", priority=2, task_type="task",
                 created_at="now", updated_at="now", seq_num=103),
        ]

        result = await expansion_registry.call(
            "apply_tdd", {"task_id": "parent-1"}
        )

        # Should succeed
        assert "error" not in result

        # Verify is_tdd_applied=True was set via update_task
        update_calls = mock_task_manager.update_task.call_args_list
        is_tdd_applied_set = any(
            call.kwargs.get("is_tdd_applied") is True
            for call in update_calls
        )
        assert is_tdd_applied_set, "is_tdd_applied=True should be set after transformation"

    @pytest.mark.asyncio
    async def test_apply_tdd_sets_validation_criteria(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test that apply_tdd sets validation_criteria on parent task."""
        parent_task = Task(
            id="parent-1",
            title="Add user authentication",
            description="Implement login functionality",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            is_tdd_applied=False,
        )
        mock_task_manager.get_task.return_value = parent_task
        mock_task_manager.create_task.side_effect = [
            Task(id="test-1", title="Write tests for: Add user authentication",
                 project_id="p1", status="open", priority=2, task_type="task",
                 created_at="now", updated_at="now", seq_num=101),
            Task(id="impl-1", title="Implement: Add user authentication",
                 project_id="p1", status="open", priority=2, task_type="task",
                 created_at="now", updated_at="now", seq_num=102),
            Task(id="refactor-1", title="Refactor: Add user authentication",
                 project_id="p1", status="open", priority=2, task_type="task",
                 created_at="now", updated_at="now", seq_num=103),
        ]

        result = await expansion_registry.call(
            "apply_tdd", {"task_id": "parent-1"}
        )

        # Should succeed
        assert "error" not in result

        # Verify validation_criteria was set via update_task
        update_calls = mock_task_manager.update_task.call_args_list
        validation_criteria_set = any(
            "child tasks" in str(call.kwargs.get("validation_criteria", "")).lower()
            for call in update_calls
        )
        assert validation_criteria_set, (
            "validation_criteria should be set to child completion message after transformation"
        )


# ============================================================================
# TDD Triplet Dependencies Tests
# ============================================================================


class TestTddTripletDependencies:
    """Tests for TDD triplet creation with proper dependencies."""

    @pytest.mark.asyncio
    async def test_apply_tdd_creates_dependencies_impl_blocked_by_test(
        self, mock_task_manager, mock_task_expander
    ):
        """Test that Implement task is blocked by Test task."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

        mock_dep_manager = MagicMock()

        with (
            patch("gobby.mcp_proxy.tools.task_expansion.TaskDependencyManager", return_value=mock_dep_manager),
            ):
            registry = create_expansion_registry(
                task_manager=mock_task_manager,
                task_expander=mock_task_expander,
            )

            parent_task = Task(
                id="parent-1",
                title="Add user authentication",
                description="Implement login functionality",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
                is_tdd_applied=False,
            )
            mock_task_manager.get_task.return_value = parent_task

            # Track created task IDs
            test_task = Task(id="test-1", title="Write tests for: Add user authentication",
                             project_id="p1", status="open", priority=2, task_type="task",
                             created_at="now", updated_at="now", seq_num=101)
            impl_task = Task(id="impl-1", title="Implement: Add user authentication",
                             project_id="p1", status="open", priority=2, task_type="task",
                             created_at="now", updated_at="now", seq_num=102)
            refactor_task = Task(id="refactor-1", title="Refactor: Add user authentication",
                                 project_id="p1", status="open", priority=2, task_type="task",
                                 created_at="now", updated_at="now", seq_num=103)

            mock_task_manager.create_task.side_effect = [test_task, impl_task, refactor_task]

            result = await registry.call("apply_tdd", {"task_id": "parent-1"})

            # Should succeed
            assert "error" not in result
            assert result["tasks_created"] == 3

            # Verify dependency was created: impl blocked by test
            add_dep_calls = mock_dep_manager.add_dependency.call_args_list

            # Should have 2 dependencies: impl->test, refactor->impl
            assert len(add_dep_calls) >= 2, f"Should create at least 2 dependencies, got {add_dep_calls}"

            # Check impl blocked by test (handle both positional and keyword args)
            def matches_dependency(call, from_id, to_id, relation):
                """Check if call matches expected dependency args (positional or keyword)."""
                if call.args == (from_id, to_id, relation):
                    return True
                kwargs = call.kwargs
                return (
                    kwargs.get("from_task_id") == from_id
                    and kwargs.get("to_task_id") == to_id
                    and kwargs.get("relation") == relation
                )

            impl_blocked_by_test = any(
                matches_dependency(call, "impl-1", "test-1", "blocks")
                for call in add_dep_calls
            )
            assert impl_blocked_by_test, f"Implement should be blocked by Test, got {add_dep_calls}"

    @pytest.mark.asyncio
    async def test_apply_tdd_creates_dependencies_refactor_blocked_by_impl(
        self, mock_task_manager, mock_task_expander
    ):
        """Test that Refactor task is blocked by Implement task."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

        mock_dep_manager = MagicMock()

        with (
            patch("gobby.mcp_proxy.tools.task_expansion.TaskDependencyManager", return_value=mock_dep_manager),
            ):
            registry = create_expansion_registry(
                task_manager=mock_task_manager,
                task_expander=mock_task_expander,
            )

            parent_task = Task(
                id="parent-1",
                title="Add user authentication",
                description="Implement login functionality",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
                is_tdd_applied=False,
            )
            mock_task_manager.get_task.return_value = parent_task

            test_task = Task(id="test-1", title="Write tests for: Add user authentication",
                             project_id="p1", status="open", priority=2, task_type="task",
                             created_at="now", updated_at="now", seq_num=101)
            impl_task = Task(id="impl-1", title="Implement: Add user authentication",
                             project_id="p1", status="open", priority=2, task_type="task",
                             created_at="now", updated_at="now", seq_num=102)
            refactor_task = Task(id="refactor-1", title="Refactor: Add user authentication",
                                 project_id="p1", status="open", priority=2, task_type="task",
                                 created_at="now", updated_at="now", seq_num=103)

            mock_task_manager.create_task.side_effect = [test_task, impl_task, refactor_task]

            result = await registry.call("apply_tdd", {"task_id": "parent-1"})

            # Should succeed
            assert "error" not in result

            # Verify dependency: refactor blocked by impl (handle both positional and keyword args)
            add_dep_calls = mock_dep_manager.add_dependency.call_args_list

            def matches_dependency(call, from_id, to_id, relation):
                """Check if call matches expected dependency args (positional or keyword)."""
                if call.args == (from_id, to_id, relation):
                    return True
                kwargs = call.kwargs
                return (
                    kwargs.get("from_task_id") == from_id
                    and kwargs.get("to_task_id") == to_id
                    and kwargs.get("relation") == relation
                )

            refactor_blocked_by_impl = any(
                matches_dependency(call, "refactor-1", "impl-1", "blocks")
                for call in add_dep_calls
            )
            assert refactor_blocked_by_impl, f"Refactor should be blocked by Implement, got {add_dep_calls}"


# ============================================================================
# should_skip_tdd() Function Tests
# ============================================================================


class TestShouldSkipTdd:
    """Tests for should_skip_tdd() function with TDD_SKIP_PATTERNS."""

    def test_should_skip_tdd_function_exists(self):
        """Test that should_skip_tdd function is importable."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

        try:
            from gobby.mcp_proxy.tools.task_expansion import should_skip_tdd
            assert callable(should_skip_tdd), "should_skip_tdd should be callable"
        except ImportError:
            pytest.fail("should_skip_tdd function not yet implemented")

    def test_should_skip_tdd_skips_tdd_prefix_write_tests(self):
        """Test that tasks with 'Write tests for:' prefix are skipped."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

        try:
            from gobby.mcp_proxy.tools.task_expansion import should_skip_tdd
        except ImportError:
            pytest.skip("should_skip_tdd not yet implemented")

        assert should_skip_tdd("Write tests for: User authentication") is True

    def test_should_skip_tdd_skips_tdd_prefix_implement(self):
        """Test that tasks with 'Implement:' prefix are skipped."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

        try:
            from gobby.mcp_proxy.tools.task_expansion import should_skip_tdd
        except ImportError:
            pytest.skip("should_skip_tdd not yet implemented")

        assert should_skip_tdd("Implement: User authentication") is True

    def test_should_skip_tdd_skips_tdd_prefix_refactor(self):
        """Test that tasks with 'Refactor:' prefix are skipped."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

        try:
            from gobby.mcp_proxy.tools.task_expansion import should_skip_tdd
        except ImportError:
            pytest.skip("should_skip_tdd not yet implemented")

        assert should_skip_tdd("Refactor: User authentication") is True

    def test_should_skip_tdd_skips_deletion_tasks(self):
        """Test that tasks with deletion verbs are skipped."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

        try:
            from gobby.mcp_proxy.tools.task_expansion import should_skip_tdd
        except ImportError:
            pytest.skip("should_skip_tdd not yet implemented")

        # Delete tasks
        assert should_skip_tdd("Delete old user data") is True
        assert should_skip_tdd("Remove deprecated API endpoint") is True

    def test_should_skip_tdd_skips_doc_updates(self):
        """Test that documentation update tasks are skipped."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

        try:
            from gobby.mcp_proxy.tools.task_expansion import should_skip_tdd
        except ImportError:
            pytest.skip("should_skip_tdd not yet implemented")

        # Doc updates
        assert should_skip_tdd("Update README with installation instructions") is True
        assert should_skip_tdd("Update API documentation") is True

    def test_should_skip_tdd_skips_config_updates(self):
        """Test that config file update tasks are skipped."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

        try:
            from gobby.mcp_proxy.tools.task_expansion import should_skip_tdd
        except ImportError:
            pytest.skip("should_skip_tdd not yet implemented")

        # Config updates
        assert should_skip_tdd("Update pyproject.toml dependencies") is True
        assert should_skip_tdd("Update .env configuration") is True

    def test_should_skip_tdd_does_not_skip_regular_tasks(self):
        """Test that regular feature/bug tasks are not skipped."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

        try:
            from gobby.mcp_proxy.tools.task_expansion import should_skip_tdd
        except ImportError:
            pytest.skip("should_skip_tdd not yet implemented")

        # Regular implementation tasks should NOT be skipped
        assert should_skip_tdd("Add user authentication") is False
        assert should_skip_tdd("Fix login bug") is False
        assert should_skip_tdd("Create new API endpoint") is False
        assert should_skip_tdd("Implement password reset") is False


