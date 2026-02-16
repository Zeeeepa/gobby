"""Tests for background action dispatch and transcript-based title re-synthesis."""

import asyncio
import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.definitions import WorkflowDefinition
from gobby.workflows.lifecycle_evaluator import (
    _background_action_done,
    _background_actions,
    _dispatch_background_action,
    evaluate_lifecycle_triggers,
    evaluate_workflow_triggers,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_background_actions() -> None:
    """Clear background actions between tests to prevent cross-test pollution."""
    _background_actions.clear()
    yield  # type: ignore[misc]
    _background_actions.clear()


def _make_action_executor(**overrides: object) -> MagicMock:
    """Create a mock ActionExecutor with required attributes."""
    executor = MagicMock()
    executor.execute = AsyncMock(return_value={})
    executor.db = MagicMock()
    executor.session_manager = MagicMock()
    executor.session_manager.get.return_value = None
    executor.template_engine = MagicMock()
    executor.llm_service = None
    executor.transcript_processor = None
    executor.config = None
    executor.tool_proxy_getter = None
    executor.memory_manager = None
    executor.memory_sync_manager = None
    executor.task_sync_manager = None
    executor.session_task_manager = None
    executor.skill_manager = None
    executor.task_manager = None
    for k, v in overrides.items():
        setattr(executor, k, v)
    return executor


def _make_state_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.get_state.return_value = None
    return mgr


def _make_evaluator(*, result: bool = True) -> MagicMock:
    evaluator = MagicMock()
    evaluator.evaluate.return_value = result
    return evaluator


def _make_event(event_type: HookEventType = HookEventType.BEFORE_AGENT) -> HookEvent:
    return HookEvent(
        event_type=event_type,
        session_id="ext-test-session",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        metadata={"_platform_session_id": "test-session"},
        data={"prompt": "test prompt"},
    )


def _make_workflow(triggers: dict | None = None) -> WorkflowDefinition:
    return WorkflowDefinition(
        name="test-workflow",
        description="Test",
        triggers=triggers or {},
        variables={},
    )


class TestBackgroundActionDispatch:
    """Tests for _dispatch_background_action and the module-level task set."""

    @pytest.mark.asyncio
    async def test_background_action_dispatched_as_task(self) -> None:
        """Verify action is dispatched as an asyncio task and tracked."""
        executor = _make_action_executor()
        executor.execute = AsyncMock(return_value={"title_synthesized": "Test Title"})
        ctx = MagicMock()

        _dispatch_background_action(executor, "synthesize_title", ctx, {"source": "transcript"})

        # Task should be tracked
        assert len(_background_actions) >= 1

        # Let the task complete
        await asyncio.sleep(0.05)

        # Executor should have been called
        executor.execute.assert_awaited_once_with("synthesize_title", ctx, source="transcript")

        # Task should be cleaned up after completion
        # (done callback discards from set)
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_background_action_error_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify errors in background actions are logged via done callback."""
        executor = _make_action_executor()
        executor.execute = AsyncMock(side_effect=RuntimeError("LLM timeout"))
        ctx = MagicMock()

        with caplog.at_level(logging.ERROR, logger="gobby.workflows.lifecycle_evaluator"):
            _dispatch_background_action(executor, "synthesize_title", ctx, {})
            # Await all background tasks so done callbacks fire
            for t in list(_background_actions):
                try:
                    await t
                except RuntimeError:
                    pass
            # Yield once more for done callback scheduling
            await asyncio.sleep(0)

        assert any("Background action failed" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_background_action_result_not_processed(self) -> None:
        """Verify background action results don't affect the hook response."""
        # If action returns inject_context, it should be ignored since it's background
        executor = _make_action_executor()
        executor.execute = AsyncMock(return_value={"inject_context": "Should be ignored"})

        workflow = _make_workflow(
            triggers={
                "on_before_agent": [
                    {"action": "synthesize_title", "background": True, "source": "transcript"},
                ]
            }
        )

        event = _make_event()
        state_manager = _make_state_manager()
        evaluator = _make_evaluator()

        response = await evaluate_workflow_triggers(
            workflow, event, {}, state_manager, executor, evaluator
        )

        # Response should have no context (background result discarded)
        assert response.decision == "allow"
        assert response.context is None

        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_background_kwarg_popped(self) -> None:
        """Verify 'background' key is not passed to the action executor."""
        executor = _make_action_executor()
        ctx = MagicMock()

        _dispatch_background_action(executor, "synthesize_title", ctx, {"source": "transcript"})
        await asyncio.sleep(0.05)

        # The kwargs passed should NOT contain 'background'
        call_kwargs = executor.execute.call_args
        assert "background" not in call_kwargs.kwargs
        # 'source' should be passed through
        assert call_kwargs.kwargs.get("source") == "transcript" or (
            len(call_kwargs.args) >= 3 and call_kwargs.args[2] == "transcript"
        )

    @pytest.mark.asyncio
    async def test_background_false_is_noop(self) -> None:
        """Verify background: false runs the action normally (foreground)."""
        executor = _make_action_executor()
        executor.execute = AsyncMock(return_value={"title_synthesized": "Test"})

        workflow = _make_workflow(
            triggers={
                "on_before_agent": [
                    {"action": "synthesize_title", "background": False},
                ]
            }
        )

        event = _make_event()
        state_manager = _make_state_manager()
        evaluator = _make_evaluator()

        response = await evaluate_workflow_triggers(
            workflow, event, {}, state_manager, executor, evaluator
        )

        # Action should have been called directly (not as background task)
        executor.execute.assert_awaited_once()
        assert response.decision == "allow"

    @pytest.mark.asyncio
    async def test_background_with_when_condition(self) -> None:
        """Verify 'when' condition is evaluated before dispatching background action."""
        executor = _make_action_executor()

        workflow = _make_workflow(
            triggers={
                "on_before_agent": [
                    {
                        "action": "synthesize_title",
                        "background": True,
                        "source": "transcript",
                        "when": "False",  # Should prevent dispatch
                    },
                ]
            }
        )

        event = _make_event()
        state_manager = _make_state_manager()
        evaluator = _make_evaluator(result=False)

        await evaluate_workflow_triggers(workflow, event, {}, state_manager, executor, evaluator)

        # Action should NOT have been called (when=False)
        executor.execute.assert_not_awaited()
        await asyncio.sleep(0.05)


class TestBackgroundActionDoneCallback:
    """Tests for the done callback function."""

    def test_done_callback_discards_from_set(self) -> None:
        """Done callback removes task from _background_actions."""
        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(asyncio.sleep(0))
            _background_actions.add(task)
            loop.run_until_complete(task)

            _background_action_done(task)
            assert task not in _background_actions
        finally:
            loop.close()

    def test_done_callback_handles_cancelled(self) -> None:
        """Done callback handles cancelled tasks gracefully."""
        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(asyncio.sleep(100))
            _background_actions.add(task)
            task.cancel()
            try:
                loop.run_until_complete(task)
            except asyncio.CancelledError:
                pass

            # Should not raise
            _background_action_done(task)
            assert task not in _background_actions
        finally:
            loop.close()


class TestLifecycleTriggersBackground:
    """Tests for background actions in evaluate_lifecycle_triggers."""

    @pytest.mark.asyncio
    async def test_lifecycle_background_action_dispatched(self) -> None:
        """Verify background actions work in evaluate_lifecycle_triggers."""
        executor = _make_action_executor()
        executor.execute = AsyncMock(return_value={"title_synthesized": "BG Title"})
        evaluator = _make_evaluator()

        loader = AsyncMock()
        loader.load_workflow = AsyncMock(
            return_value=WorkflowDefinition(
                name="test-lifecycle",
                description="Test",
                triggers={
                    "on_before_agent": [
                        {"action": "synthesize_title", "background": True, "source": "transcript"},
                    ]
                },
                variables={},
            )
        )

        event = _make_event()

        response = await evaluate_lifecycle_triggers(
            "test-lifecycle", event, loader, executor, evaluator
        )

        # Response should be allow with no context (background action is fire-and-forget)
        assert response.decision == "allow"
        assert response.context is None

        # Let the background task complete
        await asyncio.sleep(0.05)

        # The executor should have been called
        executor.execute.assert_awaited_once()


class TestSynthesizeTitleSourceTranscript:
    """Tests for source=transcript in handle_synthesize_title."""

    @pytest.mark.asyncio
    async def test_source_transcript_skips_prompt(self) -> None:
        """Verify source=transcript forces transcript path even when prompt available."""
        from gobby.workflows.summary_actions import handle_synthesize_title

        ctx = MagicMock()
        ctx.session_manager = MagicMock()
        ctx.session_id = "test-session"
        ctx.llm_service = MagicMock()
        ctx.transcript_processor = MagicMock()
        ctx.template_engine = MagicMock()
        ctx.event_data = {"prompt": "continue", "prompt_text": "continue"}

        with patch(
            "gobby.workflows.summary_actions.synthesize_title",
            new_callable=AsyncMock,
            return_value={"title_synthesized": "Transcript Title"},
        ) as mock_synth:
            await handle_synthesize_title(ctx, source="transcript")

            # prompt should be None (skipped due to source=transcript)
            mock_synth.assert_awaited_once()
            call_kwargs = mock_synth.call_args.kwargs
            assert call_kwargs["prompt"] is None

    @pytest.mark.asyncio
    async def test_no_source_uses_prompt(self) -> None:
        """Verify without source kwarg, prompt is extracted from event data."""
        from gobby.workflows.summary_actions import handle_synthesize_title

        ctx = MagicMock()
        ctx.session_manager = MagicMock()
        ctx.session_id = "test-session"
        ctx.llm_service = MagicMock()
        ctx.transcript_processor = MagicMock()
        ctx.template_engine = MagicMock()
        ctx.event_data = {"prompt": "implement feature X"}

        with patch(
            "gobby.workflows.summary_actions.synthesize_title",
            new_callable=AsyncMock,
            return_value={"title_synthesized": "Feature X"},
        ) as mock_synth:
            await handle_synthesize_title(ctx)

            mock_synth.assert_awaited_once()
            call_kwargs = mock_synth.call_args.kwargs
            assert call_kwargs["prompt"] == "implement feature X"
