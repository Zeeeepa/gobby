"""Tests for task-enforcement.yaml rules.

Verifies blocking rules for native task tools, edit gating, commit
requirements, validation bypass prevention, stop compliance, and
task claim/release tracking.
"""

from __future__ import annotations

import json

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import RuleDefinitionBody
from gobby.workflows.sync import sync_bundled_rules

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    db_path = tmp_path / "test_task_enforcement.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    return database


@pytest.fixture
def manager(db: LocalDatabase) -> LocalWorkflowDefinitionManager:
    return LocalWorkflowDefinitionManager(db)


def _sync_bundled(db):
    """Sync bundled rules from the real rules directory."""
    from gobby.workflows.sync import get_bundled_rules_path

    return sync_bundled_rules(db, get_bundled_rules_path())


TASK_ENFORCEMENT_RULES = {
    "block-native-task-tools",
    "require-task-before-edit",
    "require-commit-before-close",
    "block-skip-validation-with-commit",
    "block-ask-during-stop-compliance",
    "track-task-claim",
    "track-task-release",
}


class TestTaskEnforcementSync:
    """Test that task-enforcement.yaml syncs correctly."""

    def test_bundled_file_syncs_all_rules(self, db, manager) -> None:
        """All 7 task-enforcement rules should sync to workflow_definitions."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        rule_names = {r.name for r in rules}

        assert TASK_ENFORCEMENT_RULES.issubset(rule_names), (
            f"Missing: {TASK_ENFORCEMENT_RULES - rule_names}"
        )

    def test_all_rules_have_group(self, db, manager) -> None:
        """All rules should have group='task-enforcement'."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in TASK_ENFORCEMENT_RULES:
                body = json.loads(row.definition_json)
                assert body.get("group") == "task-enforcement", (
                    f"{row.name} missing group"
                )

    def test_all_rules_are_valid_pydantic(self, db, manager) -> None:
        """All synced rules should be valid RuleDefinitionBody instances."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in TASK_ENFORCEMENT_RULES:
                body = RuleDefinitionBody.model_validate_json(row.definition_json)
                assert body.effect.type in {"block", "set_variable"}


class TestBlockNativeTaskTools:
    """Verify block-native-task-tools blocks CC native task tools."""

    def test_blocks_all_native_task_tools(self, db, manager) -> None:
        """Should block TaskCreate, TaskUpdate, TaskGet, TaskList, TodoWrite."""
        _sync_bundled(db)

        row = manager.get_by_name("block-native-task-tools")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        assert body.effect.type == "block"

        expected_tools = {"TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TodoWrite"}
        assert set(body.effect.tools) == expected_tools

    def test_no_when_condition(self, db, manager) -> None:
        """Should always fire (no when condition)."""
        _sync_bundled(db)

        row = manager.get_by_name("block-native-task-tools")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is None


class TestRequireTaskBeforeEdit:
    """Verify require-task-before-edit blocks edits without claimed task."""

    def test_blocks_edit_tools(self, db, manager) -> None:
        """Should block Edit, Write, NotebookEdit."""
        _sync_bundled(db)

        row = manager.get_by_name("require-task-before-edit")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        assert body.effect.type == "block"
        assert set(body.effect.tools) == {"Edit", "Write", "NotebookEdit"}

    def test_when_checks_task_claimed_and_plan_mode(self, db, manager) -> None:
        """Should check task_claimed and plan_mode."""
        _sync_bundled(db)

        row = manager.get_by_name("require-task-before-edit")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "task_claimed" in body.when
        assert "plan_mode" in body.when


class TestRequireCommitBeforeClose:
    """Verify require-commit-before-close requires commit before close_task."""

    def test_blocks_close_task_mcp(self, db, manager) -> None:
        """Should block gobby-tasks:close_task."""
        _sync_bundled(db)

        row = manager.get_by_name("require-commit-before-close")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        assert body.effect.type == "block"
        assert "gobby-tasks:close_task" in body.effect.mcp_tools

    def test_when_checks_commits_and_reasons(self, db, manager) -> None:
        """Should check task_has_commits and special close reasons."""
        _sync_bundled(db)

        row = manager.get_by_name("require-commit-before-close")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "task_has_commits" in body.when
        assert "commit_sha" in body.when


class TestBlockSkipValidationWithCommit:
    """Verify block-skip-validation-with-commit blocks skip_validation."""

    def test_blocks_close_task_mcp(self, db, manager) -> None:
        """Should block gobby-tasks:close_task."""
        _sync_bundled(db)

        row = manager.get_by_name("block-skip-validation-with-commit")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        assert body.effect.type == "block"
        assert "gobby-tasks:close_task" in body.effect.mcp_tools

    def test_when_checks_skip_validation(self, db, manager) -> None:
        """Should check skip_validation flag."""
        _sync_bundled(db)

        row = manager.get_by_name("block-skip-validation-with-commit")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "skip_validation" in body.when


class TestBlockAskDuringStopCompliance:
    """Verify block-ask-during-stop-compliance blocks questions during stop."""

    def test_blocks_ask_user_question(self, db, manager) -> None:
        """Should block AskUserQuestion."""
        _sync_bundled(db)

        row = manager.get_by_name("block-ask-during-stop-compliance")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        assert body.effect.type == "block"
        assert "AskUserQuestion" in body.effect.tools

    def test_when_checks_stop_attempts_and_task(self, db, manager) -> None:
        """Should check stop_attempts and task_claimed."""
        _sync_bundled(db)

        row = manager.get_by_name("block-ask-during-stop-compliance")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "stop_attempts" in body.when
        assert "task_claimed" in body.when


class TestTrackTaskClaim:
    """Verify track-task-claim sets task_claimed on claim."""

    def test_sets_task_claimed_true(self, db, manager) -> None:
        """Should set task_claimed to true."""
        _sync_bundled(db)

        row = manager.get_by_name("track-task-claim")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        assert body.effect.type == "set_variable"
        assert body.effect.variable == "task_claimed"
        assert body.effect.value is True

    def test_when_matches_claim_and_create(self, db, manager) -> None:
        """Should fire on claim_task and create_task."""
        _sync_bundled(db)

        row = manager.get_by_name("track-task-claim")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "claim_task" in body.when
        assert "create_task" in body.when


class TestTrackTaskRelease:
    """Verify track-task-release clears task_claimed on close."""

    def test_sets_task_claimed_false(self, db, manager) -> None:
        """Should set task_claimed to false."""
        _sync_bundled(db)

        row = manager.get_by_name("track-task-release")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        assert body.effect.type == "set_variable"
        assert body.effect.variable == "task_claimed"
        assert body.effect.value is False

    def test_when_matches_close_and_release(self, db, manager) -> None:
        """Should fire on close_task and release_task."""
        _sync_bundled(db)

        row = manager.get_by_name("track-task-release")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "close_task" in body.when
        assert "release_task" in body.when
