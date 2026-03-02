"""Tests for workflows/state_actions.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_state() -> MagicMock:
    state = MagicMock()
    state.variables = {}
    state.workflow_name = "test-wf"
    state.model_fields = ["variables", "workflow_name"]
    return state


@pytest.fixture
def mock_context(mock_state: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.db = MagicMock()
    ctx.session_id = "sess-1"
    ctx.state = mock_state
    ctx.template_engine = MagicMock()
    ctx.template_engine.render.side_effect = lambda v, _ctx: v
    return ctx


# --- set_variable ---


def test_set_variable_basic() -> None:
    from gobby.workflows.state_actions import set_variable

    state = MagicMock()
    state.variables = {}
    result = set_variable(state, "foo", "bar")
    assert result == {"variable_set": "foo", "value": "bar"}
    assert state.variables["foo"] == "bar"


def test_set_variable_no_name() -> None:
    from gobby.workflows.state_actions import set_variable

    result = set_variable(MagicMock(), None, "val")
    assert result is None


def test_set_variable_creates_variables_dict() -> None:
    from gobby.workflows.state_actions import set_variable

    state = MagicMock()
    state.variables = None
    result = set_variable(state, "key", 42)
    assert result is not None
    assert state.variables["key"] == 42


# --- increment_variable ---


def test_increment_variable_default() -> None:
    from gobby.workflows.state_actions import increment_variable

    state = MagicMock()
    state.variables = {"counter": 5}
    result = increment_variable(state, "counter")
    assert result == {"variable_incremented": "counter", "value": 6}


def test_increment_variable_custom_amount() -> None:
    from gobby.workflows.state_actions import increment_variable

    state = MagicMock()
    state.variables = {"x": 10}
    result = increment_variable(state, "x", 5)
    assert result == {"variable_incremented": "x", "value": 15}


def test_increment_variable_from_zero() -> None:
    from gobby.workflows.state_actions import increment_variable

    state = MagicMock()
    state.variables = {}
    result = increment_variable(state, "new_counter")
    assert result == {"variable_incremented": "new_counter", "value": 1}


def test_increment_variable_no_name() -> None:
    from gobby.workflows.state_actions import increment_variable

    result = increment_variable(MagicMock(), None)
    assert result is None


def test_increment_variable_non_numeric() -> None:
    from gobby.workflows.state_actions import increment_variable

    state = MagicMock()
    state.variables = {"bad": "not a number"}
    with pytest.raises(TypeError, match="Cannot increment non-numeric"):
        increment_variable(state, "bad")


def test_increment_variable_creates_variables_dict() -> None:
    from gobby.workflows.state_actions import increment_variable

    state = MagicMock()
    state.variables = None
    result = increment_variable(state, "x", 3)
    assert result is not None
    assert state.variables["x"] == 3


# --- mark_loop_complete ---


def test_mark_loop_complete() -> None:
    from gobby.workflows.state_actions import mark_loop_complete

    state = MagicMock()
    state.variables = {}
    result = mark_loop_complete(state)
    assert result == {"loop_marked_complete": True}
    assert state.variables["stop_reason"] == "completed"


def test_mark_loop_complete_creates_variables() -> None:
    from gobby.workflows.state_actions import mark_loop_complete

    state = MagicMock()
    state.variables = None
    result = mark_loop_complete(state)
    assert result == {"loop_marked_complete": True}


# --- load_workflow_state / save_workflow_state ---


def test_load_workflow_state_found() -> None:
    from gobby.workflows.state_actions import load_workflow_state

    db = MagicMock()
    state = MagicMock()
    state.model_fields = ["variables"]

    loaded = MagicMock()
    loaded.model_fields = ["variables"]
    loaded.variables = {"a": 1}

    with patch("gobby.workflows.state_manager.WorkflowStateManager") as MockMgr:
        MockMgr.return_value.get_state.return_value = loaded
        result = load_workflow_state(db, "sess-1", state)

    assert result == {"state_loaded": True}


def test_load_workflow_state_not_found() -> None:
    from gobby.workflows.state_actions import load_workflow_state

    with patch("gobby.workflows.state_manager.WorkflowStateManager") as MockMgr:
        MockMgr.return_value.get_state.return_value = None
        result = load_workflow_state(MagicMock(), "sess-1", MagicMock())

    assert result == {"state_loaded": False}


def test_save_workflow_state() -> None:
    from gobby.workflows.state_actions import save_workflow_state

    with patch("gobby.workflows.state_manager.WorkflowStateManager") as MockMgr:
        result = save_workflow_state(MagicMock(), MagicMock())

    assert result == {"state_saved": True}
    MockMgr.return_value.save_state.assert_called_once()


# --- _coerce_rendered_value ---


def test_coerce_rendered_value_bool_true() -> None:
    from gobby.workflows.state_actions import _coerce_rendered_value

    assert _coerce_rendered_value("true") is True
    assert _coerce_rendered_value("True") is True
    assert _coerce_rendered_value("False") is False


def test_coerce_rendered_value_none() -> None:
    from gobby.workflows.state_actions import _coerce_rendered_value

    assert _coerce_rendered_value("null") is None
    assert _coerce_rendered_value("None") is None
    assert _coerce_rendered_value("") is None


def test_coerce_rendered_value_int() -> None:
    from gobby.workflows.state_actions import _coerce_rendered_value

    assert _coerce_rendered_value("42") == 42


def test_coerce_rendered_value_float() -> None:
    from gobby.workflows.state_actions import _coerce_rendered_value

    assert _coerce_rendered_value("3.14") == 3.14


def test_coerce_rendered_value_string() -> None:
    from gobby.workflows.state_actions import _coerce_rendered_value

    assert _coerce_rendered_value("hello world") == "hello world"


# --- _resolve_variable_name ---


def test_resolve_variable_name_from_name() -> None:
    from gobby.workflows.state_actions import _resolve_variable_name

    assert _resolve_variable_name({"name": "foo"}) == "foo"


def test_resolve_variable_name_from_variable() -> None:
    from gobby.workflows.state_actions import _resolve_variable_name

    assert _resolve_variable_name({"variable": "bar"}) == "bar"


def test_resolve_variable_name_conflict() -> None:
    from gobby.workflows.state_actions import _resolve_variable_name

    result = _resolve_variable_name({"name": "a", "variable": "b"}, "test")
    assert result == "a"  # name takes precedence


# --- handle_set_variable with template rendering ---


@pytest.mark.asyncio
async def test_handle_set_variable_with_template(mock_context: MagicMock) -> None:
    from gobby.workflows.state_actions import handle_set_variable

    mock_context.template_engine.render.return_value = "42"
    result = await handle_set_variable(mock_context, name="x", value="{{ variables.y }}")
    assert result is not None


@pytest.mark.asyncio
async def test_handle_set_variable_no_template_engine(mock_context: MagicMock) -> None:
    from gobby.workflows.state_actions import handle_set_variable

    mock_context.template_engine = None
    result = await handle_set_variable(mock_context, name="x", value="{{ y }}")
    assert result is not None


@pytest.mark.asyncio
async def test_handle_set_variable_plain_value(mock_context: MagicMock) -> None:
    from gobby.workflows.state_actions import handle_set_variable

    result = await handle_set_variable(mock_context, name="x", value="plain")
    assert result is not None


# --- handle_increment_variable ---


@pytest.mark.asyncio
async def test_handle_increment_variable(mock_context: MagicMock) -> None:
    from gobby.workflows.state_actions import handle_increment_variable

    mock_context.state.variables = {"c": 10}
    result = await handle_increment_variable(mock_context, name="c", amount=5)
    assert result is not None
    assert result["value"] == 15


# --- handle_mark_loop_complete ---


@pytest.mark.asyncio
async def test_handle_mark_loop_complete(mock_context: MagicMock) -> None:
    from gobby.workflows.state_actions import handle_mark_loop_complete

    result = await handle_mark_loop_complete(mock_context)
    assert result == {"loop_marked_complete": True}


# --- handle_end_workflow ---


@pytest.mark.asyncio
async def test_handle_end_workflow(mock_context: MagicMock) -> None:
    from gobby.workflows.state_actions import handle_end_workflow

    with patch("gobby.workflows.state_manager.WorkflowInstanceManager"):
        result = await handle_end_workflow(mock_context)

    assert result is not None
    assert result["ended"] is True


@pytest.mark.asyncio
async def test_handle_end_workflow_db_error(mock_context: MagicMock) -> None:
    from gobby.workflows.state_actions import handle_end_workflow

    with patch("gobby.workflows.state_manager.WorkflowInstanceManager") as MockMgr:
        MockMgr.return_value.set_enabled.side_effect = RuntimeError("db err")
        result = await handle_end_workflow(mock_context)

    assert result["ended"] is True


# --- handle_load/save_workflow_state ---


@pytest.mark.asyncio
async def test_handle_load_workflow_state(mock_context: MagicMock) -> None:
    from gobby.workflows.state_actions import handle_load_workflow_state

    with patch("gobby.workflows.state_manager.WorkflowStateManager") as MockMgr:
        MockMgr.return_value.get_state.return_value = None
        result = await handle_load_workflow_state(mock_context)
    assert result == {"state_loaded": False}


@pytest.mark.asyncio
async def test_handle_save_workflow_state(mock_context: MagicMock) -> None:
    from gobby.workflows.state_actions import handle_save_workflow_state

    with patch("gobby.workflows.state_manager.WorkflowStateManager"):
        result = await handle_save_workflow_state(mock_context)
    assert result == {"state_saved": True}
