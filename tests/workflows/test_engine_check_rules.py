"""Tests for check_rules resolution in WorkflowEngine.

Covers: check_rules resolves file-local names, check_rules resolves DB names
with tier precedence, unknown rule name logs warning and is skipped,
resolved rules block tools correctly, check_rules + inline rules both apply.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.storage.workflow_audit import WorkflowAuditManager
from gobby.workflows.definitions import (
    RuleDefinition,
    WorkflowDefinition,
    WorkflowRule,
    WorkflowState,
    WorkflowStep,
)
from gobby.workflows.engine import WorkflowEngine
from gobby.workflows.evaluator import ConditionEvaluator
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

pytestmark = pytest.mark.unit


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_loader():
    return MagicMock(spec=WorkflowLoader)


@pytest.fixture
def mock_state_manager():
    return MagicMock(spec=WorkflowStateManager)


@pytest.fixture
def mock_action_executor():
    executor = AsyncMock()
    executor.db = MagicMock()
    executor.session_manager = MagicMock()
    executor.template_engine = MagicMock()
    executor.llm_service = MagicMock()
    executor.transcript_processor = MagicMock()
    executor.config = MagicMock()
    executor.memory_manager = MagicMock()
    executor.memory_sync_manager = MagicMock()
    executor.session_task_manager = MagicMock()
    executor.task_sync_manager = MagicMock()
    executor.pipeline_executor = MagicMock()
    executor.task_manager = MagicMock()
    executor.workflow_loader = MagicMock()
    executor.skill_manager = MagicMock()
    executor.tool_proxy_getter = MagicMock()
    return executor


@pytest.fixture
def mock_evaluator():
    evaluator = MagicMock(spec=ConditionEvaluator)
    evaluator.evaluate.return_value = False
    evaluator.check_exit_conditions.return_value = False
    return evaluator


@pytest.fixture
def mock_audit_manager():
    return MagicMock(spec=WorkflowAuditManager)


@pytest.fixture
def mock_rule_store():
    store = MagicMock()
    store.get_rule.return_value = None
    return store


@pytest.fixture
def engine(
    mock_loader,
    mock_state_manager,
    mock_action_executor,
    mock_evaluator,
    mock_audit_manager,
    mock_rule_store,
):
    return WorkflowEngine(
        mock_loader,
        mock_state_manager,
        mock_action_executor,
        evaluator=mock_evaluator,
        audit_manager=mock_audit_manager,
        rule_store=mock_rule_store,
    )


# =============================================================================
# Helpers
# =============================================================================


def _make_event(tool_name: str = "Edit", **data_overrides) -> HookEvent:
    """Create a BEFORE_TOOL event."""
    data: dict = {"tool_name": tool_name}
    data.update(data_overrides)
    return HookEvent(
        event_type=HookEventType.BEFORE_TOOL,
        session_id="sess1",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data=data,
        metadata={"_platform_session_id": "sess1"},
    )


def _make_step(
    check_rules: list[str] | None = None,
    rules: list[WorkflowRule] | None = None,
    **kwargs,
) -> MagicMock:
    """Create a mock WorkflowStep with sensible defaults."""
    step = MagicMock(spec=WorkflowStep)
    step.name = "work"
    step.on_enter = []
    step.on_exit = []
    step.status_message = None
    step.blocked_tools = []
    step.allowed_tools = "all"
    step.allowed_mcp_tools = "all"
    step.blocked_mcp_tools = []
    step.rules = rules or []
    step.check_rules = check_rules or []
    step.transitions = []
    step.exit_conditions = []
    step.on_mcp_success = []
    step.on_mcp_error = []
    for k, v in kwargs.items():
        setattr(step, k, v)
    return step


def _make_workflow(
    step: MagicMock,
    rule_definitions: dict[str, RuleDefinition] | None = None,
) -> MagicMock:
    """Create a mock WorkflowDefinition with rule_definitions."""
    workflow = MagicMock(spec=WorkflowDefinition)
    workflow.type = "step"
    workflow.name = "test-workflow"
    workflow.rule_definitions = rule_definitions or {}
    workflow.get_step.return_value = step
    return workflow


def _make_state(**kwargs) -> WorkflowState:
    """Create a WorkflowState with sensible defaults."""
    defaults = {
        "session_id": "sess1",
        "workflow_name": "test-workflow",
        "step": "work",
        "step_entered_at": datetime.now(UTC),
        "variables": {},
    }
    defaults.update(kwargs)
    return WorkflowState(**defaults)


# =============================================================================
# _resolve_check_rules (unit tests)
# =============================================================================


class TestResolveCheckRules:
    """Direct tests for _resolve_check_rules method."""

    def test_resolves_file_local_name(self, engine, mock_rule_store):
        """check_rules names found in workflow.rule_definitions are resolved."""
        rule_def = RuleDefinition(
            tools=["Edit", "Write"],
            reason="Claim a task first",
            action="block",
        )
        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.rule_definitions = {"require_task": rule_def}

        result = engine._resolve_check_rules(["require_task"], workflow)

        assert len(result) == 1
        assert result[0] is rule_def
        mock_rule_store.get_rule.assert_not_called()

    def test_resolves_db_name(self, engine, mock_rule_store):
        """check_rules names not in workflow fall back to DB lookup."""
        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.rule_definitions = {}

        mock_rule_store.get_rule.return_value = {
            "name": "no_push",
            "tier": "bundled",
            "definition": {
                "tools": ["Bash"],
                "command_pattern": r"git\s+push",
                "reason": "No pushing allowed",
                "action": "block",
            },
        }

        result = engine._resolve_check_rules(["no_push"], workflow)

        assert len(result) == 1
        assert result[0].tools == ["Bash"]
        assert result[0].reason == "No pushing allowed"
        mock_rule_store.get_rule.assert_called_once_with("no_push", project_id=None)

    def test_file_local_overrides_db(self, engine, mock_rule_store):
        """File-local rule_definitions take precedence over DB rules."""
        local_rule = RuleDefinition(
            tools=["Edit"],
            reason="Local override",
            action="warn",
        )
        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.rule_definitions = {"shared_rule": local_rule}

        result = engine._resolve_check_rules(["shared_rule"], workflow)

        assert len(result) == 1
        assert result[0].reason == "Local override"
        mock_rule_store.get_rule.assert_not_called()

    def test_unknown_name_skipped(self, engine, mock_rule_store):
        """Unknown rule names are skipped with a warning."""
        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.rule_definitions = {}
        mock_rule_store.get_rule.return_value = None

        result = engine._resolve_check_rules(["nonexistent"], workflow)

        assert len(result) == 0

    def test_db_tier_precedence_passes_project_id(self, engine, mock_rule_store):
        """DB lookup passes project_id for tier precedence resolution."""
        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.rule_definitions = {}

        mock_rule_store.get_rule.return_value = {
            "name": "custom_rule",
            "tier": "project",
            "definition": {
                "tools": ["Bash"],
                "reason": "Project-level rule",
                "action": "block",
            },
        }

        result = engine._resolve_check_rules(
            ["custom_rule"], workflow, project_id="proj-123"
        )

        assert len(result) == 1
        mock_rule_store.get_rule.assert_called_once_with(
            "custom_rule", project_id="proj-123"
        )

    def test_multiple_rules_resolved_in_order(self, engine, mock_rule_store):
        """Multiple check_rules names are all resolved in order."""
        rule1 = RuleDefinition(tools=["Edit"], reason="Rule 1", action="block")
        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.rule_definitions = {"local_rule": rule1}

        mock_rule_store.get_rule.return_value = {
            "name": "db_rule",
            "tier": "bundled",
            "definition": {
                "tools": ["Bash"],
                "reason": "Rule 2",
                "action": "block",
            },
        }

        result = engine._resolve_check_rules(["local_rule", "db_rule"], workflow)

        assert len(result) == 2
        assert result[0].reason == "Rule 1"
        assert result[1].reason == "Rule 2"

    def test_invalid_db_definition_skipped(self, engine, mock_rule_store):
        """Invalid rule definitions from DB are skipped gracefully."""
        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.rule_definitions = {}

        # Missing required 'reason' field
        mock_rule_store.get_rule.return_value = {
            "name": "bad_rule",
            "tier": "bundled",
            "definition": {
                "tools": ["Bash"],
                # 'reason' is required but missing
            },
        }

        result = engine._resolve_check_rules(["bad_rule"], workflow)

        assert len(result) == 0

    def test_no_rule_store_skips_db_lookup(self, mock_loader, mock_state_manager, mock_action_executor, mock_evaluator):
        """When rule_store is None and no DB available, DB lookup is skipped."""
        mock_action_executor.db = None
        engine = WorkflowEngine(
            mock_loader,
            mock_state_manager,
            mock_action_executor,
            evaluator=mock_evaluator,
            rule_store=None,
        )
        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.rule_definitions = {}

        result = engine._resolve_check_rules(["unknown"], workflow)

        assert len(result) == 0


# =============================================================================
# check_rules in handle_event (integration tests)
# =============================================================================


@pytest.mark.asyncio
class TestCheckRulesInHandleEvent:
    """Tests for check_rules evaluation in handle_event BEFORE_TOOL path."""

    async def test_blocks_matching_tool(
        self, engine, mock_state_manager, mock_loader,
    ):
        """Resolved check_rules should block matching tools."""
        state = _make_state(variables={"task_claimed": False})
        mock_state_manager.get_state.return_value = state

        rule_def = RuleDefinition(
            tools=["Edit", "Write"],
            when="not task_claimed",
            reason="Claim a task before editing.",
            action="block",
        )
        step = _make_step(check_rules=["require_task"])
        workflow = _make_workflow(step, rule_definitions={"require_task": rule_def})
        mock_loader.load_workflow = AsyncMock(return_value=workflow)

        event = _make_event(tool_name="Edit")
        response = await engine.handle_event(event)

        assert response.decision == "block"
        assert "Claim a task" in response.reason

    async def test_allows_non_matching_tool(
        self, engine, mock_state_manager, mock_loader,
    ):
        """check_rules should allow tools not listed in the rule."""
        state = _make_state()
        mock_state_manager.get_state.return_value = state

        rule_def = RuleDefinition(
            tools=["Edit", "Write"],
            reason="Claim a task first.",
            action="block",
        )
        step = _make_step(check_rules=["require_task"])
        workflow = _make_workflow(step, rule_definitions={"require_task": rule_def})
        mock_loader.load_workflow = AsyncMock(return_value=workflow)

        # Read is not in the rule's tools list
        event = _make_event(tool_name="Read")
        response = await engine.handle_event(event)

        assert response.decision == "allow"

    async def test_condition_prevents_block(
        self, engine, mock_state_manager, mock_loader,
    ):
        """check_rules with when condition should not block when condition is false."""
        state = _make_state(variables={"task_claimed": True})
        mock_state_manager.get_state.return_value = state

        rule_def = RuleDefinition(
            tools=["Edit", "Write"],
            when="not task_claimed",
            reason="Claim a task first.",
            action="block",
        )
        step = _make_step(check_rules=["require_task"])
        workflow = _make_workflow(step, rule_definitions={"require_task": rule_def})
        mock_loader.load_workflow = AsyncMock(return_value=workflow)

        event = _make_event(tool_name="Edit")
        response = await engine.handle_event(event)

        assert response.decision == "allow"

    async def test_inline_rules_and_check_rules_both_apply(
        self, engine, mock_state_manager, mock_loader, mock_evaluator,
    ):
        """Both inline rules and check_rules should be evaluated."""
        state = _make_state()
        mock_state_manager.get_state.return_value = state

        # Inline rule that blocks Read
        inline_rule = WorkflowRule(
            name="no_read",
            when="True",
            action="block",
            message="Read is blocked by inline rule.",
        )
        # Named rule that blocks Edit
        named_rule = RuleDefinition(
            tools=["Edit"],
            reason="Edit is blocked by named rule.",
            action="block",
        )
        step = _make_step(
            check_rules=["no_edit"],
            rules=[inline_rule],
        )
        workflow = _make_workflow(step, rule_definitions={"no_edit": named_rule})
        mock_loader.load_workflow = AsyncMock(return_value=workflow)

        # Test 1: inline rule blocks Read when evaluator returns True
        mock_evaluator.evaluate.return_value = True
        event = _make_event(tool_name="Read")
        response = await engine.handle_event(event)
        assert response.decision == "block"
        assert "Read is blocked by inline rule" in response.reason

        # Test 2: named rule blocks Edit (inline rule doesn't match Edit,
        # so evaluator returning False for inline lets check_rules handle it)
        mock_evaluator.evaluate.return_value = False
        event = _make_event(tool_name="Edit")
        response = await engine.handle_event(event)
        assert response.decision == "block"
        assert "Edit is blocked by named rule" in response.reason

    async def test_check_rules_from_db(
        self, engine, mock_state_manager, mock_loader, mock_rule_store,
    ):
        """check_rules should resolve names from DB when not in workflow."""
        state = _make_state()
        mock_state_manager.get_state.return_value = state

        step = _make_step(check_rules=["no_push"])
        workflow = _make_workflow(step, rule_definitions={})
        mock_loader.load_workflow = AsyncMock(return_value=workflow)

        mock_rule_store.get_rule.return_value = {
            "name": "no_push",
            "tier": "bundled",
            "definition": {
                "tools": ["Bash"],
                "command_pattern": r"git\s+push",
                "reason": "Do not push to remote.",
                "action": "block",
            },
        }

        event = _make_event(
            tool_name="Bash",
            tool_input={"command": "git push origin main"},
        )
        response = await engine.handle_event(event)

        assert response.decision == "block"
        assert "Do not push" in response.reason

    async def test_command_pattern_no_match(
        self, engine, mock_state_manager, mock_loader, mock_rule_store,
    ):
        """Command pattern rules should not block non-matching commands."""
        state = _make_state()
        mock_state_manager.get_state.return_value = state

        step = _make_step(check_rules=["no_push"])
        workflow = _make_workflow(step, rule_definitions={})
        mock_loader.load_workflow = AsyncMock(return_value=workflow)

        mock_rule_store.get_rule.return_value = {
            "name": "no_push",
            "tier": "bundled",
            "definition": {
                "tools": ["Bash"],
                "command_pattern": r"git\s+push",
                "reason": "Do not push to remote.",
                "action": "block",
            },
        }

        event = _make_event(
            tool_name="Bash",
            tool_input={"command": "git status"},
        )
        response = await engine.handle_event(event)

        assert response.decision == "allow"

    async def test_empty_check_rules_no_effect(
        self, engine, mock_state_manager, mock_loader,
    ):
        """Empty check_rules list should have no effect."""
        state = _make_state()
        mock_state_manager.get_state.return_value = state

        step = _make_step(check_rules=[])
        workflow = _make_workflow(step, rule_definitions={})
        mock_loader.load_workflow = AsyncMock(return_value=workflow)

        event = _make_event(tool_name="Edit")
        response = await engine.handle_event(event)

        assert response.decision == "allow"

    async def test_unknown_check_rule_skipped(
        self, engine, mock_state_manager, mock_loader, mock_rule_store,
    ):
        """Unknown check_rules names should be skipped without blocking."""
        state = _make_state()
        mock_state_manager.get_state.return_value = state

        step = _make_step(check_rules=["nonexistent_rule"])
        workflow = _make_workflow(step, rule_definitions={})
        mock_loader.load_workflow = AsyncMock(return_value=workflow)
        mock_rule_store.get_rule.return_value = None

        event = _make_event(tool_name="Edit")
        response = await engine.handle_event(event)

        assert response.decision == "allow"

    async def test_non_block_action_skipped(
        self, engine, mock_state_manager, mock_loader,
    ):
        """Rules with action != 'block' should not be passed to block_tools."""
        state = _make_state()
        mock_state_manager.get_state.return_value = state

        warn_rule = RuleDefinition(
            tools=["Edit"],
            reason="This is a warning only.",
            action="warn",
        )
        step = _make_step(check_rules=["warn_rule"])
        workflow = _make_workflow(step, rule_definitions={"warn_rule": warn_rule})
        mock_loader.load_workflow = AsyncMock(return_value=workflow)

        event = _make_event(tool_name="Edit")
        response = await engine.handle_event(event)

        assert response.decision == "allow"
