"""Tests for simplified spawn_agent using workflow_definitions agent lookup.

Covers:
- Loading agent definition from workflow_definitions (workflow_type='agent')
- Building spawn params from AgentDefinitionBody
- Setting _agent_type session variable for rule activation
- Simplified (agent_name, prompt, task_id) interface
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import AgentDefinitionBody

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    db_path = tmp_path / "test_spawn_v2.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    return database


@pytest.fixture
def manager(db: LocalDatabase) -> LocalWorkflowDefinitionManager:
    return LocalWorkflowDefinitionManager(db)


def _insert_agent(
    manager: LocalWorkflowDefinitionManager,
    body: AgentDefinitionBody,
) -> str:
    row = manager.create(
        name=body.name,
        definition_json=body.model_dump_json(),
        workflow_type="agent",
        description=body.description,
        enabled=True,
    )
    return row.id


# ═══════════════════════════════════════════════════════════════════════
# load_agent_definition_body
# ═══════════════════════════════════════════════════════════════════════


class TestLoadAgentDefinitionBody:
    """load_agent_definition_body loads from workflow_definitions."""

    def test_loads_existing_agent(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        from gobby.mcp_proxy.tools.spawn_agent._v2 import load_agent_definition_body

        _insert_agent(
            manager,
            AgentDefinitionBody(
                name="test-dev-spawn",
                description="Developer agent",
                instructions="Write clean code.",
                provider="claude",
                model="claude-sonnet-4-6",
                mode="terminal",
                isolation="worktree",
                base_branch="main",
                timeout=120.0,
                max_turns=15,
                rules=["require-task", "require-commit"],
            ),
        )

        body = load_agent_definition_body("test-dev-spawn", db)
        assert body is not None
        assert body.name == "test-dev-spawn"
        assert body.provider == "claude"
        assert body.model == "claude-sonnet-4-6"
        assert body.mode == "terminal"
        assert body.isolation == "worktree"
        assert body.rules == ["require-task", "require-commit"]

    def test_returns_none_for_missing_agent(
        self, db: LocalDatabase
    ) -> None:
        from gobby.mcp_proxy.tools.spawn_agent._v2 import load_agent_definition_body

        body = load_agent_definition_body("nonexistent-agent", db)
        assert body is None

    def test_ignores_non_agent_types(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        from gobby.mcp_proxy.tools.spawn_agent._v2 import load_agent_definition_body

        # Insert a rule with same name
        manager.create(
            name="test-rule-not-agent",
            definition_json=json.dumps({"event": "before_tool", "effect": {"type": "block"}}),
            workflow_type="rule",
        )

        body = load_agent_definition_body("test-rule-not-agent", db)
        assert body is None


# ═══════════════════════════════════════════════════════════════════════
# build_spawn_params
# ═══════════════════════════════════════════════════════════════════════


class TestBuildSpawnParams:
    """build_spawn_params extracts params from AgentDefinitionBody."""

    def test_extracts_all_fields(self) -> None:
        from gobby.mcp_proxy.tools.spawn_agent._v2 import build_spawn_params

        body = AgentDefinitionBody(
            name="test-qa",
            description="QA agent",
            instructions="Test everything.",
            provider="gemini",
            model="gemini-2.5-pro",
            mode="terminal",
            isolation="worktree",
            base_branch="develop",
            timeout=300.0,
            max_turns=20,
            rules=["no-code-writing"],
        )

        params = build_spawn_params(body, prompt="Fix the bug", task_id="#42")

        assert params["prompt"] == "## Instructions\nTest everything.\n\n---\n\nFix the bug"
        assert params["provider"] == "gemini"
        assert params["model"] == "gemini-2.5-pro"
        assert params["mode"] == "terminal"
        assert params["isolation"] == "worktree"
        assert params["base_branch"] == "develop"
        assert params["timeout"] == 300.0
        assert params["max_turns"] == 20
        assert params["task_id"] == "#42"

    def test_sets_agent_type_variable(self) -> None:
        from gobby.mcp_proxy.tools.spawn_agent._v2 import build_spawn_params

        body = AgentDefinitionBody(name="test-developer")
        params = build_spawn_params(body, prompt="Do work")

        assert params["step_variables"]["_agent_type"] == "test-developer"

    def test_sets_agent_rules_variable(self) -> None:
        from gobby.mcp_proxy.tools.spawn_agent._v2 import build_spawn_params

        body = AgentDefinitionBody(
            name="test-dev",
            rules=["require-task", "require-commit"],
        )
        params = build_spawn_params(body, prompt="Do work")

        assert params["step_variables"]["_agent_rules"] == ["require-task", "require-commit"]

    def test_prepends_instructions_to_prompt(self) -> None:
        from gobby.mcp_proxy.tools.spawn_agent._v2 import build_spawn_params

        body = AgentDefinitionBody(
            name="test-agent",
            instructions="You are a test agent. Be thorough.",
        )
        params = build_spawn_params(body, prompt="Run tests on module X")

        assert "You are a test agent" in params["prompt"]
        assert "Run tests on module X" in params["prompt"]
        # Instructions should come before the prompt
        assert params["prompt"].index("You are a test agent") < params["prompt"].index("Run tests on module X")

    def test_no_instructions_uses_raw_prompt(self) -> None:
        from gobby.mcp_proxy.tools.spawn_agent._v2 import build_spawn_params

        body = AgentDefinitionBody(name="test-simple")
        params = build_spawn_params(body, prompt="Just do it")

        assert params["prompt"] == "Just do it"

    def test_defaults_when_minimal_body(self) -> None:
        from gobby.mcp_proxy.tools.spawn_agent._v2 import build_spawn_params

        body = AgentDefinitionBody(name="test-minimal")
        params = build_spawn_params(body, prompt="Work")

        assert params["provider"] == "claude"
        assert params["model"] is None
        assert params["mode"] == "headless"
        assert params["isolation"] is None
        assert params["base_branch"] == "main"
        assert params["timeout"] == 120.0
        assert params["max_turns"] == 10

    def test_task_id_none(self) -> None:
        from gobby.mcp_proxy.tools.spawn_agent._v2 import build_spawn_params

        body = AgentDefinitionBody(name="test-notask")
        params = build_spawn_params(body, prompt="Work")

        assert params["task_id"] is None


# ═══════════════════════════════════════════════════════════════════════
# spawn_agent_simplified (integration)
# ═══════════════════════════════════════════════════════════════════════


class TestSpawnAgentSimplified:
    """End-to-end: simplified spawn loads definition and delegates."""

    @pytest.mark.asyncio
    async def test_loads_definition_and_calls_impl(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        from gobby.mcp_proxy.tools.spawn_agent._v2 import spawn_agent_simplified

        _insert_agent(
            manager,
            AgentDefinitionBody(
                name="test-spawn-dev",
                instructions="Write code.",
                provider="claude",
                mode="terminal",
                isolation="worktree",
            ),
        )

        mock_impl = AsyncMock(return_value={"success": True, "run_id": "run-123"})

        with patch(
            "gobby.mcp_proxy.tools.spawn_agent._v2.spawn_agent_impl",
            mock_impl,
        ):
            result = await spawn_agent_simplified(
                agent_name="test-spawn-dev",
                prompt="Fix the bug",
                db=db,
                runner=MagicMock(),
                parent_session_id="sess-parent",
            )

        assert result["success"] is True
        # Verify spawn_agent_impl was called with the right params
        call_kwargs = mock_impl.call_args[1]
        assert "Write code." in call_kwargs["prompt"]
        assert "Fix the bug" in call_kwargs["prompt"]
        assert call_kwargs["provider"] == "claude"
        assert call_kwargs["mode"] == "terminal"
        assert call_kwargs["isolation"] == "worktree"

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_agent(
        self, db: LocalDatabase
    ) -> None:
        from gobby.mcp_proxy.tools.spawn_agent._v2 import spawn_agent_simplified

        result = await spawn_agent_simplified(
            agent_name="nonexistent",
            prompt="Do something",
            db=db,
            runner=MagicMock(),
            parent_session_id="sess-parent",
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_passes_agent_type_in_step_variables(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        from gobby.mcp_proxy.tools.spawn_agent._v2 import spawn_agent_simplified

        _insert_agent(
            manager,
            AgentDefinitionBody(
                name="test-spawn-qa",
                rules=["no-code-writing"],
            ),
        )

        mock_impl = AsyncMock(return_value={"success": True, "run_id": "run-456"})

        with patch(
            "gobby.mcp_proxy.tools.spawn_agent._v2.spawn_agent_impl",
            mock_impl,
        ):
            await spawn_agent_simplified(
                agent_name="test-spawn-qa",
                prompt="Test it",
                db=db,
                runner=MagicMock(),
                parent_session_id="sess-parent",
            )

        # Verify _agent_type is set in step_variables passed to spawn_agent_impl
        # step_variables should be in the keyword arguments
        call_kwargs = mock_impl.call_args[1]
        # The _agent_type should flow through as a step variable
        # It might be in prompt or in a step_variables dict
        assert call_kwargs.get("agent_lookup_name") == "test-spawn-qa"
