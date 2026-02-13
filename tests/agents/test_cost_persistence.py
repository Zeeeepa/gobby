"""Tests for cost persistence from internal agent runs.

When agents spawn via LiteLLMExecutor (headless/embedded modes), their CostInfo
should be persisted to the session's usage_total_cost_usd for budget tracking.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.agents.runner import AgentRunner
from gobby.agents.runner_models import AgentConfig, AgentRunContext
from gobby.llm.executor import AgentResult, CostInfo

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_db():
    """Create a mock database."""
    return MagicMock()


@pytest.fixture
def mock_session_storage():
    """Create a mock session storage."""
    storage = MagicMock()
    # Mock get() for parent session lookup
    parent_session = MagicMock()
    parent_session.id = "sess-parent"
    parent_session.agent_depth = 0
    parent_session.usage_total_cost_usd = 0.0
    storage.get.return_value = parent_session
    storage.update_status = MagicMock()
    storage.add_cost = MagicMock(return_value=True)
    return storage


@pytest.fixture
def mock_executor_with_cost():
    """Create a mock agent executor that returns cost info."""
    executor = MagicMock()
    executor.run = AsyncMock(
        return_value=AgentResult(
            output="Task completed",
            status="success",
            turns_used=2,
            tool_calls=[],
            cost_info=CostInfo(
                prompt_tokens=1000,
                completion_tokens=500,
                total_cost=0.05,
                model="anthropic/claude-sonnet-4-20250514",
            ),
        )
    )
    return executor


@pytest.fixture
def runner_with_cost(mock_db, mock_session_storage, mock_executor_with_cost):
    """Create an AgentRunner with mocked dependencies for cost testing."""
    return AgentRunner(
        db=mock_db,
        session_storage=mock_session_storage,
        executors={"claude": mock_executor_with_cost},
        max_agent_depth=2,
    )


class TestCostPersistence:
    """Tests for persisting CostInfo to session storage."""

    @pytest.mark.asyncio
    async def test_execute_run_persists_cost_info(self, runner_with_cost, mock_session_storage):
        """execute_run persists cost_info to session storage after completion."""
        mock_session = MagicMock()
        mock_session.id = "sess-child"
        mock_run = MagicMock()
        mock_run.id = "run-123"

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test task", provider="claude")

        result = await runner_with_cost.execute_run(context, config)

        assert result.status == "success"
        assert result.cost_info is not None
        assert result.cost_info.total_cost == 0.05

        # Verify add_cost was called with the child session's cost
        mock_session_storage.add_cost.assert_called_once_with("sess-child", 0.05)

    @pytest.mark.asyncio
    async def test_execute_run_no_cost_when_none(self, mock_db, mock_session_storage):
        """execute_run does not call add_cost when cost_info is None."""
        # Create executor that returns no cost info
        executor = MagicMock()
        executor.run = AsyncMock(
            return_value=AgentResult(
                output="Task completed",
                status="success",
                turns_used=2,
                tool_calls=[],
                cost_info=None,  # No cost info
            )
        )

        runner = AgentRunner(
            db=mock_db,
            session_storage=mock_session_storage,
            executors={"claude": executor},
            max_agent_depth=2,
        )

        mock_session = MagicMock()
        mock_session.id = "sess-child"
        mock_run = MagicMock()
        mock_run.id = "run-123"

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test task", provider="claude")

        result = await runner.execute_run(context, config)

        assert result.status == "success"
        # add_cost should NOT be called when cost_info is None
        mock_session_storage.add_cost.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_run_persists_cost_on_error(self, mock_db, mock_session_storage):
        """execute_run persists cost even when result status is error."""
        # Create executor that returns error with cost info
        executor = MagicMock()
        executor.run = AsyncMock(
            return_value=AgentResult(
                output="",
                status="error",
                error="Something went wrong",
                turns_used=1,
                tool_calls=[],
                cost_info=CostInfo(
                    prompt_tokens=500,
                    completion_tokens=100,
                    total_cost=0.02,
                    model="anthropic/claude-sonnet-4-20250514",
                ),
            )
        )

        runner = AgentRunner(
            db=mock_db,
            session_storage=mock_session_storage,
            executors={"claude": executor},
            max_agent_depth=2,
        )

        mock_session = MagicMock()
        mock_session.id = "sess-child"
        mock_run = MagicMock()
        mock_run.id = "run-123"

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test task", provider="claude")

        result = await runner.execute_run(context, config)

        assert result.status == "error"
        # Cost should still be persisted even on error
        mock_session_storage.add_cost.assert_called_once_with("sess-child", 0.02)

    @pytest.mark.asyncio
    async def test_execute_run_persists_cost_on_timeout(self, mock_db, mock_session_storage):
        """execute_run persists cost when result status is timeout."""
        # Create executor that returns timeout with cost info
        executor = MagicMock()
        executor.run = AsyncMock(
            return_value=AgentResult(
                output="Partial work done",
                status="timeout",
                turns_used=5,
                tool_calls=[],
                cost_info=CostInfo(
                    prompt_tokens=2000,
                    completion_tokens=1000,
                    total_cost=0.10,
                    model="anthropic/claude-sonnet-4-20250514",
                ),
            )
        )

        runner = AgentRunner(
            db=mock_db,
            session_storage=mock_session_storage,
            executors={"claude": executor},
            max_agent_depth=2,
        )

        mock_session = MagicMock()
        mock_session.id = "sess-child"
        mock_run = MagicMock()
        mock_run.id = "run-123"

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test task", provider="claude")

        result = await runner.execute_run(context, config)

        assert result.status == "timeout"
        # Cost should still be persisted on timeout
        mock_session_storage.add_cost.assert_called_once_with("sess-child", 0.10)

    @pytest.mark.asyncio
    async def test_execute_run_zero_cost_not_persisted(self, mock_db, mock_session_storage):
        """execute_run does not call add_cost when total_cost is zero."""
        # Create executor that returns cost_info with zero cost
        executor = MagicMock()
        executor.run = AsyncMock(
            return_value=AgentResult(
                output="Task completed",
                status="success",
                turns_used=2,
                tool_calls=[],
                cost_info=CostInfo(
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_cost=0.0,
                    model="",
                ),
            )
        )

        runner = AgentRunner(
            db=mock_db,
            session_storage=mock_session_storage,
            executors={"claude": executor},
            max_agent_depth=2,
        )

        mock_session = MagicMock()
        mock_session.id = "sess-child"
        mock_run = MagicMock()
        mock_run.id = "run-123"

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test task", provider="claude")

        result = await runner.execute_run(context, config)

        assert result.status == "success"
        # add_cost should NOT be called when total_cost is 0
        mock_session_storage.add_cost.assert_not_called()
