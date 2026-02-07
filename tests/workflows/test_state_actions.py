"""Tests for workflow state_actions handlers.

Tests the handle_set_variable and handle_increment_variable handlers,
specifically the `variable` key support (alias for `name`).
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from gobby.workflows.actions import ActionContext
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.state_actions import handle_increment_variable, handle_set_variable
from gobby.workflows.templates import TemplateEngine

pytestmark = pytest.mark.unit


@pytest.fixture
def workflow_state() -> WorkflowState:
    """Create a workflow state with empty variables."""
    return WorkflowState(
        session_id="test-session",
        workflow_name="test-workflow",
        step="test-step",
        step_entered_at=datetime.now(UTC),
        variables={},
    )


@pytest.fixture
def action_context(workflow_state: WorkflowState) -> ActionContext:
    """Create an ActionContext for testing."""
    return ActionContext(
        session_id="test-session",
        state=workflow_state,
        db=MagicMock(),
        session_manager=MagicMock(),
        template_engine=TemplateEngine(),
    )


class TestHandleSetVariableNameKey:
    """Tests for handle_set_variable with `name` key (original behavior)."""

    @pytest.mark.asyncio
    async def test_sets_variable_with_name_key(self, action_context) -> None:
        """name= kwarg sets variable correctly."""
        result = await handle_set_variable(action_context, name="my_var", value="hello")

        assert result == {"variable_set": "my_var", "value": "hello"}
        assert action_context.state.variables["my_var"] == "hello"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_name(self, action_context) -> None:
        """Returns None when neither name nor variable is provided."""
        result = await handle_set_variable(action_context, value="hello")

        assert result is None


class TestHandleSetVariableVariableKey:
    """Tests for handle_set_variable with `variable` key (YAML alias)."""

    @pytest.mark.asyncio
    async def test_sets_variable_with_variable_key(self, action_context) -> None:
        """variable= kwarg sets variable correctly (used in meeseeks YAML)."""
        result = await handle_set_variable(action_context, variable="task_id", value="abc-123")

        assert result == {"variable_set": "task_id", "value": "abc-123"}
        assert action_context.state.variables["task_id"] == "abc-123"

    @pytest.mark.asyncio
    async def test_name_takes_precedence_over_variable(self, action_context) -> None:
        """When both name and variable are provided, name wins."""
        result = await handle_set_variable(
            action_context, name="from_name", variable="from_variable", value="test"
        )

        assert result == {"variable_set": "from_name", "value": "test"}
        assert action_context.state.variables["from_name"] == "test"
        assert "from_variable" not in action_context.state.variables

    @pytest.mark.asyncio
    async def test_renders_template_value(self, action_context) -> None:
        """Template values are rendered before setting."""
        action_context.state.variables["existing"] = "world"
        result = await handle_set_variable(
            action_context, variable="greeting", value="{{ variables.existing }}"
        )

        assert result == {"variable_set": "greeting", "value": "world"}

    @pytest.mark.asyncio
    async def test_logs_warning_when_name_and_variable_differ(
        self, action_context, caplog, enable_log_propagation
    ) -> None:
        """Warning is logged when name and variable differ."""
        import logging

        with caplog.at_level(logging.WARNING):
            await handle_set_variable(
                action_context, name="from_name", variable="from_variable", value="test"
            )

        assert "from_name" in caplog.text
        assert "from_variable" in caplog.text


class TestHandleIncrementVariableVariableKey:
    """Tests for handle_increment_variable with `variable` key."""

    @pytest.mark.asyncio
    async def test_increments_with_variable_key(self, action_context) -> None:
        """variable= kwarg works for increment_variable."""
        action_context.state.variables["counter"] = 5
        result = await handle_increment_variable(action_context, variable="counter")

        assert result == {"variable_incremented": "counter", "value": 6}
        assert action_context.state.variables["counter"] == 6

    @pytest.mark.asyncio
    async def test_increments_with_name_key(self, action_context) -> None:
        """name= kwarg still works for increment_variable."""
        action_context.state.variables["counter"] = 10
        result = await handle_increment_variable(action_context, name="counter", amount=5)

        assert result == {"variable_incremented": "counter", "value": 15}

    @pytest.mark.asyncio
    async def test_returns_none_when_no_name(self, action_context) -> None:
        """Returns None when neither name nor variable is provided."""
        result = await handle_increment_variable(action_context, amount=1)

        assert result is None

    @pytest.mark.asyncio
    async def test_name_takes_precedence_over_variable(self, action_context) -> None:
        """When both name and variable are provided, name wins."""
        action_context.state.variables["from_name"] = 10
        action_context.state.variables["from_variable"] = 20
        result = await handle_increment_variable(
            action_context, name="from_name", variable="from_variable", amount=1
        )

        assert result == {"variable_incremented": "from_name", "value": 11}
        assert action_context.state.variables["from_variable"] == 20
