"""Extra tests for HookManager."""

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from gobby.hooks.hook_manager import HookManager

pytestmark = pytest.mark.unit


class TestReregisterActiveSessions:
    def test_reregister_active_sessions(self):
        """Test _reregister_active_sessions calls coordinator method."""
        with patch("gobby.hooks.hook_manager.HookManagerFactory.create") as mock_create:
            mock_components = MagicMock()
            mock_create.return_value = mock_components
            
            manager = HookManager()
            
            # Reset mock to verify explicit call
            mock_components.session_coordinator.reregister_active_sessions.reset_mock()
            
            manager._reregister_active_sessions()
            mock_components.session_coordinator.reregister_active_sessions.assert_called_once()


class TestResolveSummaryOutputPath:
    def test_with_project_repo_path(self):
        """Test output path resolved using project's repo_path."""
        with patch("gobby.hooks.hook_manager.HookManagerFactory.create") as mock_create:
            mock_components = MagicMock()
            mock_create.return_value = mock_components
            
            # Setup session
            mock_session = MagicMock()
            mock_session.project_id = "proj-1"
            mock_components.session_storage.get.return_value = mock_session
            
            manager = HookManager()
            
            with patch("gobby.storage.projects.LocalProjectManager") as mock_proj_mgr_cls:
                mock_proj_mgr = MagicMock()
                mock_proj = MagicMock()
                mock_proj.repo_path = "/path/to/repo"
                mock_proj_mgr.get.return_value = mock_proj
                mock_proj_mgr_cls.return_value = mock_proj_mgr
                
                path = manager._resolve_summary_output_path("session-1")
                assert path == "/path/to/repo/.gobby/session_summaries"
                
    def test_fallback_no_session(self):
        """Test output path fallback when session is missing."""
        with patch("gobby.hooks.hook_manager.HookManagerFactory.create") as mock_create:
            mock_components = MagicMock()
            mock_components.session_storage.get.return_value = None
            mock_create.return_value = mock_components
            
            manager = HookManager()
            path = manager._resolve_summary_output_path("session-not-exist")
            assert path == "~/.gobby/session_summaries"

    def test_fallback_exception(self):
        """Test output path fallback when storage throws exception."""
        with patch("gobby.hooks.hook_manager.HookManagerFactory.create") as mock_create:
            mock_components = MagicMock()
            mock_components.session_storage.get.side_effect = ValueError("db error")
            mock_create.return_value = mock_components
            
            manager = HookManager()
            path = manager._resolve_summary_output_path("session-error")
            assert path == "~/.gobby/session_summaries"


class TestDispatchSessionSummaries:
    @patch("gobby.hooks.hook_manager.asyncio.get_running_loop")
    @patch("gobby.hooks.hook_manager.asyncio.run_coroutine_threadsafe")
    @patch("gobby.sessions.summarize.generate_session_summaries", new_callable=AsyncMock)
    def test_dispatches_on_running_loop(self, mock_generate, mock_threadsafe, mock_get_loop):
        """Tests that if a running loop exists, it creates a task on it."""
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop

        with patch("gobby.hooks.hook_manager.HookManagerFactory.create") as mock_create:
            mock_components = MagicMock()
            mock_create.return_value = mock_components
            manager = HookManager()

            # Mock path resolution
            manager._resolve_summary_output_path = MagicMock(return_value="/tmp/sum")

            event = threading.Event()
            manager._dispatch_session_summaries("sess-1", done_event=event)

            # It should create a task on the running loop
            mock_loop.create_task.assert_called_once()
            
            # To test the side-effects of the coro, we'd have to execute it, 
            # but we just verified the correct branch was taken.

    @patch("gobby.hooks.hook_manager.asyncio.get_running_loop")
    @patch("gobby.hooks.hook_manager.asyncio.run_coroutine_threadsafe")
    @patch("gobby.sessions.summarize.generate_session_summaries", new_callable=AsyncMock)
    def test_dispatches_threadsafe_when_no_running_loop(self, mock_generate, mock_threadsafe, mock_get_loop):
        """Tests dispatch when no running loop, but manager has a running _loop."""
        # Force RuntimeError on get_running_loop
        mock_get_loop.side_effect = RuntimeError("no loop")

        with patch("gobby.hooks.hook_manager.HookManagerFactory.create") as mock_create:
            mock_components = MagicMock()
            mock_create.return_value = mock_components
            manager = HookManager()
            
            # Fake that the manager has an attached loop
            manager._loop = MagicMock()
            manager._loop.is_running.return_value = True

            manager._resolve_summary_output_path = MagicMock(return_value="/tmp/sum")

            event = threading.Event()
            manager._dispatch_session_summaries("sess-1", done_event=event)

            mock_threadsafe.assert_called_once()
            
    @patch("gobby.hooks.hook_manager.asyncio.get_running_loop")
    @patch("threading.Thread")
    @patch("gobby.sessions.summarize.generate_session_summaries", new_callable=AsyncMock)
    def test_dispatches_in_new_thread(self, mock_generate, mock_thread, mock_get_loop):
        """Tests fallback to a new daemon thread when no loop is available/running."""
        mock_get_loop.side_effect = RuntimeError("no loop")

        with patch("gobby.hooks.hook_manager.HookManagerFactory.create") as mock_create:
            mock_components = MagicMock()
            mock_create.return_value = mock_components
            manager = HookManager()
            
            # Manager has no attached loop or it's not running
            manager._loop = None

            manager._resolve_summary_output_path = MagicMock(return_value="/tmp/sum")

            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance

            event = threading.Event()
            manager._dispatch_session_summaries("sess-1", done_event=event)

            mock_thread.assert_called_once()
            assert mock_thread.call_args[1]["daemon"] is True
            mock_thread_instance.start.assert_called_once()
