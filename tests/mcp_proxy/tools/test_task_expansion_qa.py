"""Tests for expansion QA tools: save_expansion_qa_result and check_expansion_qa_result.

Tests cover:
- save_expansion_qa_result: Save QA findings to task.expansion_context.qa_result
- check_expansion_qa_result: Read QA findings from task.expansion_context.qa_result
"""

import json

import pytest

from gobby.mcp_proxy.tools.tasks._context import RegistryContext
from gobby.mcp_proxy.tools.tasks._expansion import create_expansion_registry
from gobby.storage.tasks import LocalTaskManager
from gobby.sync.tasks import TaskSyncManager

pytestmark = pytest.mark.unit


@pytest.fixture
def task_manager(temp_db):
    """Create a task manager with the shared temp database."""
    return LocalTaskManager(temp_db)


@pytest.fixture
def sync_manager(task_manager, temp_dir):
    """Create a sync manager with task manager and temp directory."""
    return TaskSyncManager(task_manager, temp_dir / "tasks.jsonl")


@pytest.fixture
def test_project(project_manager):
    """Create a test project for QA tests."""
    project = project_manager.create(
        name="test-project",
        repo_path="/tmp/test-project",
    )
    return project.id


@pytest.fixture
def expansion_registry(
    task_manager: LocalTaskManager,
    sync_manager: TaskSyncManager,
) -> dict:
    """Create expansion registry and return tools as dict."""
    ctx = RegistryContext(
        task_manager=task_manager,
        sync_manager=sync_manager,
        task_validator=None,
        agent_runner=None,
        config=None,
    )
    registry = create_expansion_registry(ctx)
    return registry._tools


@pytest.fixture
def parent_task(task_manager: LocalTaskManager, test_project: str) -> str:
    """Create a parent task for QA tests."""
    task = task_manager.create_task(
        project_id=test_project,
        title="Parent task for expansion QA",
        task_type="feature",
    )
    return task.id


@pytest.fixture
def parent_task_with_context(task_manager: LocalTaskManager, test_project: str) -> str:
    """Create a parent task with existing expansion_context (subtasks)."""
    task = task_manager.create_task(
        project_id=test_project,
        title="Parent task with existing context",
        task_type="feature",
    )
    spec = {"subtasks": [{"title": "Child A"}, {"title": "Child B"}]}
    task_manager.update_task(
        task.id,
        expansion_context=json.dumps(spec),
        expansion_status="completed",
    )
    return task.id


class TestSaveExpansionQaResult:
    """Tests for save_expansion_qa_result tool."""

    @pytest.mark.asyncio
    async def test_save_passing_result(
        self,
        expansion_registry: dict,
        parent_task: str,
        task_manager: LocalTaskManager,
    ) -> None:
        """Save a passing QA result with no fixes or escalations."""
        save_fn = expansion_registry["save_expansion_qa_result"].func

        result = await save_fn(
            task_id=parent_task,
            result={"passed": True, "fixes": [], "escalations": []},
        )

        assert result["saved"] is True
        assert result["passed"] is True
        assert result["task_id"] == parent_task

        # Verify stored in expansion_context
        task = task_manager.get_task(parent_task)
        context = json.loads(task.expansion_context)
        assert context["qa_result"]["passed"] is True
        assert context["qa_result"]["fixes"] == []
        assert context["qa_result"]["escalations"] == []

    @pytest.mark.asyncio
    async def test_save_result_with_fixes(
        self,
        expansion_registry: dict,
        parent_task: str,
        task_manager: LocalTaskManager,
    ) -> None:
        """Save a passing result with fixes applied."""
        save_fn = expansion_registry["save_expansion_qa_result"].func

        fixes = [
            {
                "type": "added_dependency",
                "task_ref": "#101",
                "detail": "#101 now depends on #100",
            },
            {
                "type": "added_parent_blocked_by",
                "task_ref": "#102",
                "detail": "Parent now blocked by #102",
            },
        ]

        result = await save_fn(
            task_id=parent_task,
            result={"passed": True, "fixes": fixes, "escalations": []},
        )

        assert result["saved"] is True
        assert result["passed"] is True

        task = task_manager.get_task(parent_task)
        context = json.loads(task.expansion_context)
        assert len(context["qa_result"]["fixes"]) == 2
        assert context["qa_result"]["fixes"][0]["type"] == "added_dependency"

    @pytest.mark.asyncio
    async def test_save_result_with_escalations(
        self,
        expansion_registry: dict,
        parent_task: str,
        task_manager: LocalTaskManager,
    ) -> None:
        """Save a failing result with escalations."""
        save_fn = expansion_registry["save_expansion_qa_result"].func

        escalations = [
            {
                "type": "missing_plan_section",
                "detail": "Plan section 2.3 has no matching task",
            },
        ]

        result = await save_fn(
            task_id=parent_task,
            result={"passed": False, "fixes": [], "escalations": escalations},
        )

        assert result["saved"] is True
        assert result["passed"] is False

        task = task_manager.get_task(parent_task)
        context = json.loads(task.expansion_context)
        assert context["qa_result"]["passed"] is False
        assert len(context["qa_result"]["escalations"]) == 1

    @pytest.mark.asyncio
    async def test_save_preserves_existing_context(
        self,
        expansion_registry: dict,
        parent_task_with_context: str,
        task_manager: LocalTaskManager,
    ) -> None:
        """QA result is appended without clobbering existing subtasks."""
        save_fn = expansion_registry["save_expansion_qa_result"].func

        result = await save_fn(
            task_id=parent_task_with_context,
            result={"passed": True, "fixes": [], "escalations": []},
        )

        assert result["saved"] is True

        task = task_manager.get_task(parent_task_with_context)
        context = json.loads(task.expansion_context)
        # Existing subtasks preserved
        assert "subtasks" in context
        assert len(context["subtasks"]) == 2
        # QA result added
        assert context["qa_result"]["passed"] is True

    @pytest.mark.asyncio
    async def test_save_missing_passed_field(
        self,
        expansion_registry: dict,
        parent_task: str,
    ) -> None:
        """Missing 'passed' field returns error."""
        save_fn = expansion_registry["save_expansion_qa_result"].func

        result = await save_fn(
            task_id=parent_task,
            result={"fixes": [], "escalations": []},
        )

        assert "error" in result
        assert "passed" in result["error"]

    @pytest.mark.asyncio
    async def test_save_missing_fixes_field(
        self,
        expansion_registry: dict,
        parent_task: str,
    ) -> None:
        """Missing 'fixes' field returns error."""
        save_fn = expansion_registry["save_expansion_qa_result"].func

        result = await save_fn(
            task_id=parent_task,
            result={"passed": True, "escalations": []},
        )

        assert "error" in result
        assert "fixes" in result["error"]

    @pytest.mark.asyncio
    async def test_save_missing_escalations_field(
        self,
        expansion_registry: dict,
        parent_task: str,
    ) -> None:
        """Missing 'escalations' field returns error."""
        save_fn = expansion_registry["save_expansion_qa_result"].func

        result = await save_fn(
            task_id=parent_task,
            result={"passed": True, "fixes": []},
        )

        assert "error" in result
        assert "escalations" in result["error"]

    @pytest.mark.asyncio
    async def test_save_task_not_found(
        self,
        expansion_registry: dict,
    ) -> None:
        """Invalid task_id returns error."""
        save_fn = expansion_registry["save_expansion_qa_result"].func

        result = await save_fn(
            task_id="nonexistent-uuid",
            result={"passed": True, "fixes": [], "escalations": []},
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_save_no_prior_context(
        self,
        expansion_registry: dict,
        parent_task: str,
        task_manager: LocalTaskManager,
    ) -> None:
        """Task with no expansion_context gets fresh JSON with qa_result."""
        save_fn = expansion_registry["save_expansion_qa_result"].func

        # Verify no prior context
        task = task_manager.get_task(parent_task)
        assert task.expansion_context is None

        result = await save_fn(
            task_id=parent_task,
            result={"passed": True, "fixes": [], "escalations": []},
        )

        assert result["saved"] is True

        task = task_manager.get_task(parent_task)
        context = json.loads(task.expansion_context)
        assert context == {"qa_result": {"passed": True, "fixes": [], "escalations": []}}


class TestCheckExpansionQaResult:
    """Tests for check_expansion_qa_result tool."""

    @pytest.mark.asyncio
    async def test_check_existing_result(
        self,
        expansion_registry: dict,
        parent_task: str,
        task_manager: LocalTaskManager,
    ) -> None:
        """Returns stored QA result when present."""
        # First save a result
        qa_result = {
            "passed": True,
            "fixes": [{"type": "added_dependency", "task_ref": "#10", "detail": "test"}],
            "escalations": [],
        }
        context = {"subtasks": [], "qa_result": qa_result}
        task_manager.update_task(parent_task, expansion_context=json.dumps(context))

        check_fn = expansion_registry["check_expansion_qa_result"].func
        result = await check_fn(task_id=parent_task)

        assert result["passed"] is True
        assert len(result["fixes"]) == 1
        assert result["escalations"] == []

    @pytest.mark.asyncio
    async def test_check_no_qa_result_key(
        self,
        expansion_registry: dict,
        parent_task_with_context: str,
    ) -> None:
        """expansion_context exists but has no qa_result key — returns skipped response."""
        check_fn = expansion_registry["check_expansion_qa_result"].func
        result = await check_fn(task_id=parent_task_with_context)

        assert "error" not in result
        assert result["passed"] is True
        assert result["qa_skipped"] is True
        assert result["reason"] == "QA agent did not save result"
        assert result["fixes"] == []
        assert result["escalations"] == []

    @pytest.mark.asyncio
    async def test_check_no_expansion_context(
        self,
        expansion_registry: dict,
        parent_task: str,
    ) -> None:
        """Task has no expansion_context at all — returns skipped response."""
        check_fn = expansion_registry["check_expansion_qa_result"].func
        result = await check_fn(task_id=parent_task)

        assert "error" not in result
        assert result["passed"] is True
        assert result["qa_skipped"] is True
        assert result["reason"] == "No expansion context on task"
        assert result["fixes"] == []
        assert result["escalations"] == []

    @pytest.mark.asyncio
    async def test_check_invalid_expansion_context_json(
        self,
        expansion_registry: dict,
        parent_task: str,
        task_manager: LocalTaskManager,
    ) -> None:
        """Invalid JSON in expansion_context — returns skipped response."""
        task_manager.update_task(parent_task, expansion_context="not-valid-json{{{")

        check_fn = expansion_registry["check_expansion_qa_result"].func
        result = await check_fn(task_id=parent_task)

        assert "error" not in result
        assert result["passed"] is True
        assert result["qa_skipped"] is True
        assert result["reason"] == "Invalid expansion_context JSON"
        assert result["fixes"] == []
        assert result["escalations"] == []

    @pytest.mark.asyncio
    async def test_check_task_not_found(
        self,
        expansion_registry: dict,
    ) -> None:
        """Invalid task_id returns error."""
        check_fn = expansion_registry["check_expansion_qa_result"].func
        result = await check_fn(task_id="nonexistent-uuid")

        assert "error" in result
