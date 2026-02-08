"""Tests for agent spawn dry-run evaluator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.agents.definitions import AgentDefinition, WorkflowSpec
from gobby.agents.dry_run import SpawnEvaluation, evaluate_spawn
from gobby.workflows.definitions import WorkflowDefinition, WorkflowStep, WorkflowTransition
from gobby.workflows.dry_run import WorkflowEvaluation

pytestmark = pytest.mark.unit


def _make_agent(
    name: str = "test-agent",
    mode: str = "headless",
    provider: str = "claude",
    terminal: str = "auto",
    isolation: str | None = None,
    workflows: dict[str, WorkflowSpec] | None = None,
    default_workflow: str | None = None,
    branch_prefix: str | None = None,
    base_branch: str = "main",
) -> AgentDefinition:
    """Helper to create an AgentDefinition."""
    return AgentDefinition(
        name=name,
        mode=mode,
        provider=provider,
        terminal=terminal,
        isolation=isolation,
        workflows=workflows,
        default_workflow=default_workflow,
        branch_prefix=branch_prefix,
        base_branch=base_branch,
    )


@pytest.fixture
def mock_agent_loader() -> MagicMock:
    loader = MagicMock()
    loader.load.return_value = None
    return loader


@pytest.fixture
def mock_workflow_loader() -> MagicMock:
    loader = MagicMock()
    loader.load_workflow = AsyncMock(return_value=None)
    loader.validate_workflow_for_agent = AsyncMock(return_value=(True, None))
    return loader


@pytest.fixture
def mock_runner() -> MagicMock:
    runner = MagicMock()
    runner.can_spawn.return_value = (True, "depth OK (0/3)", 0)
    return runner


@pytest.fixture
def mock_state_manager() -> MagicMock:
    return MagicMock()


class TestAgentNotFound:
    @pytest.mark.asyncio
    async def test_agent_not_found(self, mock_agent_loader: MagicMock) -> None:
        """AGENT_NOT_FOUND error, can_spawn=False."""
        mock_agent_loader.load.return_value = None

        result = await evaluate_spawn(
            agent="nonexistent",
            agent_loader=mock_agent_loader,
        )

        assert result.can_spawn is False
        assert result.agent_found is False
        assert len(result.errors) == 1
        assert result.errors[0].code == "AGENT_NOT_FOUND"


class TestWorkflowKeyMismatch:
    @pytest.mark.asyncio
    async def test_workflow_key_mismatch(
        self, mock_agent_loader: MagicMock, mock_workflow_loader: MagicMock,
    ) -> None:
        """WORKFLOW_KEY_MISMATCH error — the original bug."""
        agent_def = _make_agent(
            workflows={"worker": WorkflowSpec(file="worker.yaml")},
            default_workflow="box",  # Not in workflows map!
        )
        mock_agent_loader.load.return_value = agent_def

        result = await evaluate_spawn(
            agent="meeseeks",
            agent_loader=mock_agent_loader,
            workflow_loader=mock_workflow_loader,
        )

        assert result.can_spawn is False
        mismatch_items = [i for i in result.errors if i.code == "WORKFLOW_KEY_MISMATCH"]
        assert len(mismatch_items) == 1
        assert "box" in mismatch_items[0].message
        assert "worker" in mismatch_items[0].detail["available_keys"]

    @pytest.mark.asyncio
    async def test_workflow_key_matches(
        self, mock_agent_loader: MagicMock, mock_workflow_loader: MagicMock,
    ) -> None:
        """Happy path — default_workflow is in workflows map."""
        agent_def = _make_agent(
            workflows={
                "box": WorkflowSpec(file="meeseeks-box.yaml"),
                "worker": WorkflowSpec(file="worker.yaml"),
            },
            default_workflow="box",
        )
        mock_agent_loader.load.return_value = agent_def

        # Mock workflow evaluation to return valid
        mock_workflow_loader.load_workflow.return_value = WorkflowDefinition(
            name="meeseeks-box",
            steps=[WorkflowStep(name="start")],
        )

        result = await evaluate_spawn(
            agent="meeseeks",
            agent_loader=mock_agent_loader,
            workflow_loader=mock_workflow_loader,
        )

        mismatch_items = [i for i in result.errors if i.code == "WORKFLOW_KEY_MISMATCH"]
        assert len(mismatch_items) == 0


class TestOrchestratorEnforcement:
    @pytest.mark.asyncio
    async def test_orchestrator_not_evaluated_no_session(
        self, mock_agent_loader: MagicMock,
    ) -> None:
        """Reports not-evaluated when no parent session provided."""
        agent_def = _make_agent(
            workflows={
                "box": WorkflowSpec(file="box.yaml", mode="self"),
                "worker": WorkflowSpec(file="worker.yaml"),
            },
            default_workflow="box",
        )
        mock_agent_loader.load.return_value = agent_def

        result = await evaluate_spawn(
            agent="meeseeks",
            workflow="worker",
            agent_loader=mock_agent_loader,
        )

        orch_items = [i for i in result.items if i.code == "ORCHESTRATOR_NOT_EVALUATED"]
        assert len(orch_items) == 1


class TestIsolation:
    @pytest.mark.asyncio
    async def test_isolation_deps_missing_worktree(
        self, mock_agent_loader: MagicMock,
    ) -> None:
        """ISOLATION_DEPS_MISSING for worktree mode without deps."""
        agent_def = _make_agent(isolation="worktree")
        mock_agent_loader.load.return_value = agent_def

        result = await evaluate_spawn(
            agent="test",
            agent_loader=mock_agent_loader,
            git_manager=None,
            worktree_storage=None,
        )

        dep_items = [i for i in result.warnings if i.code == "ISOLATION_DEPS_MISSING"]
        assert len(dep_items) == 1
        assert "worktree" in dep_items[0].message.lower()

    @pytest.mark.asyncio
    async def test_isolation_deps_missing_clone(
        self, mock_agent_loader: MagicMock,
    ) -> None:
        """ISOLATION_DEPS_MISSING for clone mode without deps."""
        agent_def = _make_agent(isolation="clone")
        mock_agent_loader.load.return_value = agent_def

        result = await evaluate_spawn(
            agent="test",
            agent_loader=mock_agent_loader,
            clone_manager=None,
            clone_storage=None,
        )

        dep_items = [i for i in result.warnings if i.code == "ISOLATION_DEPS_MISSING"]
        assert len(dep_items) == 1
        assert "clone" in dep_items[0].message.lower()


class TestRuntimeEnvironment:
    @pytest.mark.asyncio
    async def test_spawn_depth_exceeded(
        self, mock_agent_loader: MagicMock, mock_runner: MagicMock,
    ) -> None:
        """SPAWN_DEPTH_EXCEEDED when can_spawn returns False."""
        agent_def = _make_agent()
        mock_agent_loader.load.return_value = agent_def
        mock_runner.can_spawn.return_value = (False, "Max depth 3 exceeded", 4)

        result = await evaluate_spawn(
            agent="test",
            parent_session_id="sess-123",
            agent_loader=mock_agent_loader,
            runner=mock_runner,
        )

        assert result.can_spawn is False
        depth_items = [i for i in result.errors if i.code == "SPAWN_DEPTH_EXCEEDED"]
        assert len(depth_items) == 1

    @pytest.mark.asyncio
    async def test_self_mode_workflow_conflict(
        self,
        mock_agent_loader: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """SELF_MODE_WORKFLOW_CONFLICT when parent already has active workflow."""
        agent_def = _make_agent(
            mode="self",
            workflows={"box": WorkflowSpec(file="box.yaml", mode="self")},
            default_workflow="box",
        )
        mock_agent_loader.load.return_value = agent_def

        parent_state = MagicMock()
        parent_state.workflow_name = "existing-workflow"
        mock_state_manager.get_state.return_value = parent_state

        result = await evaluate_spawn(
            agent="test",
            parent_session_id="sess-123",
            agent_loader=mock_agent_loader,
            state_manager=mock_state_manager,
        )

        conflict_items = [i for i in result.warnings if i.code == "SELF_MODE_WORKFLOW_CONFLICT"]
        assert len(conflict_items) == 1


class TestWorkflowEvaluation:
    @pytest.mark.asyncio
    async def test_workflow_eval_embedded(
        self,
        mock_agent_loader: MagicMock,
        mock_workflow_loader: MagicMock,
    ) -> None:
        """workflow_evaluation populated with structural results."""
        agent_def = _make_agent(
            workflows={"box": WorkflowSpec(file="meeseeks-box.yaml")},
            default_workflow="box",
        )
        mock_agent_loader.load.return_value = agent_def

        # Mock workflow loading for evaluation
        wf_definition = WorkflowDefinition(
            name="meeseeks-box",
            steps=[
                WorkflowStep(
                    name="start",
                    transitions=[WorkflowTransition(to="end", when="true")],
                ),
                WorkflowStep(name="end"),
            ],
        )
        mock_workflow_loader.load_workflow.return_value = wf_definition

        result = await evaluate_spawn(
            agent="meeseeks",
            agent_loader=mock_agent_loader,
            workflow_loader=mock_workflow_loader,
        )

        assert result.workflow_evaluation is not None
        assert result.workflow_evaluation.valid is True
        assert len(result.workflow_evaluation.step_trace) == 2

    @pytest.mark.asyncio
    async def test_workflow_invalid_for_agent(
        self,
        mock_agent_loader: MagicMock,
        mock_workflow_loader: MagicMock,
    ) -> None:
        """WORKFLOW_INVALID_FOR_AGENT when lifecycle workflow used for agent."""
        agent_def = _make_agent(
            workflows={"lc": WorkflowSpec(file="lifecycle.yaml")},
            default_workflow="lc",
        )
        mock_agent_loader.load.return_value = agent_def
        mock_workflow_loader.validate_workflow_for_agent.return_value = (
            False, "Cannot use lifecycle workflow"
        )

        result = await evaluate_spawn(
            agent="test",
            agent_loader=mock_agent_loader,
            workflow_loader=mock_workflow_loader,
        )

        assert result.can_spawn is False
        invalid_items = [i for i in result.errors if i.code == "WORKFLOW_INVALID_FOR_AGENT"]
        assert len(invalid_items) == 1


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_full_happy_path(
        self,
        mock_agent_loader: MagicMock,
        mock_workflow_loader: MagicMock,
        mock_runner: MagicMock,
    ) -> None:
        """All layers pass, can_spawn=True."""
        agent_def = _make_agent(
            workflows={"worker": WorkflowSpec(file="worker.yaml")},
            default_workflow="worker",
        )
        mock_agent_loader.load.return_value = agent_def

        wf_definition = WorkflowDefinition(
            name="worker",
            steps=[
                WorkflowStep(
                    name="work",
                    transitions=[WorkflowTransition(to="done", when="true")],
                ),
                WorkflowStep(name="done"),
            ],
        )
        mock_workflow_loader.load_workflow.return_value = wf_definition

        result = await evaluate_spawn(
            agent="test",
            parent_session_id="sess-123",
            agent_loader=mock_agent_loader,
            workflow_loader=mock_workflow_loader,
            runner=mock_runner,
        )

        assert result.can_spawn is True
        assert result.agent_found is True
        assert result.effective_workflow == "worker"
        assert len(result.errors) == 0


class TestToDict:
    def test_spawn_evaluation_to_dict(self) -> None:
        """SpawnEvaluation serializes correctly."""
        result = SpawnEvaluation(
            can_spawn=True,
            agent_name="test",
            agent_found=True,
            effective_provider="claude",
        )
        d = result.to_dict()
        assert d["can_spawn"] is True
        assert d["agent_name"] == "test"
        assert d["workflow_evaluation"] is None

    def test_spawn_evaluation_with_workflow_eval(self) -> None:
        """SpawnEvaluation with embedded workflow eval serializes correctly."""
        wf_eval = WorkflowEvaluation(valid=True, workflow_name="test", workflow_type="step")
        result = SpawnEvaluation(
            can_spawn=True,
            agent_name="test",
            workflow_evaluation=wf_eval,
        )
        d = result.to_dict()
        assert d["workflow_evaluation"] is not None
        assert d["workflow_evaluation"]["valid"] is True
