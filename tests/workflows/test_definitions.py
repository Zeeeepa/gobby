"""Tests for WorkflowInstance model in definitions.py."""

from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.unit


def test_workflow_instance_required_fields() -> None:
    """Test that WorkflowInstance can be instantiated with required fields only."""
    from gobby.workflows.definitions import WorkflowInstance

    instance = WorkflowInstance(
        id="inst-123",
        session_id="session-abc",
        workflow_name="auto-task",
    )

    assert instance.id == "inst-123"
    assert instance.session_id == "session-abc"
    assert instance.workflow_name == "auto-task"


def test_workflow_instance_defaults() -> None:
    """Test that WorkflowInstance has correct default values."""
    from gobby.workflows.definitions import WorkflowInstance

    instance = WorkflowInstance(
        id="inst-123",
        session_id="session-abc",
        workflow_name="auto-task",
    )

    assert instance.enabled is True
    assert instance.priority == 100
    assert instance.current_step is None
    assert instance.step_entered_at is None
    assert instance.step_action_count == 0
    assert instance.total_action_count == 0
    assert instance.variables == {}
    assert instance.context_injected is False
    assert instance.created_at is not None
    assert instance.updated_at is not None


def test_workflow_instance_all_fields() -> None:
    """Test that WorkflowInstance can be instantiated with all fields."""
    from gobby.workflows.definitions import WorkflowInstance

    now = datetime.now(UTC)
    instance = WorkflowInstance(
        id="inst-456",
        session_id="session-def",
        workflow_name="developer",
        enabled=False,
        priority=20,
        current_step="red",
        step_entered_at=now,
        step_action_count=5,
        total_action_count=12,
        variables={"tests_written": True, "task_id": "task-789"},
        context_injected=True,
        created_at=now,
        updated_at=now,
    )

    assert instance.id == "inst-456"
    assert instance.session_id == "session-def"
    assert instance.workflow_name == "developer"
    assert instance.enabled is False
    assert instance.priority == 20
    assert instance.current_step == "red"
    assert instance.step_entered_at == now
    assert instance.step_action_count == 5
    assert instance.total_action_count == 12
    assert instance.variables == {"tests_written": True, "task_id": "task-789"}
    assert instance.context_injected is True


def test_workflow_instance_to_dict() -> None:
    """Test that WorkflowInstance serializes to dict correctly."""
    from gobby.workflows.definitions import WorkflowInstance

    now = datetime.now(UTC)
    instance = WorkflowInstance(
        id="inst-123",
        session_id="session-abc",
        workflow_name="auto-task",
        enabled=True,
        priority=25,
        current_step="work",
        step_entered_at=now,
        step_action_count=3,
        total_action_count=7,
        variables={"session_task": "task-1"},
        context_injected=True,
        created_at=now,
        updated_at=now,
    )

    d = instance.to_dict()

    assert isinstance(d, dict)
    assert d["id"] == "inst-123"
    assert d["session_id"] == "session-abc"
    assert d["workflow_name"] == "auto-task"
    assert d["enabled"] is True
    assert d["priority"] == 25
    assert d["current_step"] == "work"
    assert d["step_entered_at"] == now.isoformat()
    assert d["step_action_count"] == 3
    assert d["total_action_count"] == 7
    assert d["variables"] == {"session_task": "task-1"}
    assert d["context_injected"] is True
    assert d["created_at"] == now.isoformat()
    assert d["updated_at"] == now.isoformat()


def test_workflow_instance_to_dict_none_step() -> None:
    """Test that to_dict handles None values for optional fields."""
    from gobby.workflows.definitions import WorkflowInstance

    instance = WorkflowInstance(
        id="inst-123",
        session_id="session-abc",
        workflow_name="session-lifecycle",
    )

    d = instance.to_dict()

    assert d["current_step"] is None
    assert d["step_entered_at"] is None


def test_workflow_instance_from_dict() -> None:
    """Test that WorkflowInstance can be deserialized from dict."""
    from gobby.workflows.definitions import WorkflowInstance

    now = datetime.now(UTC)
    data = {
        "id": "inst-789",
        "session_id": "session-xyz",
        "workflow_name": "developer",
        "enabled": False,
        "priority": 20,
        "current_step": "green",
        "step_entered_at": now.isoformat(),
        "step_action_count": 10,
        "total_action_count": 25,
        "variables": {"tests_passing": True},
        "context_injected": True,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    instance = WorkflowInstance.from_dict(data)

    assert instance.id == "inst-789"
    assert instance.session_id == "session-xyz"
    assert instance.workflow_name == "developer"
    assert instance.enabled is False
    assert instance.priority == 20
    assert instance.current_step == "green"
    assert instance.step_entered_at == now
    assert instance.step_action_count == 10
    assert instance.total_action_count == 25
    assert instance.variables == {"tests_passing": True}
    assert instance.context_injected is True


def test_workflow_instance_from_dict_minimal() -> None:
    """Test from_dict with only required fields, defaults applied."""
    from gobby.workflows.definitions import WorkflowInstance

    data = {
        "id": "inst-min",
        "session_id": "session-min",
        "workflow_name": "test-wf",
    }

    instance = WorkflowInstance.from_dict(data)

    assert instance.id == "inst-min"
    assert instance.workflow_name == "test-wf"
    assert instance.enabled is True
    assert instance.priority == 100
    assert instance.current_step is None
    assert instance.variables == {}
    assert instance.context_injected is False


def test_workflow_instance_roundtrip() -> None:
    """Test that to_dict -> from_dict roundtrip preserves all fields."""
    from gobby.workflows.definitions import WorkflowInstance

    now = datetime.now(UTC)
    original = WorkflowInstance(
        id="inst-rt",
        session_id="session-rt",
        workflow_name="auto-task",
        enabled=True,
        priority=25,
        current_step="work",
        step_entered_at=now,
        step_action_count=3,
        total_action_count=7,
        variables={"key": "value", "nested": {"a": 1}},
        context_injected=True,
        created_at=now,
        updated_at=now,
    )

    d = original.to_dict()
    restored = WorkflowInstance.from_dict(d)

    assert restored.id == original.id
    assert restored.session_id == original.session_id
    assert restored.workflow_name == original.workflow_name
    assert restored.enabled == original.enabled
    assert restored.priority == original.priority
    assert restored.current_step == original.current_step
    assert restored.step_entered_at == original.step_entered_at
    assert restored.step_action_count == original.step_action_count
    assert restored.total_action_count == original.total_action_count
    assert restored.variables == original.variables
    assert restored.context_injected == original.context_injected
    assert restored.created_at == original.created_at
    assert restored.updated_at == original.updated_at
