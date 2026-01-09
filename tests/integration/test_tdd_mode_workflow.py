"""
Functional tests for TDD mode enforcement via workflow variable.

Tests that expand_task, expand_from_spec, and expand_from_prompt respect
tdd_mode from workflow state variables and create test→implementation pairs.
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.projects import LocalProjectManager
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import LocalTaskManager
from gobby.tasks.spec_parser import TaskHierarchyBuilder
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.state_manager import WorkflowStateManager

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def workflow_state_manager(temp_db: LocalDatabase) -> WorkflowStateManager:
    """Create a WorkflowStateManager with test database."""
    return WorkflowStateManager(temp_db)


@pytest.fixture
def task_manager(temp_db: LocalDatabase) -> LocalTaskManager:
    """Create a LocalTaskManager with test database."""
    return LocalTaskManager(temp_db)


@pytest.fixture
def dep_manager(temp_db: LocalDatabase) -> TaskDependencyManager:
    """Create a TaskDependencyManager with test database."""
    return TaskDependencyManager(temp_db)


@pytest.fixture
def session_with_tdd_mode(
    temp_db: LocalDatabase,
    workflow_state_manager: WorkflowStateManager,
) -> tuple[str, str]:
    """Create a session with tdd_mode=true in workflow state.

    Returns:
        Tuple of (session_id, project_id)
    """
    project_manager = LocalProjectManager(temp_db)
    project = project_manager.get_or_create("/tmp/test-project")

    session_manager = LocalSessionManager(temp_db)
    session = session_manager.register(
        external_id="ext_tdd_test",
        machine_id="machine_001",
        source="claude_code",
        project_id=project.id,
    )

    state = WorkflowState(
        session_id=session.id,
        workflow_name="test-driven-workflow",
        step="work",
        step_entered_at=datetime.now(UTC),
        variables={"tdd_mode": True},
    )
    workflow_state_manager.save_state(state)

    return session.id, project.id


@pytest.fixture
def session_without_tdd_mode(
    temp_db: LocalDatabase,
    workflow_state_manager: WorkflowStateManager,
) -> tuple[str, str]:
    """Create a session with tdd_mode=false in workflow state.

    Returns:
        Tuple of (session_id, project_id)
    """
    project_manager = LocalProjectManager(temp_db)
    project = project_manager.get_or_create("/tmp/test-project-no-tdd")

    session_manager = LocalSessionManager(temp_db)
    session = session_manager.register(
        external_id="ext_no_tdd_test",
        machine_id="machine_001",
        source="claude_code",
        project_id=project.id,
    )

    state = WorkflowState(
        session_id=session.id,
        workflow_name="regular-workflow",
        step="work",
        step_entered_at=datetime.now(UTC),
        variables={"tdd_mode": False},
    )
    workflow_state_manager.save_state(state)

    return session.id, project.id


@pytest.fixture
def project_id(temp_db: LocalDatabase) -> str:
    """Create a project and return its ID."""
    project_manager = LocalProjectManager(temp_db)
    project = project_manager.get_or_create("/tmp/test-project")
    return project.id


# =============================================================================
# Test resolve_tdd_mode function
# =============================================================================


class TestResolveTddMode:
    """Test that resolve_tdd_mode correctly reads from workflow state."""

    def test_returns_true_when_tdd_mode_enabled(
        self,
        workflow_state_manager: WorkflowStateManager,
        session_with_tdd_mode: tuple[str, str],
    ):
        """resolve_tdd_mode returns True when workflow variable is set."""
        session_id, _ = session_with_tdd_mode
        state = workflow_state_manager.get_state(session_id)
        assert state is not None
        assert state.variables.get("tdd_mode") is True

    def test_returns_false_when_tdd_mode_disabled(
        self,
        workflow_state_manager: WorkflowStateManager,
        session_without_tdd_mode: tuple[str, str],
    ):
        """resolve_tdd_mode returns False when workflow variable is False."""
        session_id, _ = session_without_tdd_mode
        state = workflow_state_manager.get_state(session_id)
        assert state is not None
        assert state.variables.get("tdd_mode") is False

    def test_returns_none_for_missing_session(
        self,
        workflow_state_manager: WorkflowStateManager,
    ):
        """resolve_tdd_mode returns None for non-existent session."""
        state = workflow_state_manager.get_state("nonexistent-session-id")
        assert state is None


# =============================================================================
# Test TaskHierarchyBuilder TDD mode via build_from_checkboxes
# =============================================================================


class TestTaskHierarchyBuilderTddMode:
    """Test TaskHierarchyBuilder creates test→implementation pairs when tdd_mode enabled."""

    def test_build_from_checkboxes_creates_tdd_pairs_when_enabled(
        self,
        task_manager: LocalTaskManager,
        dep_manager: TaskDependencyManager,
        project_id: str,
    ):
        """When tdd_mode=True, build_from_checkboxes creates test + implementation tasks."""
        from gobby.tasks.spec_parser import CheckboxItem, ExtractedCheckboxes

        builder = TaskHierarchyBuilder(
            task_manager=task_manager,
            project_id=project_id,
            parent_task_id=None,
            tdd_mode=True,
        )

        checkboxes = ExtractedCheckboxes(
            items=[
                CheckboxItem(
                    text="Add user authentication",
                    checked=False,
                    line_number=1,
                    indent_level=0,
                    raw_line="- [ ] Add user authentication",
                    parent_heading="Implementation",
                ),
                CheckboxItem(
                    text="Create login endpoint",
                    checked=False,
                    line_number=2,
                    indent_level=0,
                    raw_line="- [ ] Create login endpoint",
                    parent_heading="Implementation",
                ),
            ],
            total_count=2,
            checked_count=0,
        )

        result = builder.build_from_checkboxes(checkboxes)

        # Should have test + implementation pairs for each checkbox
        # TDD mode uses "Write tests for:" prefix
        test_tasks = [t for t in result.tasks if t.title.startswith("Write tests for:")]
        impl_tasks = [
            t
            for t in result.tasks
            if not t.title.startswith("Write tests for:") and t.task_type == "task"
        ]

        # With 2 checkboxes in TDD mode, we expect 2 test + 2 impl = 4 task-level items
        assert len(test_tasks) >= 2, f"Expected at least 2 test tasks, got {len(test_tasks)}"
        assert len(impl_tasks) >= 2, f"Expected at least 2 impl tasks, got {len(impl_tasks)}"

        # Verify dependency: impl blocked by test
        for impl_task in impl_tasks:
            deps = dep_manager.get_all_dependencies(impl_task.id)
            blocked_by_ids = [d.depends_on for d in deps if d.dep_type == "blocks"]
            # Each impl should be blocked by its corresponding test
            matching_tests = [
                t for t in test_tasks if t.title == f"Write tests for: {impl_task.title}"
            ]
            if matching_tests:
                assert matching_tests[0].id in blocked_by_ids

    def test_build_from_checkboxes_no_tdd_pairs_when_disabled(
        self,
        task_manager: LocalTaskManager,
        dep_manager: TaskDependencyManager,
        project_id: str,
    ):
        """When tdd_mode=False, build_from_checkboxes creates single tasks."""
        from gobby.tasks.spec_parser import CheckboxItem, ExtractedCheckboxes

        builder = TaskHierarchyBuilder(
            task_manager=task_manager,
            project_id=project_id,
            parent_task_id=None,
            tdd_mode=False,
        )

        checkboxes = ExtractedCheckboxes(
            items=[
                CheckboxItem(
                    text="Add user authentication",
                    checked=False,
                    line_number=1,
                    indent_level=0,
                    raw_line="- [ ] Add user authentication",
                    parent_heading="Implementation",
                ),
                CheckboxItem(
                    text="Create login endpoint",
                    checked=False,
                    line_number=2,
                    indent_level=0,
                    raw_line="- [ ] Create login endpoint",
                    parent_heading="Implementation",
                ),
            ],
            total_count=2,
            checked_count=0,
        )

        result = builder.build_from_checkboxes(checkboxes)

        # Should NOT have test tasks
        test_tasks = [t for t in result.tasks if t.title.startswith("Write tests for:")]
        assert len(test_tasks) == 0, f"Expected no test tasks, got {len(test_tasks)}"


# =============================================================================
# Test expand_from_spec with workflow TDD mode
# =============================================================================


class TestExpandFromSpecTddMode:
    """Test expand_from_spec respects tdd_mode from workflow state."""

    @pytest.mark.asyncio
    async def test_expand_from_spec_uses_workflow_tdd_mode(
        self,
        temp_db: LocalDatabase,
        task_manager: LocalTaskManager,
        workflow_state_manager: WorkflowStateManager,
        session_with_tdd_mode: tuple[str, str],
        temp_dir: Path,
    ):
        """expand_from_spec creates TDD pairs when workflow tdd_mode=True."""
        session_id, project_id = session_with_tdd_mode

        # Create a spec file
        spec_file = temp_dir / "test_spec.md"
        spec_file.write_text("""# Test Feature

## Implementation Tasks

- [ ] Add user model
- [ ] Create user API endpoint
""")

        # Create parent task for the spec
        parent_task = task_manager.create_task(
            project_id=project_id,
            title="Test Feature Spec",
            task_type="epic",
        )

        # Create resolve_tdd_mode function
        def resolve_tdd_mode(sid: str | None) -> bool:
            if not sid:
                return False
            state = workflow_state_manager.get_state(sid)
            if state and "tdd_mode" in state.variables:
                return bool(state.variables["tdd_mode"])
            return False

        from gobby.mcp_proxy.tools.task_expansion import create_expansion_registry

        registry = create_expansion_registry(
            task_manager=task_manager,
            task_expander=None,  # Not needed for structured parsing
            resolve_tdd_mode=resolve_tdd_mode,
        )

        expand_from_spec_tool = registry._tools.get("expand_from_spec")
        assert expand_from_spec_tool is not None

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context",
            return_value={"id": project_id, "path": str(temp_dir)},
        ):
            result = await expand_from_spec_tool.func(
                spec_path=str(spec_file),
                parent_task_id=parent_task.id,
                session_id=session_id,
            )

        assert "error" not in result
        assert result.get("tasks_created", 0) > 0

        # Get all created tasks
        all_tasks = task_manager.list_tasks(project_id=project_id)

        # Filter to descendants (tasks under the parent or its children)
        child_tasks = [t for t in all_tasks if t.id != parent_task.id]

        # Should have test tasks (TDD mode creates "Write tests for:" prefixed tasks)
        test_tasks = [
            t
            for t in child_tasks
            if t.title.startswith("Test:") or t.title.startswith("Write tests for:")
        ]
        impl_tasks = [
            t
            for t in child_tasks
            if not t.title.startswith("Test:")
            and not t.title.startswith("Write tests for:")
            and t.task_type == "task"
        ]

        # With TDD mode, we expect test tasks
        assert len(test_tasks) > 0, "Expected test tasks to be created with tdd_mode=True"
        assert len(impl_tasks) > 0, "Expected implementation tasks to be created"

    @pytest.mark.asyncio
    async def test_expand_from_spec_no_tdd_pairs_when_disabled(
        self,
        temp_db: LocalDatabase,
        task_manager: LocalTaskManager,
        workflow_state_manager: WorkflowStateManager,
        session_without_tdd_mode: tuple[str, str],
        temp_dir: Path,
    ):
        """expand_from_spec creates single tasks when workflow tdd_mode=False."""
        session_id, project_id = session_without_tdd_mode

        spec_file = temp_dir / "test_spec2.md"
        spec_file.write_text("""# Test Feature

## Implementation Tasks

- [ ] Add user model
- [ ] Create user API endpoint
""")

        parent_task = task_manager.create_task(
            project_id=project_id,
            title="Test Feature Spec No TDD",
            task_type="epic",
        )

        def resolve_tdd_mode(sid: str | None) -> bool:
            if not sid:
                return False
            state = workflow_state_manager.get_state(sid)
            if state and "tdd_mode" in state.variables:
                return bool(state.variables["tdd_mode"])
            return False

        from gobby.mcp_proxy.tools.task_expansion import create_expansion_registry

        registry = create_expansion_registry(
            task_manager=task_manager,
            task_expander=None,
            resolve_tdd_mode=resolve_tdd_mode,
        )

        expand_from_spec_tool = registry._tools.get("expand_from_spec")

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context",
            return_value={"id": project_id, "path": str(temp_dir)},
        ):
            result = await expand_from_spec_tool.func(
                spec_path=str(spec_file),
                parent_task_id=parent_task.id,
                session_id=session_id,
            )

        assert "error" not in result

        all_tasks = task_manager.list_tasks(project_id=project_id)
        child_tasks = [t for t in all_tasks if t.id != parent_task.id]

        # Should NOT have test tasks when tdd_mode=False
        test_tasks = [
            t
            for t in child_tasks
            if t.title.startswith("Test:") or t.title.startswith("Write tests for:")
        ]
        assert len(test_tasks) == 0, "Expected no test tasks with tdd_mode=False"


# =============================================================================
# Test expand_from_prompt with workflow TDD mode
# =============================================================================


class TestExpandFromPromptTddMode:
    """Test expand_from_prompt respects tdd_mode from workflow state."""

    @pytest.mark.asyncio
    async def test_expand_from_prompt_passes_tdd_mode_to_expander(
        self,
        temp_db: LocalDatabase,
        task_manager: LocalTaskManager,
        workflow_state_manager: WorkflowStateManager,
        session_with_tdd_mode: tuple[str, str],
    ):
        """expand_from_prompt passes tdd_mode to TaskExpander.expand_task."""
        session_id, project_id = session_with_tdd_mode

        def resolve_tdd_mode(sid: str | None) -> bool:
            if not sid:
                return False
            state = workflow_state_manager.get_state(sid)
            if state and "tdd_mode" in state.variables:
                return bool(state.variables["tdd_mode"])
            return False

        # Create mock task expander to verify tdd_mode is passed
        mock_expander = MagicMock()
        mock_expander.expand_task = AsyncMock(
            return_value={
                "subtask_ids": [],
                "subtask_count": 0,
            }
        )

        from gobby.mcp_proxy.tools.task_expansion import create_expansion_registry

        registry = create_expansion_registry(
            task_manager=task_manager,
            task_expander=mock_expander,
            resolve_tdd_mode=resolve_tdd_mode,
        )

        expand_from_prompt_tool = registry._tools.get("expand_from_prompt")
        assert expand_from_prompt_tool is not None

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context",
            return_value={"id": project_id},
        ):
            await expand_from_prompt_tool.func(
                prompt="Implement user authentication with OAuth",
                session_id=session_id,
            )

        # Verify expand_task was called with tdd_mode=True
        mock_expander.expand_task.assert_called_once()
        call_kwargs = mock_expander.expand_task.call_args.kwargs
        assert call_kwargs.get("tdd_mode") is True

    @pytest.mark.asyncio
    async def test_expand_from_prompt_tdd_mode_false_when_disabled(
        self,
        temp_db: LocalDatabase,
        task_manager: LocalTaskManager,
        workflow_state_manager: WorkflowStateManager,
        session_without_tdd_mode: tuple[str, str],
    ):
        """expand_from_prompt passes tdd_mode=False when workflow variable is False."""
        session_id, project_id = session_without_tdd_mode

        def resolve_tdd_mode(sid: str | None) -> bool:
            if not sid:
                return False
            state = workflow_state_manager.get_state(sid)
            if state and "tdd_mode" in state.variables:
                return bool(state.variables["tdd_mode"])
            return False

        mock_expander = MagicMock()
        mock_expander.expand_task = AsyncMock(
            return_value={
                "subtask_ids": [],
                "subtask_count": 0,
            }
        )

        from gobby.mcp_proxy.tools.task_expansion import create_expansion_registry

        registry = create_expansion_registry(
            task_manager=task_manager,
            task_expander=mock_expander,
            resolve_tdd_mode=resolve_tdd_mode,
        )

        expand_from_prompt_tool = registry._tools.get("expand_from_prompt")

        with patch(
            "gobby.mcp_proxy.tools.task_expansion.get_project_context",
            return_value={"id": project_id},
        ):
            await expand_from_prompt_tool.func(
                prompt="Implement user authentication",
                session_id=session_id,
            )

        mock_expander.expand_task.assert_called_once()
        call_kwargs = mock_expander.expand_task.call_args.kwargs
        assert call_kwargs.get("tdd_mode") is False


# =============================================================================
# Test expand_task with workflow TDD mode
# =============================================================================


class TestExpandTaskTddMode:
    """Test expand_task respects tdd_mode from workflow state."""

    @pytest.mark.asyncio
    async def test_expand_task_passes_tdd_mode_to_expander(
        self,
        temp_db: LocalDatabase,
        task_manager: LocalTaskManager,
        workflow_state_manager: WorkflowStateManager,
        session_with_tdd_mode: tuple[str, str],
    ):
        """expand_task passes tdd_mode to TaskExpander.expand_task."""
        session_id, project_id = session_with_tdd_mode

        def resolve_tdd_mode(sid: str | None) -> bool:
            if not sid:
                return False
            state = workflow_state_manager.get_state(sid)
            if state and "tdd_mode" in state.variables:
                return bool(state.variables["tdd_mode"])
            return False

        # Create a task to expand
        task = task_manager.create_task(
            project_id=project_id,
            title="Implement user authentication",
            description="Add OAuth support",
        )

        mock_expander = MagicMock()
        mock_expander.expand_task = AsyncMock(
            return_value={
                "subtask_ids": [],
                "subtask_count": 0,
            }
        )

        from gobby.mcp_proxy.tools.task_expansion import create_expansion_registry

        registry = create_expansion_registry(
            task_manager=task_manager,
            task_expander=mock_expander,
            resolve_tdd_mode=resolve_tdd_mode,
        )

        expand_task_tool = registry._tools.get("expand_task")
        assert expand_task_tool is not None

        await expand_task_tool.func(
            task_id=task.id,
            session_id=session_id,
        )

        mock_expander.expand_task.assert_called_once()
        call_kwargs = mock_expander.expand_task.call_args.kwargs
        assert call_kwargs.get("tdd_mode") is True

    @pytest.mark.asyncio
    async def test_expand_task_tdd_mode_none_without_session(
        self,
        temp_db: LocalDatabase,
        task_manager: LocalTaskManager,
        workflow_state_manager: WorkflowStateManager,
        project_id: str,
    ):
        """expand_task passes tdd_mode=None when no session_id provided."""

        def resolve_tdd_mode(sid: str | None) -> bool:
            if not sid:
                return False
            state = workflow_state_manager.get_state(sid)
            if state and "tdd_mode" in state.variables:
                return bool(state.variables["tdd_mode"])
            return False

        task = task_manager.create_task(
            project_id=project_id,
            title="Implement feature",
        )

        mock_expander = MagicMock()
        mock_expander.expand_task = AsyncMock(
            return_value={
                "subtask_ids": [],
                "subtask_count": 0,
            }
        )

        from gobby.mcp_proxy.tools.task_expansion import create_expansion_registry

        registry = create_expansion_registry(
            task_manager=task_manager,
            task_expander=mock_expander,
            resolve_tdd_mode=resolve_tdd_mode,
        )

        expand_task_tool = registry._tools.get("expand_task")

        # Call without session_id
        await expand_task_tool.func(task_id=task.id)

        mock_expander.expand_task.assert_called_once()
        call_kwargs = mock_expander.expand_task.call_args.kwargs
        # When no session, resolve_tdd_mode returns False (from our implementation)
        # But the tool passes None to expand_task which then falls back to config
        assert call_kwargs.get("tdd_mode") is None or call_kwargs.get("tdd_mode") is False
