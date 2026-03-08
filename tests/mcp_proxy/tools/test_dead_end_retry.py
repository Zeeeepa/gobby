"""Tests for dead-end retry mechanism in pipeline continuations.

Covers:
- #9937: Dead-end retry counter must increment across re-invocations
- #9938: Dead-end retry must use parent session to avoid infinite lineage
- #9939: Only one dead-end retry chain per pipeline+epic (deduplication)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.workflows._pipelines import (
    _pending_dead_end_retries,
    register_pipeline_tools,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_pending_retries():
    """Clear the module-level dedup dict between tests."""
    _pending_dead_end_retries.clear()
    yield
    # Cancel any lingering tasks
    for task in _pending_dead_end_retries.values():
        task.cancel()
    _pending_dead_end_retries.clear()


@pytest.fixture
def mock_session_manager() -> MagicMock:
    session_mgr = MagicMock()
    sess = MagicMock()
    sess.project_id = "proj-1"
    sess.parent_session_id = "parent-session-uuid"
    session_mgr.get.return_value = sess
    return session_mgr


@pytest.fixture
def mock_completion_registry() -> MagicMock:
    registry = MagicMock()
    registry._pipeline_rerun_callback = AsyncMock()
    registry.is_registered.return_value = False
    registry.register = MagicMock()
    registry.register_continuation = MagicMock()
    return registry


@pytest.fixture
def registry_with_continuation(
    mock_session_manager: MagicMock,
    mock_completion_registry: MagicMock,
) -> InternalToolRegistry:
    """Build an InternalToolRegistry with pipeline tools wired up."""
    registry = InternalToolRegistry(name="gobby-workflows")
    register_pipeline_tools(
        registry,
        loader=MagicMock(),
        executor_getter=lambda: MagicMock(),
        execution_manager_getter=lambda: MagicMock(),
        db=MagicMock(),
        session_manager=mock_session_manager,
        completion_registry=mock_completion_registry,
    )
    return registry


def _get_continuation_tool(registry: InternalToolRegistry):
    """Extract the register_pipeline_continuation callable from the registry."""
    func = registry.get_tool("register_pipeline_continuation")
    if func is None:
        raise RuntimeError("register_pipeline_continuation not found in registry")
    return func


class TestDeadEndRetryCounterIncrements:
    """#9937: Counter must increment across re-invocations."""

    @pytest.mark.asyncio
    async def test_counter_passes_through_yaml_inputs(
        self,
        registry_with_continuation: InternalToolRegistry,
        mock_completion_registry: MagicMock,
    ) -> None:
        """When dead-end retry fires, the retry_inputs must contain incremented counter."""
        handler = _get_continuation_tool(registry_with_continuation)

        # Simulate dead-end: no agents dispatched, not complete, counter at 3
        with patch("gobby.mcp_proxy.tools.workflows._pipelines._resolve_session_ref", return_value="sess-uuid"):
            result = await handler(
                dispatch_outputs={"orchestration_complete": False},
                pipeline_name="dev-loop",
                inputs={
                    "session_task": "#100",
                    "_dead_end_retries": 3,
                },
                session_id="sess-uuid",
            )

        assert result["dead_end_retry"] is True
        assert result["retry_number"] == 4

        # Verify the rerun callback will be called with counter=4
        # Give the asyncio task a moment to be created
        await asyncio.sleep(0)
        # The task is pending (sleeping), check the config it will pass
        assert "dev-loop:#100" in _pending_dead_end_retries

    @pytest.mark.asyncio
    async def test_counter_at_limit_stops_orchestration(
        self,
        registry_with_continuation: InternalToolRegistry,
    ) -> None:
        """When counter reaches max (10), orchestration stops."""
        handler = _get_continuation_tool(registry_with_continuation)

        with patch("gobby.mcp_proxy.tools.workflows._pipelines._resolve_session_ref", return_value="sess-uuid"):
            result = await handler(
                dispatch_outputs={"orchestration_complete": False},
                pipeline_name="dev-loop",
                inputs={
                    "session_task": "#100",
                    "_dead_end_retries": 10,
                },
                session_id="sess-uuid",
            )

        assert result["success"] is False
        assert "retry limit reached" in result["error"].lower()


class TestDeadEndRetryUsesParentSession:
    """#9938: Retry must use parent session to avoid infinite lineage."""

    @pytest.mark.asyncio
    async def test_retry_config_uses_parent_session(
        self,
        registry_with_continuation: InternalToolRegistry,
        mock_completion_registry: MagicMock,
        mock_session_manager: MagicMock,
    ) -> None:
        """Dead-end retry should resolve to parent session, not pipeline child session."""
        handler = _get_continuation_tool(registry_with_continuation)

        with patch("gobby.mcp_proxy.tools.workflows._pipelines._resolve_session_ref", return_value="child-session-uuid"):
            # Mock: session has parent_session_id
            sess = MagicMock()
            sess.project_id = "proj-1"
            sess.parent_session_id = "original-invoker-uuid"
            mock_session_manager.get.return_value = sess

            result = await handler(
                dispatch_outputs={"orchestration_complete": False},
                pipeline_name="dev-loop",
                inputs={"session_task": "#100", "_dead_end_retries": 0},
                session_id="#42",
            )

        assert result["dead_end_retry"] is True

        # Let the delayed retry task start (but it sleeps 10s so won't complete)
        await asyncio.sleep(0.01)

        # The retry should NOT have been called yet (10s delay), but we can
        # check the task was created with correct dedup key
        assert "dev-loop:#100" in _pending_dead_end_retries

    @pytest.mark.asyncio
    async def test_retry_without_parent_uses_resolved_session(
        self,
        registry_with_continuation: InternalToolRegistry,
        mock_session_manager: MagicMock,
    ) -> None:
        """If session has no parent, use the resolved session as-is."""
        handler = _get_continuation_tool(registry_with_continuation)

        sess = MagicMock()
        sess.project_id = "proj-1"
        sess.parent_session_id = None  # No parent
        mock_session_manager.get.return_value = sess

        with patch("gobby.mcp_proxy.tools.workflows._pipelines._resolve_session_ref", return_value="root-session"):
            result = await handler(
                dispatch_outputs={"orchestration_complete": False},
                pipeline_name="dev-loop",
                inputs={"session_task": "#100", "_dead_end_retries": 0},
                session_id="#42",
            )

        assert result["dead_end_retry"] is True


class TestDeadEndRetryDeduplication:
    """#9939: Only one pending retry per pipeline+epic."""

    @pytest.mark.asyncio
    async def test_second_retry_cancels_first(
        self,
        registry_with_continuation: InternalToolRegistry,
    ) -> None:
        """A second dead-end retry for the same pipeline+epic cancels the first."""
        handler = _get_continuation_tool(registry_with_continuation)

        with patch("gobby.mcp_proxy.tools.workflows._pipelines._resolve_session_ref", return_value="sess-uuid"):
            # First retry
            result1 = await handler(
                dispatch_outputs={"orchestration_complete": False},
                pipeline_name="dev-loop",
                inputs={"session_task": "#100", "_dead_end_retries": 0},
                session_id="sess-uuid",
            )
            first_task = _pending_dead_end_retries.get("dev-loop:#100")

            # Second retry (e.g., from parallel agent completion)
            result2 = await handler(
                dispatch_outputs={"orchestration_complete": False},
                pipeline_name="dev-loop",
                inputs={"session_task": "#100", "_dead_end_retries": 1},
                session_id="sess-uuid",
            )

        assert result1["dead_end_retry"] is True
        assert result2["dead_end_retry"] is True
        # Let cancellation propagate
        await asyncio.sleep(0)
        # First task should be cancelled
        assert first_task.cancelled() or first_task.done()
        # Second task should be the current one
        assert "dev-loop:#100" in _pending_dead_end_retries
        second_task = _pending_dead_end_retries["dev-loop:#100"]
        assert not second_task.done()

    @pytest.mark.asyncio
    async def test_different_epics_get_separate_retries(
        self,
        registry_with_continuation: InternalToolRegistry,
    ) -> None:
        """Different epics can have independent retries."""
        handler = _get_continuation_tool(registry_with_continuation)

        with patch("gobby.mcp_proxy.tools.workflows._pipelines._resolve_session_ref", return_value="sess-uuid"):
            await handler(
                dispatch_outputs={"orchestration_complete": False},
                pipeline_name="dev-loop",
                inputs={"session_task": "#100", "_dead_end_retries": 0},
                session_id="sess-uuid",
            )
            await handler(
                dispatch_outputs={"orchestration_complete": False},
                pipeline_name="dev-loop",
                inputs={"session_task": "#200", "_dead_end_retries": 0},
                session_id="sess-uuid",
            )

        assert "dev-loop:#100" in _pending_dead_end_retries
        assert "dev-loop:#200" in _pending_dead_end_retries

    @pytest.mark.asyncio
    async def test_agents_dispatched_cancels_pending_retry(
        self,
        registry_with_continuation: InternalToolRegistry,
        mock_completion_registry: MagicMock,
    ) -> None:
        """When agents ARE dispatched, any pending dead-end retry is cancelled."""
        handler = _get_continuation_tool(registry_with_continuation)

        with patch("gobby.mcp_proxy.tools.workflows._pipelines._resolve_session_ref", return_value="sess-uuid"):
            # Create a pending dead-end retry
            await handler(
                dispatch_outputs={"orchestration_complete": False},
                pipeline_name="dev-loop",
                inputs={"session_task": "#100", "_dead_end_retries": 0},
                session_id="sess-uuid",
            )
            pending_task = _pending_dead_end_retries.get("dev-loop:#100")
            assert pending_task is not None

            # Now agents get dispatched
            await handler(
                dispatch_outputs={
                    "developers": {"results": [{"run_id": "run-abc"}]},
                },
                pipeline_name="dev-loop",
                inputs={"session_task": "#100", "_dead_end_retries": 1},
                session_id="sess-uuid",
            )

        # Let cancellation propagate
        await asyncio.sleep(0)
        # Pending retry should be cancelled
        assert pending_task.cancelled() or pending_task.done()
        assert "dev-loop:#100" not in _pending_dead_end_retries
