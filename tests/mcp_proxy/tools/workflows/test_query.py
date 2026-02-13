"""Tests for workflow status query with multi-workflow support."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from gobby.workflows.definitions import WorkflowInstance, WorkflowState

pytestmark = pytest.mark.unit


def _make_mocks(
    existing_state: WorkflowState | None = None,
    instances: list[WorkflowInstance] | None = None,
    session_variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create mock dependencies for query functions."""
    state_manager = MagicMock()
    state_manager.get_state.return_value = existing_state

    session_manager = MagicMock()
    session_manager.resolve_session_reference.return_value = "uuid-session-1"

    instance_manager = MagicMock()
    instance_manager.get_active_instances.return_value = instances or []

    session_var_manager = MagicMock()
    session_var_manager.get_variables.return_value = session_variables or {}

    return {
        "state_manager": state_manager,
        "session_manager": session_manager,
        "instance_manager": instance_manager,
        "session_var_manager": session_var_manager,
    }


class TestGetWorkflowStatusMultiWorkflow:
    """Tests for get_workflow_status with multi-workflow support."""

    def test_returns_all_active_instances(self) -> None:
        """get_workflow_status returns all active workflow instances."""
        from gobby.mcp_proxy.tools.workflows._query import get_workflow_status

        instances = [
            WorkflowInstance(
                id="inst-1",
                session_id="uuid-session-1",
                workflow_name="auto-task",
                enabled=True,
                priority=10,
                current_step="work",
                variables={"session_task": "task-uuid"},
            ),
            WorkflowInstance(
                id="inst-2",
                session_id="uuid-session-1",
                workflow_name="plan-execute",
                enabled=True,
                priority=20,
                current_step="plan",
                variables={"plan_ready": False},
            ),
        ]
        state = WorkflowState(
            session_id="uuid-session-1",
            workflow_name="auto-task",
            step="work",
        )
        mocks = _make_mocks(
            existing_state=state,
            instances=instances,
            session_variables={"counter": 5},
        )

        result = get_workflow_status(
            mocks["state_manager"],
            mocks["session_manager"],
            session_id="#1",
            instance_manager=mocks["instance_manager"],
            session_var_manager=mocks["session_var_manager"],
        )

        assert result["success"] is True
        assert len(result["workflows"]) == 2
        assert result["workflows"][0]["workflow_name"] == "auto-task"
        assert result["workflows"][0]["current_step"] == "work"
        assert result["workflows"][0]["variables"] == {"session_task": "task-uuid"}
        assert result["workflows"][1]["workflow_name"] == "plan-execute"

    def test_shows_session_variables_separately(self) -> None:
        """get_workflow_status shows session variables in a separate field."""
        from gobby.mcp_proxy.tools.workflows._query import get_workflow_status

        instances = [
            WorkflowInstance(
                id="inst-1",
                session_id="uuid-session-1",
                workflow_name="auto-task",
                enabled=True,
                priority=10,
                current_step="work",
                variables={},
            ),
        ]
        state = WorkflowState(
            session_id="uuid-session-1",
            workflow_name="auto-task",
            step="work",
        )
        mocks = _make_mocks(
            existing_state=state,
            instances=instances,
            session_variables={"shared_flag": True, "counter": 42},
        )

        result = get_workflow_status(
            mocks["state_manager"],
            mocks["session_manager"],
            session_id="#1",
            instance_manager=mocks["instance_manager"],
            session_var_manager=mocks["session_var_manager"],
        )

        assert result["success"] is True
        assert result["session_variables"] == {"shared_flag": True, "counter": 42}

    def test_no_instances_falls_back_to_state(self) -> None:
        """get_workflow_status without instance_manager falls back to legacy state."""
        from gobby.mcp_proxy.tools.workflows._query import get_workflow_status

        state = WorkflowState(
            session_id="uuid-session-1",
            workflow_name="auto-task",
            step="work",
            variables={"my_var": "val"},
        )
        mocks = _make_mocks(existing_state=state)

        result = get_workflow_status(
            mocks["state_manager"],
            mocks["session_manager"],
            session_id="#1",
        )

        # Falls back to legacy single-workflow response
        assert result["success"] is True
        assert result["has_workflow"] is True
        assert result["workflow_name"] == "auto-task"

    def test_each_instance_shows_priority_and_enabled(self) -> None:
        """Each workflow instance includes priority and enabled fields."""
        from gobby.mcp_proxy.tools.workflows._query import get_workflow_status

        instances = [
            WorkflowInstance(
                id="inst-1",
                session_id="uuid-session-1",
                workflow_name="dev",
                enabled=True,
                priority=5,
                current_step="code",
                variables={},
            ),
        ]
        state = WorkflowState(
            session_id="uuid-session-1",
            workflow_name="dev",
            step="code",
        )
        mocks = _make_mocks(existing_state=state, instances=instances)

        result = get_workflow_status(
            mocks["state_manager"],
            mocks["session_manager"],
            session_id="#1",
            instance_manager=mocks["instance_manager"],
            session_var_manager=mocks["session_var_manager"],
        )

        assert result["success"] is True
        wf = result["workflows"][0]
        assert wf["enabled"] is True
        assert wf["priority"] == 5

    def test_empty_instances_returns_no_workflows(self) -> None:
        """get_workflow_status with no active instances returns empty list."""
        from gobby.mcp_proxy.tools.workflows._query import get_workflow_status

        mocks = _make_mocks(existing_state=None, instances=[])

        result = get_workflow_status(
            mocks["state_manager"],
            mocks["session_manager"],
            session_id="#1",
            instance_manager=mocks["instance_manager"],
            session_var_manager=mocks["session_var_manager"],
        )

        assert result["success"] is True
        assert result["workflows"] == []
