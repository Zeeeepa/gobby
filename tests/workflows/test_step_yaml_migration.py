"""Tests for step workflow YAML migration to unified format."""

from __future__ import annotations

import pytest

from gobby.workflows.loader import WorkflowLoader

pytestmark = pytest.mark.unit

STEP_WORKFLOWS = [
    "auto-task",
    "developer",
    "generic",
    "code-review",
    "merge",
    "qa-reviewer",
]


class TestStepWorkflowsLoadWithoutError:
    """All step workflows should load without error after migration."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("workflow_name", STEP_WORKFLOWS)
    async def test_step_workflow_loads(
        self, db_loader: WorkflowLoader, workflow_name: str
    ) -> None:
        """Each step workflow loads without error."""
        definition = await db_loader.load_workflow(workflow_name)
        assert definition is not None, f"{workflow_name} failed to load"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("workflow_name", STEP_WORKFLOWS)
    async def test_step_workflow_type_defaults_to_step(
        self, db_loader: WorkflowLoader, workflow_name: str
    ) -> None:
        """Step workflows use default type='step' without explicit field."""
        definition = await db_loader.load_workflow(workflow_name)
        assert definition is not None
        assert definition.type == "step"


class TestStepWorkflowsEnabledFalse:
    """Step workflows should default to enabled=false (activated on demand)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("workflow_name", STEP_WORKFLOWS)
    async def test_step_workflow_enabled_false(
        self, db_loader: WorkflowLoader, workflow_name: str
    ) -> None:
        """Step workflow loads with enabled=false."""
        definition = await db_loader.load_workflow(workflow_name)
        assert definition is not None
        assert definition.enabled is False, f"{workflow_name} should have enabled=false"


class TestDeveloperWorkflowPriority:
    """Developer workflow should have priority=20."""

    @pytest.mark.asyncio
    async def test_developer_priority_20(self, db_loader: WorkflowLoader) -> None:
        """developer.yaml loads with priority=20."""
        definition = await db_loader.load_workflow("developer")
        assert definition is not None
        assert definition.priority == 20


class TestAutoTaskVariableScoping:
    """auto-task.yaml should have correctly scoped variables."""

    @pytest.mark.asyncio
    async def test_session_task_in_session_variables(self, db_loader: WorkflowLoader) -> None:
        """session_task should be in session_variables (shared across workflows)."""
        definition = await db_loader.load_workflow("auto-task")
        assert definition is not None
        assert "session_task" in definition.session_variables

    @pytest.mark.asyncio
    async def test_premature_stop_max_in_variables(self, db_loader: WorkflowLoader) -> None:
        """premature_stop_max_attempts should be in variables (workflow-scoped)."""
        definition = await db_loader.load_workflow("auto-task")
        assert definition is not None
        assert "premature_stop_max_attempts" in definition.variables
