"""Tests for workflows/state_actions.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


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
