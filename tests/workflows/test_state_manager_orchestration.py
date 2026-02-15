"""
Tests for WorkflowStateManager.update_orchestration_lists.

Verifies atomic read-modify-write for orchestration tracking lists,
preventing TOCTOU races between poll_agent_status and orchestrate_ready_tasks.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.workflows.state_manager import WorkflowStateManager

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path):
    database = LocalDatabase(tmp_path / "test.db")
    run_migrations(database)
    # Create prerequisite project and session for FK constraints
    database.execute(
        "INSERT INTO projects (id, name) VALUES (?, ?)",
        ("proj1", "test-project"),
    )
    yield database
    database.close()


@pytest.fixture
def state_manager(db):
    return WorkflowStateManager(db)


def _ensure_session(db, session_id: str) -> None:
    """Ensure a session row exists for FK constraints."""
    db.execute(
        "INSERT OR IGNORE INTO sessions (id, external_id, machine_id, source, project_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, session_id, "test-machine", "claude", "proj1"),
    )


def _insert_state(db, session_id: str, variables: dict | None = None) -> None:
    """Insert a workflow state row for testing."""
    _ensure_session(db, session_id)
    db.execute(
        """
        INSERT INTO workflow_states (
            session_id, workflow_name, step, step_entered_at,
            step_action_count, total_action_count,
            observations, reflection_pending, context_injected,
            variables, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            "test_wf",
            "working",
            datetime.now(UTC).isoformat(),
            0,
            0,
            "[]",
            0,
            0,
            json.dumps(variables or {}),
            datetime.now(UTC).isoformat(),
        ),
    )


class TestUpdateOrchestrationLists:
    """Tests for atomic orchestration list updates."""

    def test_append_to_spawned(self, state_manager, db) -> None:
        """Appending to spawned_agents works atomically."""
        _insert_state(db, "sess1", {"spawned_agents": [{"session_id": "a1"}]})

        result = state_manager.update_orchestration_lists(
            "sess1",
            append_to_spawned=[{"session_id": "a2"}, {"session_id": "a3"}],
        )

        assert result is True
        state = state_manager.get_state("sess1")
        assert state is not None
        agents = state.variables["spawned_agents"]
        assert len(agents) == 3
        assert {a["session_id"] for a in agents} == {"a1", "a2", "a3"}

    def test_replace_spawned(self, state_manager, db) -> None:
        """Replacing spawned_agents replaces the entire list."""
        _insert_state(db, "sess1", {"spawned_agents": [{"session_id": "a1"}, {"session_id": "a2"}]})

        result = state_manager.update_orchestration_lists(
            "sess1",
            replace_spawned=[{"session_id": "a2"}],
        )

        assert result is True
        state = state_manager.get_state("sess1")
        assert state is not None
        assert len(state.variables["spawned_agents"]) == 1
        assert state.variables["spawned_agents"][0]["session_id"] == "a2"

    def test_replace_takes_precedence_over_remove(self, state_manager, db) -> None:
        """replace_spawned takes precedence over remove_from_spawned."""
        _insert_state(db, "sess1", {"spawned_agents": [{"session_id": "a1"}, {"session_id": "a2"}]})

        result = state_manager.update_orchestration_lists(
            "sess1",
            remove_from_spawned={"a1"},
            replace_spawned=[{"session_id": "a3"}],
        )

        assert result is True
        state = state_manager.get_state("sess1")
        assert state is not None
        # replace wins — should have a3, not filtered a1
        assert len(state.variables["spawned_agents"]) == 1
        assert state.variables["spawned_agents"][0]["session_id"] == "a3"

    def test_remove_from_spawned(self, state_manager, db) -> None:
        """Removing specific session IDs from spawned_agents."""
        _insert_state(
            db,
            "sess1",
            {
                "spawned_agents": [
                    {"session_id": "a1"},
                    {"session_id": "a2"},
                    {"session_id": "a3"},
                ]
            },
        )

        result = state_manager.update_orchestration_lists(
            "sess1",
            remove_from_spawned={"a1", "a3"},
        )

        assert result is True
        state = state_manager.get_state("sess1")
        assert state is not None
        assert len(state.variables["spawned_agents"]) == 1
        assert state.variables["spawned_agents"][0]["session_id"] == "a2"

    def test_append_to_completed(self, state_manager, db) -> None:
        """Appending to completed_agents."""
        _insert_state(db, "sess1", {"completed_agents": [{"session_id": "done1"}]})

        result = state_manager.update_orchestration_lists(
            "sess1",
            append_to_completed=[{"session_id": "done2"}],
        )

        assert result is True
        state = state_manager.get_state("sess1")
        assert state is not None
        assert len(state.variables["completed_agents"]) == 2

    def test_append_to_failed(self, state_manager, db) -> None:
        """Appending to failed_agents."""
        _insert_state(db, "sess1", {})

        result = state_manager.update_orchestration_lists(
            "sess1",
            append_to_failed=[{"session_id": "f1", "reason": "crashed"}],
        )

        assert result is True
        state = state_manager.get_state("sess1")
        assert state is not None
        assert len(state.variables["failed_agents"]) == 1
        assert state.variables["failed_agents"][0]["reason"] == "crashed"

    def test_combined_update(self, state_manager, db) -> None:
        """All list updates happen atomically in one call."""
        _insert_state(
            db,
            "sess1",
            {
                "spawned_agents": [{"session_id": "a1"}, {"session_id": "a2"}],
                "completed_agents": [],
                "failed_agents": [],
            },
        )

        result = state_manager.update_orchestration_lists(
            "sess1",
            replace_spawned=[{"session_id": "a2"}],  # a1 finished
            append_to_completed=[{"session_id": "a1", "task_id": "t1"}],
        )

        assert result is True
        state = state_manager.get_state("sess1")
        assert state is not None
        assert len(state.variables["spawned_agents"]) == 1
        assert len(state.variables["completed_agents"]) == 1
        assert state.variables["completed_agents"][0]["session_id"] == "a1"

    def test_session_not_found(self, state_manager, db) -> None:
        """Returns False when session doesn't exist."""
        result = state_manager.update_orchestration_lists(
            "nonexistent",
            append_to_spawned=[{"session_id": "a1"}],
        )

        assert result is False

    def test_empty_initial_lists(self, state_manager, db) -> None:
        """Works when lists don't exist yet in variables."""
        _insert_state(db, "sess1", {})  # No orchestration lists

        result = state_manager.update_orchestration_lists(
            "sess1",
            append_to_spawned=[{"session_id": "a1"}],
            append_to_completed=[{"session_id": "done1"}],
            append_to_failed=[{"session_id": "fail1"}],
        )

        assert result is True
        state = state_manager.get_state("sess1")
        assert state is not None
        assert len(state.variables["spawned_agents"]) == 1
        assert len(state.variables["completed_agents"]) == 1
        assert len(state.variables["failed_agents"]) == 1

    def test_preserves_other_variables(self, state_manager, db) -> None:
        """Updating orchestration lists doesn't clobber other variables."""
        _insert_state(
            db,
            "sess1",
            {
                "session_task": "#123",
                "custom_var": "keep_me",
                "spawned_agents": [],
            },
        )

        state_manager.update_orchestration_lists(
            "sess1",
            append_to_spawned=[{"session_id": "a1"}],
        )

        state = state_manager.get_state("sess1")
        assert state is not None
        assert state.variables["session_task"] == "#123"
        assert state.variables["custom_var"] == "keep_me"
        assert len(state.variables["spawned_agents"]) == 1


class TestCheckAndReserveSlots:
    """Tests for atomic slot reservation."""

    def test_reserve_slots_basic(self, state_manager, db) -> None:
        """Reserves requested slots when capacity available."""
        _insert_state(db, "sess1", {"spawned_agents": [{"session_id": "a1"}]})

        reserved = state_manager.check_and_reserve_slots("sess1", max_concurrent=3, requested=2)

        assert reserved == 2
        state = state_manager.get_state("sess1")
        assert state is not None
        assert state.variables["_reserved_slots"] == 2

    def test_reserve_slots_limited_by_capacity(self, state_manager, db) -> None:
        """Reserves only available slots when requesting more than capacity."""
        _insert_state(db, "sess1", {"spawned_agents": [{"session_id": "a1"}, {"session_id": "a2"}]})

        reserved = state_manager.check_and_reserve_slots("sess1", max_concurrent=3, requested=5)

        assert reserved == 1  # Only 1 slot available (3 - 2 spawned)

    def test_reserve_slots_at_capacity(self, state_manager, db) -> None:
        """Returns 0 when at capacity."""
        _insert_state(
            db,
            "sess1",
            {"spawned_agents": [{"session_id": "a1"}, {"session_id": "a2"}]},
        )

        reserved = state_manager.check_and_reserve_slots("sess1", max_concurrent=2, requested=1)

        assert reserved == 0

    def test_reserve_slots_accounts_for_existing_reservations(self, state_manager, db) -> None:
        """Existing _reserved_slots count against capacity."""
        _insert_state(
            db,
            "sess1",
            {"spawned_agents": [{"session_id": "a1"}], "_reserved_slots": 1},
        )

        # 1 spawned + 1 reserved = 2 active, max 3 = 1 available
        reserved = state_manager.check_and_reserve_slots("sess1", max_concurrent=3, requested=5)

        assert reserved == 1
        state = state_manager.get_state("sess1")
        assert state is not None
        # Should be 1 (existing) + 1 (new) = 2
        assert state.variables["_reserved_slots"] == 2

    def test_reserve_slots_session_not_found(self, state_manager, db) -> None:
        """Returns 0 for nonexistent session."""
        reserved = state_manager.check_and_reserve_slots(
            "nonexistent", max_concurrent=5, requested=3
        )

        assert reserved == 0

    def test_release_reserved_slots(self, state_manager, db) -> None:
        """Releasing slots decrements _reserved_slots."""
        _insert_state(db, "sess1", {"_reserved_slots": 3})

        state_manager.release_reserved_slots("sess1", 2)

        state = state_manager.get_state("sess1")
        assert state is not None
        assert state.variables["_reserved_slots"] == 1

    def test_release_reserved_slots_floors_at_zero(self, state_manager, db) -> None:
        """Releasing more than reserved floors at 0."""
        _insert_state(db, "sess1", {"_reserved_slots": 1})

        state_manager.release_reserved_slots("sess1", 5)

        state = state_manager.get_state("sess1")
        assert state is not None
        assert state.variables["_reserved_slots"] == 0

    def test_release_reserved_slots_noop_for_zero(self, state_manager, db) -> None:
        """Releasing 0 slots is a no-op."""
        _insert_state(db, "sess1", {"_reserved_slots": 2})

        state_manager.release_reserved_slots("sess1", 0)

        state = state_manager.get_state("sess1")
        assert state is not None
        assert state.variables["_reserved_slots"] == 2

    def test_reserve_then_release_cycle(self, state_manager, db) -> None:
        """Full reserve-spawn-release cycle keeps state consistent."""
        _insert_state(db, "sess1", {"spawned_agents": []})

        # Reserve 2 slots
        reserved = state_manager.check_and_reserve_slots("sess1", max_concurrent=3, requested=2)
        assert reserved == 2

        # Spawn 2 agents and update lists
        state_manager.update_orchestration_lists(
            "sess1",
            append_to_spawned=[{"session_id": "a1"}, {"session_id": "a2"}],
        )

        # Release reservations
        state_manager.release_reserved_slots("sess1", 2)

        state = state_manager.get_state("sess1")
        assert state is not None
        assert len(state.variables["spawned_agents"]) == 2
        assert state.variables["_reserved_slots"] == 0

        # Next reservation should see 2 active, 1 available
        reserved = state_manager.check_and_reserve_slots("sess1", max_concurrent=3, requested=5)
        assert reserved == 1
