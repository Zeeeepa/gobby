import pytest
import asyncio
import threading
from unittest.mock import MagicMock, AsyncMock, patch
from gobby.workflows.hooks import WorkflowHookHandler
from gobby.hooks.events import HookEvent, HookResponse, HookEventType, SessionSource
from datetime import datetime


class TestWorkflowHookHandler:
    @pytest.fixture
    def mock_engine(self):
        engine = MagicMock()
        engine.evaluate_all_lifecycle_workflows = AsyncMock(
            return_value=HookResponse(decision="allow")
        )
        engine.handle_event = AsyncMock(return_value=HookResponse(decision="allow"))
        engine.evaluate_lifecycle_triggers = AsyncMock(return_value=HookResponse(decision="allow"))
        return engine

    @pytest.fixture
    def event(self):
        return HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id="session-123",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(),
            data={},
        )

    def test_init(self, mock_engine):
        handler = WorkflowHookHandler(mock_engine, enabled=False)
        assert not handler._enabled
        assert handler.engine == mock_engine

    def test_disabled(self, mock_engine, event):
        handler = WorkflowHookHandler(mock_engine, enabled=False)

        assert handler.handle_all_lifecycles(event).decision == "allow"
        assert handler.handle(event).decision == "allow"
        assert handler.handle_lifecycle("wf", event).decision == "allow"

        mock_engine.evaluate_all_lifecycle_workflows.assert_not_called()
        mock_engine.handle_event.assert_not_called()

    def test_handle_sync_straight(self, mock_engine, event):
        # Case specific to no running loop (pytest-asyncio might interfere, so we might need to patch asyncio.run or be careful)
        # Assuming typical unit test env where we can start a fresh loop if needed for strict sync calls?
        # Actually in pytest-asyncio, there IS a loop running usually.
        # But this method uses asyncio.run() if no loop in self._loop.

        # Let's mock a handler that assumes no loop is running
        with patch("asyncio.run") as mock_run:
            mock_run.return_value = HookResponse(decision="deny")

            handler = WorkflowHookHandler(mock_engine)
            # Force no loop
            handler._loop = None

            # We also need to ensure asyncio.get_running_loop raises RuntimeError or we patch it
            with patch("asyncio.get_running_loop", side_effect=RuntimeError):
                handler = WorkflowHookHandler(mock_engine)
                res = handler.handle(event)
                assert res.decision == "deny"
                mock_run.assert_called_once()

    def test_handle_exception(self, mock_engine, event):
        handler = WorkflowHookHandler(mock_engine)
        handler._loop = None
        with patch("asyncio.run", side_effect=Exception("Boom")):
            with patch("asyncio.get_running_loop", side_effect=RuntimeError):
                res = handler.handle(event)
                assert res.decision == "allow"

    @pytest.mark.asyncio
    async def test_handle_main_thread_loop_running(self, mock_engine, event):
        # Simulate being on main thread with a running loop
        # The code returns "allow" to avoid blocking
        handler = WorkflowHookHandler(mock_engine, loop=asyncio.get_running_loop())

        # We need to ensure threading.current_thread() is threading.main_thread()
        if threading.current_thread() is threading.main_thread():
            res = handler.handle(event)
            assert res.decision == "allow"
        else:
            pytest.skip("Test must run on main thread")

    def test_handle_thread_safe(self, mock_engine, event):
        # We need to simulate running from a DIFFERENT thread than the loop

        # Create a loop in a separate thread (Background Loop)
        loop = asyncio.new_event_loop()
        t_loop = threading.Thread(target=loop.run_forever)
        t_loop.start()

        try:
            handler = WorkflowHookHandler(mock_engine, loop=loop)

            # Now call handle from a THIRD thread (Worker Thread)
            # This ensures threading.current_thread() != main_thread()
            # satisfying the guard in hooks.py

            mock_engine.handle_event.return_value = HookResponse(decision="ask")

            result_holder = {}

            def run_handle():
                result_holder["res"] = handler.handle(event)

            t_worker = threading.Thread(target=run_handle)
            t_worker.start()
            t_worker.join()

            res = result_holder.get("res")
            assert res is not None
            assert res.decision == "ask"

        finally:
            loop.call_soon_threadsafe(loop.stop)
            t_loop.join()
            loop.close()

    def test_handle_all_lifecycles_thread_safe(self, mock_engine, event):
        loop = asyncio.new_event_loop()
        t_loop = threading.Thread(target=loop.run_forever)
        t_loop.start()
        try:
            handler = WorkflowHookHandler(mock_engine, loop=loop)
            mock_engine.evaluate_all_lifecycle_workflows.return_value = HookResponse(
                decision="deny"
            )

            result_holder = {}

            def run_handle():
                result_holder["res"] = handler.handle_all_lifecycles(event)

            t_worker = threading.Thread(target=run_handle)
            t_worker.start()
            t_worker.join()

            res = result_holder.get("res")
            assert res is not None
            assert res.decision == "deny"

        finally:
            loop.call_soon_threadsafe(loop.stop)
            t_loop.join()
            loop.close()

    def test_handle_lifecycle_thread_safe(self, mock_engine, event):
        loop = asyncio.new_event_loop()
        t_loop = threading.Thread(target=loop.run_forever)
        t_loop.start()
        try:
            handler = WorkflowHookHandler(mock_engine, loop=loop)
            mock_engine.evaluate_lifecycle_triggers.return_value = HookResponse(decision="modify")

            result_holder = {}

            def run_handle():
                result_holder["res"] = handler.handle_lifecycle("wf1", event)

            t_worker = threading.Thread(target=run_handle)
            t_worker.start()
            t_worker.join()

            res = result_holder.get("res")
            assert res is not None
            assert res.decision == "modify"

        finally:
            loop.call_soon_threadsafe(loop.stop)
            t_loop.join()
            loop.close()
