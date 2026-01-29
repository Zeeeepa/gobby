"""
Tests for session-related workflow actions in gobby.workflows.session_actions.

Tests the four main functions:
- start_new_session: Starting new CLI sessions with various configurations
- mark_session_status: Marking current or parent session status
- switch_mode: Signaling agent mode switches
- mark_loop_complete: Marking workflow loops as complete
"""

from unittest.mock import MagicMock, patch

import pytest

from gobby.storage.sessions import LocalSessionManager
from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.session_actions import (
    mark_session_status,
    start_new_session,
    switch_mode,
)

pytestmark = pytest.mark.unit

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_session():
    """Create a mock session with standard attributes."""
    session = MagicMock()
    session.source = "claude"
    session.project_path = "/tmp/test"
    session.parent_session_id = None
    return session


@pytest.fixture
def mock_session_manager(mock_session):
    """Create a mock session manager."""
    session_manager = MagicMock(spec=LocalSessionManager)
    session_manager.get.return_value = mock_session
    return session_manager


@pytest.fixture
def mock_context(mock_session_manager):
    """Create a mock action context for executor-based tests."""
    return ActionContext(
        session_id="sess_123",
        state=WorkflowState(
            session_id="sess_123",
            workflow_name="test_workflow",
            step="test_step",
            variables={},
        ),
        db=MagicMock(),
        session_manager=mock_session_manager,
        template_engine=MagicMock(),
    )


# =============================================================================
# Tests for start_new_session
# =============================================================================


class TestStartNewSession:
    """Tests for the start_new_session function."""

    def test_session_not_found(self, mock_session_manager) -> None:
        """Test error when session is not found."""
        mock_session_manager.get.return_value = None

        result = start_new_session(
            session_manager=mock_session_manager,
            session_id="nonexistent",
        )

        assert result == {"error": "Session not found"}

    def test_auto_detect_claude_source(self, mock_session_manager, mock_session) -> None:
        """Test auto-detection of claude command from session source."""
        mock_session.source = "claude"

        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
            )

            assert result["started_new_session"] is True
            args, _ = mock_popen.call_args
            assert args[0][0] == "claude"

    def test_auto_detect_gemini_source(self, mock_session_manager, mock_session) -> None:
        """Test auto-detection of gemini command from session source."""
        mock_session.source = "gemini"

        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
            )

            assert result["started_new_session"] is True
            args, _ = mock_popen.call_args
            assert args[0][0] == "gemini"

    def test_auto_detect_unknown_source_defaults_to_claude(
        self, mock_session_manager, mock_session
    ) -> None:
        """Test that unknown source defaults to claude command."""
        mock_session.source = "unknown_source"

        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
            )

            assert result["started_new_session"] is True
            args, _ = mock_popen.call_args
            assert args[0][0] == "claude"

    def test_auto_detect_missing_source_attribute(self, mock_session_manager, mock_session) -> None:
        """Test when session has no source attribute."""
        # Remove the source attribute to trigger getattr fallback
        del mock_session.source

        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
            )

            assert result["started_new_session"] is True
            args, _ = mock_popen.call_args
            # Default is "claude" when source attribute is missing
            assert args[0][0] == "claude"

    def test_explicit_command_overrides_source(self, mock_session_manager, mock_session) -> None:
        """Test that explicit command overrides auto-detection."""
        mock_session.source = "claude"

        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
                command="custom-cli",
            )

            assert result["started_new_session"] is True
            args, _ = mock_popen.call_args
            assert args[0][0] == "custom-cli"

    def test_args_as_string(self, mock_session_manager) -> None:
        """Test parsing args from string using shlex."""
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
                command="claude",
                args="-v --debug 'quoted arg'",
            )

            assert result["started_new_session"] is True
            args, _ = mock_popen.call_args
            cmd_list = args[0]
            assert "-v" in cmd_list
            assert "--debug" in cmd_list
            assert "quoted arg" in cmd_list

    def test_args_as_list(self, mock_session_manager) -> None:
        """Test args passed as a list."""
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
                command="claude",
                args=["-v", "--debug", "arg with spaces"],
            )

            assert result["started_new_session"] is True
            args, _ = mock_popen.call_args
            cmd_list = args[0]
            assert "-v" in cmd_list
            assert "--debug" in cmd_list
            assert "arg with spaces" in cmd_list

    def test_args_empty_list(self, mock_session_manager) -> None:
        """Test empty args list."""
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
                command="claude",
                args=[],
            )

            assert result["started_new_session"] is True
            args, _ = mock_popen.call_args
            cmd_list = args[0]
            assert cmd_list == ["claude"]

    def test_prompt_injection_for_claude(self, mock_session_manager) -> None:
        """Test prompt injection via -p flag for claude."""
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
                command="claude",
                prompt="Hello world",
            )

            assert result["started_new_session"] is True
            args, _ = mock_popen.call_args
            cmd_list = args[0]
            assert "-p" in cmd_list
            assert "Hello world" in cmd_list

    def test_prompt_injection_for_gemini(self, mock_session_manager) -> None:
        """Test prompt injection via -p flag for gemini."""
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
                command="gemini",
                prompt="Start with context",
            )

            assert result["started_new_session"] is True
            args, _ = mock_popen.call_args
            cmd_list = args[0]
            assert "-p" in cmd_list
            assert "Start with context" in cmd_list

    def test_no_prompt_injection_for_other_commands(self, mock_session_manager) -> None:
        """Test that prompt is not injected for non-claude/gemini commands."""
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
                command="custom-cli",
                prompt="Some prompt",
            )

            assert result["started_new_session"] is True
            args, _ = mock_popen.call_args
            cmd_list = args[0]
            assert "-p" not in cmd_list
            assert "Some prompt" not in cmd_list

    def test_explicit_cwd(self, mock_session_manager) -> None:
        """Test explicit working directory."""
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
                cwd="/custom/path",
            )

            assert result["started_new_session"] is True
            _, kwargs = mock_popen.call_args
            assert kwargs["cwd"] == "/custom/path"

    def test_cwd_from_session_project_path(self, mock_session_manager, mock_session) -> None:
        """Test cwd defaults to session's project_path."""
        mock_session.project_path = "/project/root"

        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
            )

            assert result["started_new_session"] is True
            _, kwargs = mock_popen.call_args
            assert kwargs["cwd"] == "/project/root"

    def test_cwd_fallback_to_dot(self, mock_session_manager, mock_session) -> None:
        """Test cwd falls back to '.' when no project_path."""
        mock_session.project_path = None

        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
            )

            assert result["started_new_session"] is True
            _, kwargs = mock_popen.call_args
            assert kwargs["cwd"] == "."

    def test_cwd_missing_project_path_attribute(self, mock_session_manager, mock_session) -> None:
        """Test cwd when session has no project_path attribute."""
        del mock_session.project_path

        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
            )

            assert result["started_new_session"] is True
            _, kwargs = mock_popen.call_args
            assert kwargs["cwd"] == "."

    def test_popen_called_with_correct_options(self, mock_session_manager) -> None:
        """Test Popen is called with detached process options."""
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
            )

            mock_popen.assert_called_once()
            _, kwargs = mock_popen.call_args

            # Verify detached process options
            import subprocess

            assert kwargs["stdout"] == subprocess.DEVNULL
            assert kwargs["stderr"] == subprocess.DEVNULL
            assert kwargs["stdin"] == subprocess.DEVNULL
            assert kwargs["start_new_session"] is True

    def test_subprocess_exception_handling(self, mock_session_manager) -> None:
        """Test error handling when subprocess.Popen raises an exception."""
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = FileNotFoundError("Command not found")

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
                command="nonexistent-command",
            )

            assert "error" in result
            assert "Command not found" in result["error"]

    def test_subprocess_permission_error(self, mock_session_manager) -> None:
        """Test error handling when subprocess.Popen raises PermissionError."""
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = PermissionError("Permission denied")

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
            )

            assert "error" in result
            assert "Permission denied" in result["error"]

    def test_subprocess_os_error(self, mock_session_manager) -> None:
        """Test error handling when subprocess.Popen raises OSError."""
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = OSError("OS error occurred")

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
            )

            assert "error" in result
            assert "OS error occurred" in result["error"]

    def test_return_value_structure(self, mock_session_manager) -> None:
        """Test the structure of successful return value."""
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 99999
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
                command="claude",
                args=["-v"],
            )

            assert "started_new_session" in result
            assert result["started_new_session"] is True
            assert "pid" in result
            assert result["pid"] == 99999
            assert "command" in result
            assert "claude" in result["command"]
            assert "-v" in result["command"]

    def test_full_command_with_all_options(self, mock_session_manager) -> None:
        """Test starting session with all options specified."""
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = start_new_session(
                session_manager=mock_session_manager,
                session_id="sess_123",
                command="claude",
                args=["--verbose", "--model", "opus"],
                prompt="Continue the task",
                cwd="/workspace",
            )

            assert result["started_new_session"] is True
            assert result["pid"] == 12345

            args, kwargs = mock_popen.call_args
            cmd_list = args[0]

            assert cmd_list[0] == "claude"
            assert "--verbose" in cmd_list
            assert "--model" in cmd_list
            assert "opus" in cmd_list
            assert "-p" in cmd_list
            assert "Continue the task" in cmd_list
            assert kwargs["cwd"] == "/workspace"


# =============================================================================
# Tests for mark_session_status
# =============================================================================


class TestMarkSessionStatus:
    """Tests for the mark_session_status function."""

    def test_missing_status_error(self, mock_session_manager) -> None:
        """Test error when status is not provided."""
        result = mark_session_status(
            session_manager=mock_session_manager,
            session_id="sess_123",
            status=None,
        )

        assert result == {"error": "Missing status"}

    def test_mark_current_session_status(self, mock_session_manager) -> None:
        """Test marking current session status."""
        result = mark_session_status(
            session_manager=mock_session_manager,
            session_id="sess_123",
            status="active",
            target="current_session",
        )

        assert result["status_updated"] is True
        assert result["session_id"] == "sess_123"
        assert result["status"] == "active"
        mock_session_manager.update_status.assert_called_once_with("sess_123", "active")

    def test_mark_current_session_default_target(self, mock_session_manager) -> None:
        """Test that current_session is the default target."""
        result = mark_session_status(
            session_manager=mock_session_manager,
            session_id="sess_123",
            status="completed",
        )

        assert result["status_updated"] is True
        assert result["session_id"] == "sess_123"
        mock_session_manager.update_status.assert_called_once_with("sess_123", "completed")

    def test_mark_parent_session_status_success(self, mock_session_manager, mock_session) -> None:
        """Test marking parent session status when parent exists."""
        mock_session.parent_session_id = "parent_sess_456"

        result = mark_session_status(
            session_manager=mock_session_manager,
            session_id="sess_123",
            status="waiting",
            target="parent_session",
        )

        assert result["status_updated"] is True
        assert result["session_id"] == "parent_sess_456"
        assert result["status"] == "waiting"
        mock_session_manager.update_status.assert_called_once_with("parent_sess_456", "waiting")

    def test_mark_parent_session_no_parent(self, mock_session_manager, mock_session) -> None:
        """Test error when marking parent but no parent session exists."""
        mock_session.parent_session_id = None

        result = mark_session_status(
            session_manager=mock_session_manager,
            session_id="sess_123",
            status="waiting",
            target="parent_session",
        )

        assert result == {"error": "No parent session linked"}
        mock_session_manager.update_status.assert_not_called()

    def test_mark_parent_session_current_not_found(self, mock_session_manager) -> None:
        """Test error when marking parent but current session not found."""
        mock_session_manager.get.return_value = None

        result = mark_session_status(
            session_manager=mock_session_manager,
            session_id="sess_123",
            status="waiting",
            target="parent_session",
        )

        assert result == {"error": "No parent session linked"}
        mock_session_manager.update_status.assert_not_called()

    def test_various_status_values(self, mock_session_manager) -> None:
        """Test marking session with various status values."""
        statuses = ["active", "completed", "failed", "waiting", "paused"]

        for status in statuses:
            mock_session_manager.reset_mock()

            result = mark_session_status(
                session_manager=mock_session_manager,
                session_id="sess_123",
                status=status,
            )

            assert result["status_updated"] is True
            assert result["status"] == status
            mock_session_manager.update_status.assert_called_once_with("sess_123", status)

    def test_empty_string_status(self, mock_session_manager) -> None:
        """Test that empty string status is treated as missing."""
        # Empty string is falsy in Python, so it should be treated as missing
        result = mark_session_status(
            session_manager=mock_session_manager,
            session_id="sess_123",
            status="",
        )

        assert result == {"error": "Missing status"}


# =============================================================================
# Tests for switch_mode
# =============================================================================


class TestSwitchMode:
    """Tests for the switch_mode function."""

    def test_missing_mode_error(self) -> None:
        """Test error when mode is not provided."""
        result = switch_mode(mode=None)

        assert result == {"error": "Missing mode"}

    def test_switch_to_plan_mode(self) -> None:
        """Test switching to PLAN mode."""
        result = switch_mode(mode="PLAN")

        assert "inject_context" in result
        assert "mode_switch" in result
        assert result["mode_switch"] == "PLAN"
        assert "PLAN" in result["inject_context"]
        assert "SWITCH MODE TO PLAN" in result["inject_context"]

    def test_switch_to_act_mode(self) -> None:
        """Test switching to ACT mode."""
        result = switch_mode(mode="ACT")

        assert result["mode_switch"] == "ACT"
        assert "SWITCH MODE TO ACT" in result["inject_context"]
        assert "You are now in ACT mode" in result["inject_context"]

    def test_switch_to_reflect_mode(self) -> None:
        """Test switching to REFLECT mode."""
        result = switch_mode(mode="REFLECT")

        assert result["mode_switch"] == "REFLECT"
        assert "SWITCH MODE TO REFLECT" in result["inject_context"]

    def test_mode_uppercased_in_message(self) -> None:
        """Test that mode is uppercased in the inject_context message."""
        result = switch_mode(mode="plan")

        assert result["mode_switch"] == "plan"
        assert "SWITCH MODE TO PLAN" in result["inject_context"]
        assert "You are now in PLAN mode" in result["inject_context"]

    def test_custom_mode(self) -> None:
        """Test switching to a custom mode."""
        result = switch_mode(mode="custom_mode")

        assert result["mode_switch"] == "custom_mode"
        assert "SWITCH MODE TO CUSTOM_MODE" in result["inject_context"]

    def test_inject_context_format(self) -> None:
        """Test the format of the inject_context message."""
        result = switch_mode(mode="test")

        expected_parts = [
            "SYSTEM: SWITCH MODE TO TEST",
            "You are now in TEST mode.",
            "Adjust your behavior accordingly.",
        ]

        for part in expected_parts:
            assert part in result["inject_context"]

    def test_empty_string_mode(self) -> None:
        """Test that empty string mode is treated as missing."""
        result = switch_mode(mode="")

        assert result == {"error": "Missing mode"}


# =============================================================================
# Integration tests with ActionExecutor
# =============================================================================


class TestActionExecutorIntegration:
    """Tests for session actions through ActionExecutor."""

    @pytest.mark.asyncio
    async def test_start_new_session_via_executor(self, mock_context):
        """Test start_new_session action through executor."""
        executor = ActionExecutor(
            db=MagicMock(),
            session_manager=mock_context.session_manager,
            template_engine=MagicMock(),
        )

        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = await executor.execute(
                "start_new_session",
                mock_context,
                command="claude",
                args=["-vv"],
                prompt="Hello world",
            )

            assert result is not None
            assert result["started_new_session"] is True
            assert result["pid"] == 12345

    @pytest.mark.asyncio
    async def test_mark_session_status_via_executor(self, mock_context):
        """Test mark_session_status action through executor."""
        executor = ActionExecutor(
            db=MagicMock(),
            session_manager=mock_context.session_manager,
            template_engine=MagicMock(),
        )

        result = await executor.execute(
            "mark_session_status",
            mock_context,
            status="active",
            target="current_session",
        )

        assert result is not None
        assert result["status_updated"] is True
        assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_switch_mode_via_executor(self, mock_context):
        """Test switch_mode action through executor."""
        executor = ActionExecutor(
            db=MagicMock(),
            session_manager=mock_context.session_manager,
            template_engine=MagicMock(),
        )

        result = await executor.execute("switch_mode", mock_context, mode="PLAN")

        assert result is not None
        assert result["mode_switch"] == "PLAN"
        assert "inject_context" in result

    @pytest.mark.asyncio
    async def test_executor_with_missing_args(self, mock_context):
        """Test executor handles missing arguments gracefully."""
        executor = ActionExecutor(
            db=MagicMock(),
            session_manager=mock_context.session_manager,
            template_engine=MagicMock(),
        )

        # Missing status
        result = await executor.execute("mark_session_status", mock_context)
        assert result == {"error": "Missing status"}

        # Missing mode
        result = await executor.execute("switch_mode", mock_context)
        assert result == {"error": "Missing mode"}

    @pytest.mark.asyncio
    async def test_start_new_session_auto_detect_source_via_executor(self, mock_context):
        """Test auto-detection of source through executor."""
        executor = ActionExecutor(
            db=MagicMock(),
            session_manager=mock_context.session_manager,
            template_engine=MagicMock(),
        )

        # Session source is 'claude' from fixture
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 11111
            mock_popen.return_value = mock_proc

            result = await executor.execute("start_new_session", mock_context)

            assert result["started_new_session"] is True
            args, _ = mock_popen.call_args
            assert args[0][0] == "claude"

        # Change to gemini
        mock_context.session_manager.get.return_value.source = "gemini"
        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 22222
            mock_popen.return_value = mock_proc

            result = await executor.execute("start_new_session", mock_context)

            assert result["started_new_session"] is True
            args, _ = mock_popen.call_args
            assert args[0][0] == "gemini"

    @pytest.mark.asyncio
    async def test_start_new_session_explicit_cwd_via_executor(self, mock_context):
        """Test explicit cwd through executor."""
        executor = ActionExecutor(
            db=MagicMock(),
            session_manager=mock_context.session_manager,
            template_engine=MagicMock(),
        )

        with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            result = await executor.execute("start_new_session", mock_context, cwd="/custom/path")

            assert result["started_new_session"] is True
            _, kwargs = mock_popen.call_args
            assert kwargs["cwd"] == "/custom/path"

    @pytest.mark.asyncio
    async def test_mark_loop_complete_via_executor(self, mock_context):
        """Test mark_loop_complete action through executor."""
        executor = ActionExecutor(
            db=MagicMock(),
            session_manager=mock_context.session_manager,
            template_engine=MagicMock(),
        )

        result = await executor.execute("mark_loop_complete", mock_context)

        assert result["loop_marked_complete"] is True
        assert mock_context.state.variables["stop_reason"] == "completed"
