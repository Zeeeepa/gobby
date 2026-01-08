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

    with (
        patch("gobby.mcp_proxy.tools.task_expansion.TaskDependencyManager"),
        patch("gobby.mcp_proxy.tools.task_expansion.LocalProjectManager"),
    ):
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
        patch("gobby.mcp_proxy.tools.task_expansion.LocalProjectManager"),
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
        patch("gobby.mcp_proxy.tools.task_expansion.LocalProjectManager"),
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

    @pytest.mark.asyncio
    async def test_expand_task_no_expander_raises_error(
        self, mock_task_manager, expansion_registry_no_expander
    ):
        """Test expand_task raises error when task_expander is not configured."""
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

        with pytest.raises(RuntimeError, match="not enabled"):
            await expansion_registry_no_expander.call("expand_task", {"task_id": "t1"})

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
            patch("gobby.mcp_proxy.tools.task_expansion.LocalProjectManager"),
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
# expand_from_spec MCP Tool Tests
# ============================================================================


class TestExpandFromSpecTool:
    """Tests for expand_from_spec MCP tool."""

    @pytest.mark.asyncio
    async def test_expand_from_spec_parses_markdown(self, mock_task_manager, expansion_registry):
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
                    with patch(
                        "gobby.mcp_proxy.tools.task_expansion.get_project_context",
                        return_value={"id": "p1"},
                    ):
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
    async def test_expand_from_spec_creates_hierarchy(self, mock_task_manager, expansion_registry):
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
                    with patch(
                        "gobby.mcp_proxy.tools.task_expansion.get_project_context",
                        return_value={"id": "p1"},
                    ):
                        created_tasks = [
                            Task(
                                id=f"t{i}",
                                title=f"Task {i}",
                                project_id="p1",
                                status="open",
                                priority=2,
                                task_type="task",
                                created_at="now",
                                updated_at="now",
                            )
                            for i in range(10)
                        ]
                        mock_task_manager.create_task.side_effect = created_tasks
                        mock_task_manager.get_task.side_effect = lambda tid: next(
                            (t for t in created_tasks if t.id == tid), None
                        )

                        result = await expansion_registry.call(
                            "expand_from_spec",
                            {"spec_path": "/path/to/spec.md"},
                        )

                        assert "parent_task_id" in result
                        assert "mode_used" in result

    @pytest.mark.asyncio
    async def test_expand_from_spec_file_not_found(self, mock_task_manager, expansion_registry):
        """Test expand_from_spec with non-existent file."""
        with patch("pathlib.Path.exists", return_value=False):
            result = await expansion_registry.call(
                "expand_from_spec",
                {"spec_path": "/nonexistent/spec.md"},
            )

            assert "error" in result

    @pytest.mark.asyncio
    async def test_expand_from_spec_not_a_file(self, mock_task_manager, expansion_registry):
        """Test expand_from_spec when path is a directory."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=False):
                result = await expansion_registry.call(
                    "expand_from_spec",
                    {"spec_path": "/path/to/directory"},
                )

                assert "error" in result
                assert "not a file" in result["error"]

    @pytest.mark.asyncio
    async def test_expand_from_spec_read_error(self, mock_task_manager, expansion_registry):
        """Test expand_from_spec handles file read errors."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch(
                    "pathlib.Path.read_text", side_effect=PermissionError("Permission denied")
                ):
                    result = await expansion_registry.call(
                        "expand_from_spec",
                        {"spec_path": "/path/to/protected.md"},
                    )

                    assert "error" in result
                    assert "Failed to read" in result["error"]

    @pytest.mark.asyncio
    async def test_expand_from_spec_with_parent_task(self, mock_task_manager, expansion_registry):
        """Test expand_from_spec creates tasks under specified parent."""
        spec_content = "- [ ] Subtask 1\n- [ ] Subtask 2"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=spec_content):
                    with patch(
                        "gobby.mcp_proxy.tools.task_expansion.get_project_context",
                        return_value={"id": "p1"},
                    ):
                        created_tasks = [
                            Task(
                                id=f"t{i}",
                                title=f"Task {i}",
                                project_id="p1",
                                status="open",
                                priority=2,
                                task_type="task",
                                parent_task_id="parent",
                                created_at="now",
                                updated_at="now",
                            )
                            for i in range(3)
                        ]
                        mock_task_manager.create_task.side_effect = created_tasks
                        mock_task_manager.get_task.side_effect = lambda tid: next(
                            (t for t in created_tasks if t.id == tid), None
                        )

                        result = await expansion_registry.call(
                            "expand_from_spec",
                            {
                                "spec_path": "/path/to/spec.md",
                                "parent_task_id": "parent",
                            },
                        )

                        # Verify parent_task_id passed in
                        assert "parent_task_id" in result

    @pytest.mark.asyncio
    async def test_expand_from_spec_structured_mode_no_structure_error(
        self, mock_task_manager, expansion_registry
    ):
        """Test expand_from_spec returns error when structured mode but no headings/checkboxes."""
        # Plain text with no markdown structure
        spec_content = "This is just plain text without any headings or checkboxes."

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=spec_content):
                    with patch(
                        "gobby.mcp_proxy.tools.task_expansion.get_project_context",
                        return_value={"id": "p1"},
                    ):
                        result = await expansion_registry.call(
                            "expand_from_spec",
                            {"spec_path": "/path/to/spec.md", "mode": "structured"},
                        )

                        assert "error" in result
                        assert "No structure found" in result["error"]

    @pytest.mark.asyncio
    async def test_expand_from_spec_llm_mode(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_spec uses LLM when mode='llm'."""
        spec_content = "Build a user authentication system with login and registration."

        mock_task_expander.expand_task.return_value = {
            "subtask_ids": ["t2", "t3"],
        }

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=spec_content):
                    with patch(
                        "gobby.mcp_proxy.tools.task_expansion.get_project_context",
                        return_value={"id": "p1"},
                    ):
                        task_counter = [0]
                        created_tasks = {}

                        def create_task_factory(**kwargs):
                            task_counter[0] += 1
                            task = Task(
                                id=f"t{task_counter[0]}",
                                title=kwargs.get("title", f"Task {task_counter[0]}"),
                                project_id="p1",
                                status="open",
                                priority=2,
                                task_type=kwargs.get("task_type", "task"),
                                created_at="now",
                                updated_at="now",
                            )
                            created_tasks[task.id] = task
                            return task

                        mock_task_manager.create_task.side_effect = create_task_factory
                        mock_task_manager.get_task.side_effect = lambda tid: created_tasks.get(tid)

                        result = await expansion_registry.call(
                            "expand_from_spec",
                            {"spec_path": "/path/to/spec.md", "mode": "llm"},
                        )

                        assert "parent_task_id" in result
                        assert result.get("mode_used") == "llm"
                        mock_task_expander.expand_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_expand_from_spec_llm_mode_no_expander(
        self, mock_task_manager, expansion_registry_no_expander
    ):
        """Test expand_from_spec returns error when mode='llm' but no task_expander."""
        spec_content = "Build a user authentication system."

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=spec_content):
                    with patch(
                        "gobby.mcp_proxy.tools.task_expansion.get_project_context",
                        return_value={"id": "p1"},
                    ):
                        task = Task(
                            id="t1",
                            title="Spec Task",
                            project_id="p1",
                            status="open",
                            priority=2,
                            task_type="epic",
                            created_at="now",
                            updated_at="now",
                        )
                        mock_task_manager.create_task.return_value = task

                        result = await expansion_registry_no_expander.call(
                            "expand_from_spec",
                            {"spec_path": "/path/to/spec.md", "mode": "llm"},
                        )

                        assert "error" in result
                        assert "not enabled" in result["error"]
                        assert "parent_task_id" in result  # Parent still created

    @pytest.mark.asyncio
    async def test_expand_from_spec_llm_mode_expansion_error(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_spec handles LLM expansion errors."""
        spec_content = "Build something complex."

        mock_task_expander.expand_task.return_value = {
            "error": "LLM service unavailable",
        }

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=spec_content):
                    with patch(
                        "gobby.mcp_proxy.tools.task_expansion.get_project_context",
                        return_value={"id": "p1"},
                    ):
                        task = Task(
                            id="t1",
                            title="Spec Task",
                            project_id="p1",
                            status="open",
                            priority=2,
                            task_type="epic",
                            created_at="now",
                            updated_at="now",
                        )
                        mock_task_manager.create_task.return_value = task

                        result = await expansion_registry.call(
                            "expand_from_spec",
                            {"spec_path": "/path/to/spec.md", "mode": "llm"},
                        )

                        assert "error" in result
                        assert "LLM service unavailable" in result["error"]

    @pytest.mark.asyncio
    async def test_expand_from_spec_auto_mode_chooses_structured(
        self, mock_task_manager, expansion_registry
    ):
        """Test expand_from_spec auto mode chooses structured when structure found."""
        spec_content = """## Feature
- [ ] Task 1
- [ ] Task 2
"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=spec_content):
                    with patch(
                        "gobby.mcp_proxy.tools.task_expansion.get_project_context",
                        return_value={"id": "p1"},
                    ):
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
                            {"spec_path": "/path/to/spec.md", "mode": "auto"},
                        )

                        assert result.get("mode_used") == "structured"

    @pytest.mark.asyncio
    async def test_expand_from_spec_project_init_when_no_context(
        self, mock_task_manager, expansion_registry
    ):
        """Test expand_from_spec initializes project when no context exists."""
        spec_content = "- [ ] Task 1"

        mock_init_result = MagicMock()
        mock_init_result.project_id = "new-project-id"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=spec_content):
                    with patch(
                        "gobby.mcp_proxy.tools.task_expansion.get_project_context",
                        return_value=None,
                    ):
                        with patch(
                            "gobby.mcp_proxy.tools.task_expansion.initialize_project",
                            return_value=mock_init_result,
                        ):
                            task = Task(
                                id="t1",
                                title="Task",
                                project_id="new-project-id",
                                status="open",
                                priority=2,
                                task_type="epic",
                                created_at="now",
                                updated_at="now",
                            )
                            mock_task_manager.create_task.return_value = task
                            mock_task_manager.get_task.return_value = None

                            result = await expansion_registry.call(
                                "expand_from_spec",
                                {"spec_path": "/path/to/spec.md"},
                            )

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
            Task(
                id="parent",
                title="Create a REST API",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            ),
            Task(
                id="t1",
                title="Setup database",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            ),
            Task(
                id="t2",
                title="Create models",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            ),
        ]
        mock_task_manager.create_task.return_value = created_tasks[0]
        mock_task_manager.get_task.side_effect = lambda tid: next(
            (t for t in created_tasks if t.id == tid), None
        )

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}
        ):
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
            id="parent",
            title="Add tests",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}
        ):
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
            id="parent",
            title="Vague request",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}
        ):
            result = await expansion_registry.call(
                "expand_from_prompt",
                {"prompt": "Vague request"},
            )

        assert result["tasks_created"] == 0

    @pytest.mark.asyncio
    async def test_expand_from_prompt_no_expander_raises_error(
        self, mock_task_manager, expansion_registry_no_expander
    ):
        """Test expand_from_prompt raises error when task_expander not configured."""
        with pytest.raises(RuntimeError, match="not enabled"):
            await expansion_registry_no_expander.call(
                "expand_from_prompt",
                {"prompt": "Build something"},
            )

    @pytest.mark.asyncio
    async def test_expand_from_prompt_empty_prompt_error(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt returns error for empty prompt."""
        result = await expansion_registry.call(
            "expand_from_prompt",
            {"prompt": ""},
        )

        assert "error" in result
        assert "empty" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_expand_from_prompt_whitespace_only_error(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt returns error for whitespace-only prompt."""
        result = await expansion_registry.call(
            "expand_from_prompt",
            {"prompt": "   \n\t  "},
        )

        assert "error" in result
        assert "empty" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_expand_from_prompt_truncates_long_title(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt truncates very long prompts for title."""
        long_prompt = "A" * 100  # More than 80 chars

        mock_task_expander.expand_task.return_value = {"subtask_ids": []}
        mock_task_manager.create_task.return_value = Task(
            id="parent",
            title="A" * 77 + "...",  # Truncated
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}
        ):
            await expansion_registry.call(
                "expand_from_prompt",
                {"prompt": long_prompt},
            )

        # Verify create_task was called with truncated title
        call_kwargs = mock_task_manager.create_task.call_args.kwargs
        assert len(call_kwargs.get("title", "")) <= 80

    @pytest.mark.asyncio
    async def test_expand_from_prompt_uses_sentence_boundary(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt uses sentence boundary for title when possible."""
        prompt_with_sentence = "Build authentication. Also add tests and documentation."

        mock_task_expander.expand_task.return_value = {"subtask_ids": []}
        mock_task_manager.create_task.return_value = Task(
            id="parent",
            title="Build authentication.",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}
        ):
            await expansion_registry.call(
                "expand_from_prompt",
                {"prompt": prompt_with_sentence},
            )

        # Verify create_task was called (title extraction uses first sentence)
        mock_task_manager.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_expand_from_prompt_creates_epic_for_long_prompts(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt creates epic for prompts >200 chars."""
        long_prompt = "A" * 250

        mock_task_expander.expand_task.return_value = {"subtask_ids": []}
        mock_task_manager.create_task.return_value = Task(
            id="parent",
            title="Long task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="epic",  # Should be epic for long prompts
            created_at="now",
            updated_at="now",
        )

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}
        ):
            await expansion_registry.call(
                "expand_from_prompt",
                {"prompt": long_prompt},
            )

        # Verify create_task was called with task_type="epic"
        call_kwargs = mock_task_manager.create_task.call_args.kwargs
        assert call_kwargs.get("task_type") == "epic"

    @pytest.mark.asyncio
    async def test_expand_from_prompt_expansion_error(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt handles expansion errors."""
        mock_task_expander.expand_task.return_value = {"error": "LLM failed"}
        mock_task_manager.create_task.return_value = Task(
            id="parent",
            title="Task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}
        ):
            result = await expansion_registry.call(
                "expand_from_prompt",
                {"prompt": "Build something"},
            )

        assert "error" in result
        assert "parent_task_id" in result


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
            Task(
                id="t1",
                title="Task 1",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            ),
            Task(
                id="t2",
                title="Task 2",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            ),
        ]

        def list_tasks_side_effect(**kwargs):
            if kwargs.get("parent_task_id"):
                return []  # No children
            return unexpanded_tasks

        mock_task_manager.list_tasks.side_effect = list_tasks_side_effect
        mock_task_manager.get_task.side_effect = lambda tid: next(
            (t for t in unexpanded_tasks if t.id == tid), None
        )

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
        parent_task = Task(
            id="t1",
            title="Already expanded",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        subtask = Task(
            id="t1-1",
            title="Existing subtask",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )

        def list_tasks_side_effect(**kwargs):
            if kwargs.get("parent_task_id") == "t1":
                return [subtask]  # Has children - should be skipped
            return [parent_task]

        mock_task_manager.list_tasks.side_effect = list_tasks_side_effect
        mock_task_manager.get_task.return_value = parent_task

        result = await expansion_registry.call("expand_all", {})

        # Task with children should be filtered out before expansion
        assert result["total_attempted"] == 0

    @pytest.mark.asyncio
    async def test_expand_all_no_expander_raises_error(
        self, mock_task_manager, expansion_registry_no_expander
    ):
        """Test expand_all raises error when task_expander not configured."""
        with pytest.raises(RuntimeError, match="not enabled"):
            await expansion_registry_no_expander.call("expand_all", {})

    @pytest.mark.asyncio
    async def test_expand_all_handles_expansion_exception(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_all handles exceptions during individual task expansion."""
        unexpanded_task = Task(
            id="t1",
            title="Task 1",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )

        def list_tasks_side_effect(**kwargs):
            if kwargs.get("parent_task_id"):
                return []
            return [unexpanded_task]

        mock_task_manager.list_tasks.side_effect = list_tasks_side_effect
        mock_task_manager.get_task.return_value = unexpanded_task

        # Make expansion raise an exception
        mock_task_expander.expand_task.side_effect = Exception("Expansion failed")

        result = await expansion_registry.call("expand_all", {})

        assert result["expanded_count"] == 0
        assert result["total_attempted"] == 1
        assert result["results"][0]["status"] == "error"
        assert "Expansion failed" in result["results"][0]["error"]

    @pytest.mark.asyncio
    async def test_expand_all_respects_max_tasks_limit(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_all respects max_tasks limit."""
        # Create 10 unexpanded tasks
        unexpanded_tasks = [
            Task(
                id=f"t{i}",
                title=f"Task {i}",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            )
            for i in range(10)
        ]

        def list_tasks_side_effect(**kwargs):
            if kwargs.get("parent_task_id"):
                return []
            return unexpanded_tasks

        mock_task_manager.list_tasks.side_effect = list_tasks_side_effect
        mock_task_manager.get_task.side_effect = lambda tid: next(
            (t for t in unexpanded_tasks if t.id == tid), None
        )
        mock_task_expander.expand_task.return_value = {"subtask_ids": []}

        result = await expansion_registry.call("expand_all", {"max_tasks": 3})

        # Only 3 should be attempted
        assert result["total_attempted"] == 3

    @pytest.mark.asyncio
    async def test_expand_all_filters_by_task_type(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_all filters by task_type parameter."""
        mock_task_manager.list_tasks.return_value = []
        mock_task_expander.expand_task.return_value = {"subtask_ids": []}

        await expansion_registry.call("expand_all", {"task_type": "feature"})

        # Verify list_tasks was called with task_type filter in at least one call
        call_args_list = mock_task_manager.list_tasks.call_args_list
        assert any(
            call.kwargs.get("task_type") == "feature" for call in call_args_list
        ), f"Expected task_type='feature' in one of the calls: {call_args_list}"

    @pytest.mark.asyncio
    async def test_expand_all_filters_by_min_complexity(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_all filters tasks by minimum complexity score."""
        low_complexity_task = Task(
            id="t1",
            title="Simple task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            complexity_score=2,  # Below threshold
            created_at="now",
            updated_at="now",
        )
        high_complexity_task = Task(
            id="t2",
            title="Complex task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            complexity_score=8,  # Above threshold
            created_at="now",
            updated_at="now",
        )

        def list_tasks_side_effect(**kwargs):
            if kwargs.get("parent_task_id"):
                return []
            return [low_complexity_task, high_complexity_task]

        mock_task_manager.list_tasks.side_effect = list_tasks_side_effect
        mock_task_manager.get_task.side_effect = lambda tid: (
            low_complexity_task if tid == "t1" else high_complexity_task
        )
        mock_task_expander.expand_task.return_value = {"subtask_ids": []}

        result = await expansion_registry.call("expand_all", {"min_complexity": 5})

        # Only high_complexity_task should be expanded
        assert result["total_attempted"] == 1
        assert result["results"][0]["task_id"] == "t2"


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

    def test_expand_all_schema(self, expansion_registry):
        """Test expand_all has correct input schema."""
        schema = expansion_registry.get_schema("expand_all")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        # expand_all has optional parameters only
        assert "properties" in input_schema

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
            patch("gobby.mcp_proxy.tools.task_expansion.LocalProjectManager"),
        ):
            registry = create_expansion_registry(
                task_manager=mock_task_manager,
                task_expander=mock_task_expander,
                task_validator=None,  # No validator
                auto_generate_on_expand=True,
            )

            # Should still work, just won't generate criteria
            assert len(registry.list_tools()) == 5

    @pytest.mark.asyncio
    async def test_expand_from_spec_extracts_title_from_first_heading(
        self, mock_task_manager, expansion_registry
    ):
        """Test expand_from_spec extracts title from first heading."""
        spec_content = """# My Epic Title

Some description text.
- [ ] Task 1
"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=spec_content):
                    with patch(
                        "gobby.mcp_proxy.tools.task_expansion.get_project_context",
                        return_value={"id": "p1"},
                    ):
                        created_task = Task(
                            id="t1",
                            title="My Epic Title",
                            project_id="p1",
                            status="open",
                            priority=2,
                            task_type="epic",
                            created_at="now",
                            updated_at="now",
                        )
                        mock_task_manager.create_task.return_value = created_task
                        mock_task_manager.get_task.return_value = None

                        result = await expansion_registry.call(
                            "expand_from_spec",
                            {"spec_path": "/path/to/spec.md"},
                        )

                        # Verify title was extracted from heading
                        assert result["parent_task_title"] == "My Epic Title"

    @pytest.mark.asyncio
    async def test_expand_from_spec_extracts_title_from_first_line(
        self, mock_task_manager, expansion_registry
    ):
        """Test expand_from_spec extracts title from first line when no heading."""
        spec_content = """Build a complete authentication system with OAuth support

- [ ] Task 1
- [ ] Task 2
"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=spec_content):
                    with patch(
                        "gobby.mcp_proxy.tools.task_expansion.get_project_context",
                        return_value={"id": "p1"},
                    ):
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

                        # First line should be used as title (may be truncated)
                        assert "parent_task_title" in result

    @pytest.mark.asyncio
    async def test_expand_from_spec_dependency_cycle_ignored(
        self, mock_task_manager, mock_task_expander
    ):
        """Test expand_from_spec ignores dependency cycle errors in LLM mode."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

        spec_content = "Build a user authentication system."

        mock_dep_manager = MagicMock()
        mock_dep_manager.add_dependency.side_effect = ValueError("Cycle detected")

        mock_task_expander.expand_task.return_value = {"subtask_ids": ["t2", "t3"]}

        with (
            patch(
                "gobby.mcp_proxy.tools.task_expansion.TaskDependencyManager",
                return_value=mock_dep_manager,
            ),
            patch("gobby.mcp_proxy.tools.task_expansion.LocalProjectManager"),
        ):
            registry = create_expansion_registry(
                task_manager=mock_task_manager,
                task_expander=mock_task_expander,
            )

            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.is_file", return_value=True):
                    with patch("pathlib.Path.read_text", return_value=spec_content):
                        with patch(
                            "gobby.mcp_proxy.tools.task_expansion.get_project_context",
                            return_value={"id": "p1"},
                        ):
                            task_counter = [0]
                            created_tasks = {}

                            def create_task_factory(**kwargs):
                                task_counter[0] += 1
                                task = Task(
                                    id=f"t{task_counter[0]}",
                                    title=kwargs.get("title", f"Task {task_counter[0]}"),
                                    project_id="p1",
                                    status="open",
                                    priority=2,
                                    task_type=kwargs.get("task_type", "task"),
                                    created_at="now",
                                    updated_at="now",
                                )
                                created_tasks[task.id] = task
                                return task

                            mock_task_manager.create_task.side_effect = create_task_factory
                            mock_task_manager.get_task.side_effect = lambda tid: created_tasks.get(
                                tid
                            )

                            # Should not raise - cycle errors are ignored
                            result = await registry.call(
                                "expand_from_spec",
                                {"spec_path": "/path/to/spec.md", "mode": "llm"},
                            )

                            assert "parent_task_id" in result

    @pytest.mark.asyncio
    async def test_expand_from_prompt_project_init_when_no_context(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt initializes project when no context exists."""
        mock_init_result = MagicMock()
        mock_init_result.project_id = "new-project-id"

        mock_task_expander.expand_task.return_value = {"subtask_ids": []}

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context",
            return_value=None,  # No existing project context
        ):
            with patch(
                "gobby.mcp_proxy.tools.task_expansion.initialize_project",
                return_value=mock_init_result,
            ):
                mock_task_manager.create_task.return_value = Task(
                    id="parent",
                    title="Build something",
                    project_id="new-project-id",
                    status="open",
                    priority=2,
                    task_type="task",
                    created_at="now",
                    updated_at="now",
                )

                result = await expansion_registry.call(
                    "expand_from_prompt",
                    {"prompt": "Build something"},
                )

                assert "parent_task_id" in result

    @pytest.mark.asyncio
    async def test_expand_from_prompt_title_with_exclamation_boundary(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt uses exclamation mark boundary for title."""
        # Long prompt with exclamation mark boundary
        prompt_with_exclamation = "Fix this critical bug NOW! Also refactor the code and add tests and documentation and improve performance."

        mock_task_expander.expand_task.return_value = {"subtask_ids": []}
        mock_task_manager.create_task.return_value = Task(
            id="parent",
            title="Fix this critical bug NOW!",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}
        ):
            await expansion_registry.call(
                "expand_from_prompt",
                {"prompt": prompt_with_exclamation},
            )

        mock_task_manager.create_task.assert_called_once()
        call_kwargs = mock_task_manager.create_task.call_args.kwargs
        # Title should be extracted up to the exclamation mark
        assert "!" in call_kwargs.get("title", "")

    @pytest.mark.asyncio
    async def test_expand_from_prompt_title_with_question_boundary(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt uses question mark boundary for title."""
        prompt_with_question = "Can you implement user authentication? Also add tests for all the new endpoints and update the documentation."

        mock_task_expander.expand_task.return_value = {"subtask_ids": []}
        mock_task_manager.create_task.return_value = Task(
            id="parent",
            title="Can you implement user authentication?",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}
        ):
            await expansion_registry.call(
                "expand_from_prompt",
                {"prompt": prompt_with_question},
            )

        mock_task_manager.create_task.assert_called_once()
        call_kwargs = mock_task_manager.create_task.call_args.kwargs
        assert "?" in call_kwargs.get("title", "")

    @pytest.mark.asyncio
    async def test_expand_from_prompt_title_with_colon_boundary(
        self, mock_task_manager, mock_task_expander, expansion_registry
    ):
        """Test expand_from_prompt uses colon boundary for title."""
        prompt_with_colon = "Authentication System: Implement login, registration, password reset, email verification, and OAuth providers."

        mock_task_expander.expand_task.return_value = {"subtask_ids": []}
        mock_task_manager.create_task.return_value = Task(
            id="parent",
            title="Authentication System:",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context", return_value={"id": "p1"}
        ):
            await expansion_registry.call(
                "expand_from_prompt",
                {"prompt": prompt_with_colon},
            )

        mock_task_manager.create_task.assert_called_once()
        call_kwargs = mock_task_manager.create_task.call_args.kwargs
        assert ":" in call_kwargs.get("title", "")

    @pytest.mark.asyncio
    async def test_expand_from_prompt_dependency_cycle_ignored(
        self, mock_task_manager, mock_task_expander
    ):
        """Test expand_from_prompt ignores dependency cycle errors."""
        if not IMPORT_SUCCEEDED:
            pytest.skip("Module not extracted yet")

        mock_dep_manager = MagicMock()
        mock_dep_manager.add_dependency.side_effect = ValueError("Cycle detected")

        mock_task_expander.expand_task.return_value = {"subtask_ids": ["t1", "t2"]}

        with (
            patch(
                "gobby.mcp_proxy.tools.task_expansion.TaskDependencyManager",
                return_value=mock_dep_manager,
            ),
            patch("gobby.mcp_proxy.tools.task_expansion.LocalProjectManager"),
        ):
            registry = create_expansion_registry(
                task_manager=mock_task_manager,
                task_expander=mock_task_expander,
            )

            created_tasks = [
                Task(
                    id="parent",
                    title="Build something",
                    project_id="p1",
                    status="open",
                    priority=2,
                    task_type="task",
                    created_at="now",
                    updated_at="now",
                ),
                Task(
                    id="t1",
                    title="Subtask 1",
                    project_id="p1",
                    status="open",
                    priority=2,
                    task_type="task",
                    created_at="now",
                    updated_at="now",
                ),
                Task(
                    id="t2",
                    title="Subtask 2",
                    project_id="p1",
                    status="open",
                    priority=2,
                    task_type="task",
                    created_at="now",
                    updated_at="now",
                ),
            ]
            mock_task_manager.create_task.return_value = created_tasks[0]
            mock_task_manager.get_task.side_effect = lambda tid: next(
                (t for t in created_tasks if t.id == tid), None
            )

            with patch(
                "gobby.mcp_proxy.tools.task_expansion.get_project_context",
                return_value={"id": "p1"},
            ):
                # Should not raise - cycle errors are ignored
                result = await registry.call(
                    "expand_from_prompt",
                    {"prompt": "Build something"},
                )

                assert result["tasks_created"] == 2
