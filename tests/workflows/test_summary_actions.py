"""
Tests for summary_actions.py - summary generation workflow actions.

Tests cover:
- format_turns_for_llm: Turn formatting for LLM analysis
- synthesize_title: Session title synthesis via LLM
- generate_summary: Session summary generation via LLM
- generate_handoff: Combined summary + status update
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.sessions.analyzer import HandoffContext
from gobby.workflows.summary_actions import (
    _format_structured_context,
    _write_summary_file,
    format_turns_for_llm,
    generate_handoff,
    generate_summary,
    synthesize_title,
)

pytestmark = pytest.mark.unit

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_session_manager():
    """Create a mock session manager."""
    manager = MagicMock()
    return manager


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service with provider chain."""
    service = MagicMock()
    provider = MagicMock()
    provider.generate_text = AsyncMock(return_value="Generated Title")
    provider.generate_summary = AsyncMock(return_value="Generated Summary Content")
    service.get_default_provider.return_value = provider
    return service


@pytest.fixture
def mock_transcript_processor():
    """Create a mock transcript processor."""
    processor = MagicMock()
    processor.extract_turns_since_clear.return_value = []
    processor.extract_last_messages.return_value = []
    return processor


@pytest.fixture
def mock_template_engine():
    """Create a mock template engine."""
    engine = MagicMock()
    engine.render.side_effect = lambda template, context: template.replace(
        "{{ transcript }}", context.get("transcript", "")
    )
    return engine


@pytest.fixture
def sample_transcript_file(tmp_path):
    """Create a sample transcript JSONL file."""
    transcript_file = tmp_path / "transcript.jsonl"
    turns = [
        {"message": {"role": "user", "content": "Hello, can you help me?"}},
        {
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Of course! How can I assist you today?"}],
            }
        },
        {"message": {"role": "user", "content": "I need to refactor some code."}},
    ]
    with open(transcript_file, "w") as f:
        for turn in turns:
            f.write(json.dumps(turn) + "\n")
    return transcript_file


@pytest.fixture
def mock_session(tmp_path):
    """Create a mock session object with transcript path."""
    session = MagicMock()
    transcript_file = tmp_path / "transcript.jsonl"
    # Create a basic transcript
    with open(transcript_file, "w") as f:
        f.write(json.dumps({"message": {"role": "user", "content": "test"}}) + "\n")
    session.jsonl_path = str(transcript_file)
    return session


# =============================================================================
# Tests for format_turns_for_llm
# =============================================================================


class TestFormatTurnsForLlm:
    """Tests for the format_turns_for_llm helper function."""

    def test_format_empty_turns(self) -> None:
        """Test formatting with empty turns list."""
        result = format_turns_for_llm([])
        assert result == ""

    def test_format_user_turn_string_content(self) -> None:
        """Test formatting a user turn with string content."""
        turns = [{"message": {"role": "user", "content": "Hello world"}}]
        result = format_turns_for_llm(turns)
        assert "[Turn 1 - user]: Hello world" in result

    def test_format_assistant_turn_text_block(self) -> None:
        """Test formatting an assistant turn with text block content."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hi there!"}],
                }
            }
        ]
        result = format_turns_for_llm(turns)
        assert "[Turn 1 - assistant]: Hi there!" in result

    def test_format_assistant_turn_thinking_block(self) -> None:
        """Test formatting an assistant turn with thinking block."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [{"type": "thinking", "thinking": "Let me consider..."}],
                }
            }
        ]
        result = format_turns_for_llm(turns)
        assert "[Turn 1 - assistant]: [Thinking: Let me consider...]" in result

    def test_format_assistant_turn_tool_use_block(self) -> None:
        """Test formatting an assistant turn with tool_use block."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "read_file"}],
                }
            }
        ]
        result = format_turns_for_llm(turns)
        assert "[Turn 1 - assistant]: [Tool: read_file]" in result

    def test_format_assistant_turn_mixed_blocks(self) -> None:
        """Test formatting assistant turn with multiple block types."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Let me help."},
                        {"type": "thinking", "thinking": "Analyzing request"},
                        {"type": "tool_use", "name": "search"},
                    ],
                }
            }
        ]
        result = format_turns_for_llm(turns)
        assert "Let me help." in result
        assert "[Thinking: Analyzing request]" in result
        assert "[Tool: search]" in result

    def test_format_multiple_turns(self) -> None:
        """Test formatting multiple turns."""
        turns = [
            {"message": {"role": "user", "content": "First message"}},
            {
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Response"}],
                }
            },
            {"message": {"role": "user", "content": "Second message"}},
        ]
        result = format_turns_for_llm(turns)
        assert "[Turn 1 - user]: First message" in result
        assert "[Turn 2 - assistant]: Response" in result
        assert "[Turn 3 - user]: Second message" in result
        # Check turns are separated by double newlines
        assert "\n\n" in result

    def test_format_turn_missing_message(self) -> None:
        """Test formatting turns with missing message key."""
        turns = [{"other_key": "value"}]
        result = format_turns_for_llm(turns)
        assert "[Turn 1 - unknown]:" in result

    def test_format_turn_missing_role(self) -> None:
        """Test formatting turns with missing role."""
        turns = [{"message": {"content": "No role here"}}]
        result = format_turns_for_llm(turns)
        assert "[Turn 1 - unknown]: No role here" in result

    def test_format_turn_missing_content(self) -> None:
        """Test formatting turns with missing content."""
        turns = [{"message": {"role": "user"}}]
        result = format_turns_for_llm(turns)
        assert "[Turn 1 - user]:" in result

    def test_format_turn_unknown_block_type(self) -> None:
        """Test formatting turns with unknown block type (should be skipped)."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "unknown_type", "data": "something"},
                        {"type": "text", "text": "Known text"},
                    ],
                }
            }
        ]
        result = format_turns_for_llm(turns)
        # Unknown type should be skipped, only text should appear
        assert "Known text" in result
        assert "unknown_type" not in result

    def test_format_turn_tool_use_missing_name(self) -> None:
        """Test formatting tool_use block with missing name."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use"}],  # Missing 'name'
                }
            }
        ]
        result = format_turns_for_llm(turns)
        assert "[Tool: unknown]" in result

    def test_format_turn_non_dict_block(self) -> None:
        """Test formatting with non-dict items in content list."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": ["string item", {"type": "text", "text": "dict item"}],
                }
            }
        ]
        result = format_turns_for_llm(turns)
        # Non-dict items should be skipped
        assert "dict item" in result
        assert "string item" not in result

    def test_format_assistant_turn_tool_result_block(self) -> None:
        """Test formatting an assistant turn with tool_result block."""
        turns = [
            {
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_123",
                            "content": "File contents here",
                        }
                    ],
                }
            }
        ]
        result = format_turns_for_llm(turns)
        assert "[Turn 1 - user]: [Result: File contents here]" in result

    def test_format_tool_result_truncates_long_content(self) -> None:
        """Test that tool_result content is truncated to 200 chars (default limit)."""
        long_content = "x" * 500  # 500 characters
        turns = [
            {
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_123",
                            "content": long_content,
                        }
                    ],
                }
            }
        ]
        result = format_turns_for_llm(turns)
        # Should show first 200 chars followed by "..."
        assert "[Result: " + "x" * 200 + "...]" in result
        # Should NOT contain the full 500 chars
        assert "x" * 500 not in result


# =============================================================================
# Tests for synthesize_title
# =============================================================================


class TestSynthesizeTitle:
    """Tests for the synthesize_title async function."""

    @pytest.mark.asyncio
    async def test_synthesize_title_success(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        mock_template_engine,
        tmp_path,
    ):
        """Test successful title synthesis."""
        # Create transcript file
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Help me"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        result = await synthesize_title(
            session_manager=mock_session_manager,
            session_id="test-session-123",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            template_engine=mock_template_engine,
        )

        assert result is not None
        assert "title_synthesized" in result
        assert result["title_synthesized"] == "Generated Title"
        mock_session_manager.update_title.assert_called_once_with(
            "test-session-123", "Generated Title"
        )

    @pytest.mark.asyncio
    async def test_synthesize_title_missing_llm_service(
        self, mock_session_manager, mock_transcript_processor, mock_template_engine
    ):
        """Test title synthesis with missing LLM service."""
        result = await synthesize_title(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=None,
            transcript_processor=mock_transcript_processor,
            template_engine=mock_template_engine,
        )

        assert result == {"error": "Missing LLM service"}

    @pytest.mark.asyncio
    async def test_synthesize_title_missing_transcript_processor(
        self, mock_session_manager, mock_llm_service, mock_template_engine
    ):
        """Test title synthesis with missing transcript processor.

        Note: synthesize_title doesn't actually use transcript_processor directly -
        it reads the transcript file itself. When the session has no valid jsonl_path,
        it returns 'Empty transcript'.
        """
        # Mock session returns a MagicMock which has a truthy jsonl_path, but that
        # path doesn't exist, so turns will be empty
        result = await synthesize_title(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=None,
            template_engine=mock_template_engine,
        )

        assert result == {"error": "Empty transcript"}

    @pytest.mark.asyncio
    async def test_synthesize_title_session_not_found(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        mock_template_engine,
    ):
        """Test title synthesis when session is not found."""
        mock_session_manager.get.return_value = None

        result = await synthesize_title(
            session_manager=mock_session_manager,
            session_id="nonexistent-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            template_engine=mock_template_engine,
        )

        assert result == {"error": "Session not found"}

    @pytest.mark.asyncio
    async def test_synthesize_title_no_transcript_path(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        mock_template_engine,
    ):
        """Test title synthesis when session has no transcript path."""
        session = MagicMock()
        session.jsonl_path = None
        mock_session_manager.get.return_value = session

        result = await synthesize_title(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            template_engine=mock_template_engine,
        )

        assert result == {"error": "No transcript path and no prompt provided"}

    @pytest.mark.asyncio
    async def test_synthesize_title_empty_transcript(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        mock_template_engine,
        tmp_path,
    ):
        """Test title synthesis with empty transcript file."""
        # Create empty transcript file
        transcript_file = tmp_path / "empty_transcript.jsonl"
        transcript_file.touch()

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        result = await synthesize_title(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            template_engine=mock_template_engine,
        )

        assert result == {"error": "Empty transcript"}

    @pytest.mark.asyncio
    async def test_synthesize_title_nonexistent_transcript_file(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        mock_template_engine,
        tmp_path,
    ):
        """Test title synthesis when transcript file doesn't exist."""
        session = MagicMock()
        session.jsonl_path = str(tmp_path / "nonexistent.jsonl")
        mock_session_manager.get.return_value = session

        result = await synthesize_title(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            template_engine=mock_template_engine,
        )

        # File doesn't exist, so turns will be empty
        assert result == {"error": "Empty transcript"}

    @pytest.mark.asyncio
    async def test_synthesize_title_with_custom_template(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        mock_template_engine,
        tmp_path,
    ):
        """Test title synthesis with custom template."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        custom_template = "Generate a creative title: {{ transcript }}"

        result = await synthesize_title(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            template_engine=mock_template_engine,
            template=custom_template,
        )

        assert result is not None
        assert "title_synthesized" in result
        # Verify template engine was called with custom template
        mock_template_engine.render.assert_called()

    @pytest.mark.asyncio
    async def test_synthesize_title_strips_quotes(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        mock_template_engine,
        tmp_path,
    ):
        """Test that title synthesis strips quotes from LLM response."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        # LLM returns title with quotes
        provider = mock_llm_service.get_default_provider()
        provider.generate_text.return_value = '"Quoted Title"'

        result = await synthesize_title(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            template_engine=mock_template_engine,
        )

        assert result["title_synthesized"] == "Quoted Title"

    @pytest.mark.asyncio
    async def test_synthesize_title_strips_single_quotes(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        mock_template_engine,
        tmp_path,
    ):
        """Test that title synthesis strips single quotes from LLM response."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        provider = mock_llm_service.get_default_provider()
        provider.generate_text.return_value = "'Single Quoted'"

        result = await synthesize_title(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            template_engine=mock_template_engine,
        )

        assert result["title_synthesized"] == "Single Quoted"

    @pytest.mark.asyncio
    async def test_synthesize_title_llm_exception(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        mock_template_engine,
        tmp_path,
    ):
        """Test title synthesis when LLM raises exception."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        provider = mock_llm_service.get_default_provider()
        provider.generate_text.side_effect = Exception("LLM API Error")

        result = await synthesize_title(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            template_engine=mock_template_engine,
        )

        assert "error" in result
        assert "LLM API Error" in result["error"]

    @pytest.mark.asyncio
    async def test_synthesize_title_reads_limited_turns(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        mock_template_engine,
        tmp_path,
    ):
        """Test that title synthesis reads only first 20 turns."""
        transcript_file = tmp_path / "transcript.jsonl"
        # Create 30 turns
        with open(transcript_file, "w") as f:
            for i in range(30):
                f.write(json.dumps({"message": {"role": "user", "content": f"Message {i}"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        await synthesize_title(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            template_engine=mock_template_engine,
        )

        # Verify template engine received formatted turns (limited to 20)
        mock_template_engine.render.assert_called_once()
        call_args = mock_template_engine.render.call_args
        transcript_arg = call_args[0][1].get("transcript", "")
        # The loop reads indices 0-19 (breaks at i >= 20), so Messages 0-19 are included
        assert "Message 0" in transcript_arg
        assert "Message 19" in transcript_arg  # Last message that IS included
        # Messages 20+ should NOT be included (loop breaks at i=20)
        assert "Message 20" not in transcript_arg
        assert "Message 25" not in transcript_arg

    @pytest.mark.asyncio
    async def test_synthesize_title_handles_blank_lines(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        mock_template_engine,
        tmp_path,
    ):
        """Test that title synthesis skips blank lines in transcript."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "First"}}) + "\n")
            f.write("\n")  # Blank line
            f.write("   \n")  # Whitespace-only line
            f.write(json.dumps({"message": {"role": "user", "content": "Second"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        result = await synthesize_title(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            template_engine=mock_template_engine,
        )

        assert result is not None
        assert "title_synthesized" in result


# =============================================================================
# Tests for _rename_tmux_window
# =============================================================================


class TestRenameTmuxWindow:
    """Tests for _rename_tmux_window helper."""

    @pytest.mark.asyncio
    async def test_skips_when_no_terminal_context(self):
        """No-op when session has no terminal_context."""
        from gobby.workflows.summary_actions import _rename_tmux_window

        session = MagicMock()
        session.terminal_context = None
        # Should not raise
        await _rename_tmux_window(session, "Title")

    @pytest.mark.asyncio
    async def test_skips_when_no_tmux_pane(self):
        """No-op when terminal_context has no tmux_pane."""
        from gobby.workflows.summary_actions import _rename_tmux_window

        session = MagicMock()
        session.terminal_context = {"parent_pid": 123}
        await _rename_tmux_window(session, "Title")

    @pytest.mark.asyncio
    async def test_user_session_renames_on_default_server(self):
        """User session (depth 0) calls tmux rename-window on default server."""
        from gobby.workflows.summary_actions import _rename_tmux_window

        session = MagicMock()
        session.terminal_context = {"tmux_pane": "%42"}
        session.agent_depth = 0

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            await _rename_tmux_window(session, "My Title")

            mock_exec.assert_called_once_with(
                "tmux",
                "set-option", "-g", "set-titles", "on", ";",
                "set-option", "-g", "set-titles-string", "#W", ";",
                "rename-window", "-t", "%42", "My Title", ";",
                "set-option", "-w", "-t", "%42", "automatic-rename", "off",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

    @pytest.mark.asyncio
    async def test_spawned_agent_renames_on_gobby_socket(self):
        """Spawned agent (depth > 0) uses TmuxSessionManager."""
        from gobby.workflows.summary_actions import _rename_tmux_window

        session = MagicMock()
        session.terminal_context = {"tmux_pane": "%0"}
        session.agent_depth = 1

        mock_mgr = AsyncMock()
        mock_mgr.rename_window.return_value = True

        with patch(
            "gobby.agents.tmux.get_tmux_session_manager",
            return_value=mock_mgr,
        ):
            await _rename_tmux_window(session, "Agent Title")
            mock_mgr.rename_window.assert_called_once_with("%0", "Agent Title")

    @pytest.mark.asyncio
    async def test_failure_does_not_propagate(self):
        """Rename failures are swallowed, never propagated."""
        from gobby.workflows.summary_actions import _rename_tmux_window

        session = MagicMock()
        session.terminal_context = {"tmux_pane": "%42"}
        session.agent_depth = 0

        with patch("asyncio.create_subprocess_exec", side_effect=OSError("no tmux")):
            # Should not raise
            await _rename_tmux_window(session, "Title")


# =============================================================================
# Tests for generate_summary
# =============================================================================


class TestGenerateSummary:
    """Tests for the generate_summary async function."""

    @pytest.mark.asyncio
    async def test_generate_summary_success(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test successful summary generation."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Help me"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = [
            {"message": {"role": "user", "content": "Help me"}}
        ]
        mock_transcript_processor.extract_last_messages.return_value = []

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="clean"),
            patch("gobby.workflows.summary_actions.get_file_changes", return_value="No changes"),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_summary(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
            )

        assert result is not None
        assert result["summary_generated"] is True
        assert result["summary_length"] == len("Generated Summary Content")
        mock_session_manager.update_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_summary_invalid_mode(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
    ):
        """Test that invalid mode raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await generate_summary(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
                mode="invalid_mode",  # type: ignore
            )

        assert "Invalid mode 'invalid_mode'" in str(exc_info.value)
        assert "clear" in str(exc_info.value)
        assert "compact" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_summary_clear_mode(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test summary generation in clear mode."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = [
            {"message": {"role": "user", "content": "Test"}}
        ]
        mock_transcript_processor.extract_last_messages.return_value = []

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="clean"),
            patch("gobby.workflows.summary_actions.get_file_changes", return_value="No changes"),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_summary(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
                mode="clear",
            )

        assert result["summary_generated"] is True
        # Verify mode was passed in LLM context
        provider = mock_llm_service.get_default_provider()
        call_kwargs = provider.generate_summary.call_args.kwargs
        assert call_kwargs["context"]["mode"] == "clear"

    @pytest.mark.asyncio
    async def test_generate_summary_compact_mode(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test summary generation in compact mode."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = [
            {"message": {"role": "user", "content": "Test"}}
        ]
        mock_transcript_processor.extract_last_messages.return_value = []

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="clean"),
            patch("gobby.workflows.summary_actions.get_file_changes", return_value="No changes"),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_summary(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
                mode="compact",
            )

        assert result["summary_generated"] is True
        provider = mock_llm_service.get_default_provider()
        call_kwargs = provider.generate_summary.call_args.kwargs
        assert call_kwargs["context"]["mode"] == "compact"

    @pytest.mark.asyncio
    async def test_generate_summary_with_previous_summary(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test summary generation with previous summary for cumulative compression."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = []
        mock_transcript_processor.extract_last_messages.return_value = []

        previous = "Previous session summary content"

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="clean"),
            patch("gobby.workflows.summary_actions.get_file_changes", return_value="No changes"),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_summary(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
                previous_summary=previous,
                mode="compact",
            )

        assert result["summary_generated"] is True
        provider = mock_llm_service.get_default_provider()
        call_kwargs = provider.generate_summary.call_args.kwargs
        assert call_kwargs["context"]["previous_summary"] == previous

    @pytest.mark.asyncio
    async def test_generate_summary_missing_services(
        self,
        mock_session_manager,
        mock_transcript_processor,
    ):
        """Test summary generation with missing LLM service."""
        result = await generate_summary(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=None,
            transcript_processor=mock_transcript_processor,
        )

        assert result == {"error": "Missing services"}

    @pytest.mark.asyncio
    async def test_generate_summary_missing_transcript_processor(
        self,
        mock_session_manager,
        mock_llm_service,
    ):
        """Test summary generation with missing transcript processor."""
        result = await generate_summary(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=None,
        )

        assert result == {"error": "Missing services"}

    @pytest.mark.asyncio
    async def test_generate_summary_session_not_found(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
    ):
        """Test summary generation when session is not found."""
        mock_session_manager.get.return_value = None

        result = await generate_summary(
            session_manager=mock_session_manager,
            session_id="nonexistent",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
        )

        assert result == {"error": "Session not found"}

    @pytest.mark.asyncio
    async def test_generate_summary_no_transcript_path(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
    ):
        """Test summary generation when session has no transcript path."""
        session = MagicMock()
        session.jsonl_path = None
        mock_session_manager.get.return_value = session

        result = await generate_summary(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
        )

        assert result == {"error": "No transcript path"}

    @pytest.mark.asyncio
    async def test_generate_summary_transcript_not_found(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test summary generation when transcript file doesn't exist."""
        session = MagicMock()
        session.jsonl_path = str(tmp_path / "nonexistent.jsonl")
        mock_session_manager.get.return_value = session

        result = await generate_summary(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
        )

        assert result == {"error": "Transcript not found"}

    @pytest.mark.asyncio
    async def test_generate_summary_transcript_processing_error(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test summary generation when transcript processing fails."""
        transcript_file = tmp_path / "bad_transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write("invalid json content\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        result = await generate_summary(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_generate_summary_llm_error(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test summary generation when LLM call fails."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = []
        mock_transcript_processor.extract_last_messages.return_value = []

        provider = mock_llm_service.get_default_provider()
        provider.generate_summary.side_effect = Exception("LLM API Error")

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="clean"),
            patch("gobby.workflows.summary_actions.get_file_changes", return_value="No changes"),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_summary(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
            )

        assert "error" in result
        assert "LLM error" in result["error"]

    @pytest.mark.asyncio
    async def test_generate_summary_with_custom_template(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test summary generation with custom template."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = []
        mock_transcript_processor.extract_last_messages.return_value = []

        custom_template = "Custom summary template: {transcript_summary}"

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="clean"),
            patch("gobby.workflows.summary_actions.get_file_changes", return_value="No changes"),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_summary(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
                template=custom_template,
            )

        assert result["summary_generated"] is True
        provider = mock_llm_service.get_default_provider()
        call_kwargs = provider.generate_summary.call_args.kwargs
        assert call_kwargs["prompt_template"] == custom_template

    @pytest.mark.asyncio
    async def test_generate_summary_includes_git_context(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test that summary generation includes git status and file changes."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = []
        mock_transcript_processor.extract_last_messages.return_value = []

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="M file.py"),
            patch(
                "gobby.workflows.summary_actions.get_file_changes",
                return_value="Modified/Deleted:\nM\tfile.py",
            ),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_summary(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
            )

        assert result["summary_generated"] is True
        provider = mock_llm_service.get_default_provider()
        call_kwargs = provider.generate_summary.call_args.kwargs
        assert call_kwargs["context"]["git_status"] == "M file.py"
        assert "file.py" in call_kwargs["context"]["file_changes"]

    @pytest.mark.asyncio
    async def test_generate_summary_includes_last_messages(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test that summary generation includes last messages in context."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        last_messages = [
            {"message": {"role": "user", "content": "Final question"}},
            {"message": {"role": "assistant", "content": "Final answer"}},
        ]
        mock_transcript_processor.extract_turns_since_clear.return_value = []
        mock_transcript_processor.extract_last_messages.return_value = last_messages

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="clean"),
            patch("gobby.workflows.summary_actions.get_file_changes", return_value="No changes"),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_summary(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
            )

        assert result["summary_generated"] is True
        provider = mock_llm_service.get_default_provider()
        call_kwargs = provider.generate_summary.call_args.kwargs
        assert "Final question" in call_kwargs["context"]["last_messages"]


# =============================================================================
# Tests for generate_handoff
# =============================================================================


class TestGenerateHandoff:
    """Tests for the generate_handoff async function."""

    @pytest.mark.asyncio
    async def test_generate_handoff_success(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test successful handoff generation."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = []
        mock_transcript_processor.extract_last_messages.return_value = []

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="clean"),
            patch("gobby.workflows.summary_actions.get_file_changes", return_value="No changes"),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_handoff(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
            )

        assert result is not None
        assert result["handoff_created"] is True
        assert result["summary_length"] == len("Generated Summary Content")
        mock_session_manager.update_status.assert_called_once_with("test-session", "handoff_ready")

    @pytest.mark.asyncio
    async def test_generate_handoff_propagates_summary_error(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
    ):
        """Test that handoff propagates errors from generate_summary."""
        mock_session_manager.get.return_value = None  # Session not found

        result = await generate_handoff(
            session_manager=mock_session_manager,
            session_id="nonexistent",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
        )

        assert result == {"error": "Session not found"}
        mock_session_manager.update_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_handoff_with_mode(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test handoff generation with mode parameter."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = []
        mock_transcript_processor.extract_last_messages.return_value = []

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="clean"),
            patch("gobby.workflows.summary_actions.get_file_changes", return_value="No changes"),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_handoff(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
                mode="compact",
            )

        assert result["handoff_created"] is True
        provider = mock_llm_service.get_default_provider()
        call_kwargs = provider.generate_summary.call_args.kwargs
        assert call_kwargs["context"]["mode"] == "compact"

    @pytest.mark.asyncio
    async def test_generate_handoff_invalid_mode(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
    ):
        """Test that handoff with invalid mode raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await generate_handoff(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
                mode="bad_mode",  # type: ignore
            )

        assert "Invalid mode 'bad_mode'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_handoff_with_previous_summary(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test handoff generation with previous summary."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = []
        mock_transcript_processor.extract_last_messages.return_value = []

        previous = "Previous summary"

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="clean"),
            patch("gobby.workflows.summary_actions.get_file_changes", return_value="No changes"),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_handoff(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
                previous_summary=previous,
                mode="compact",
            )

        assert result["handoff_created"] is True
        provider = mock_llm_service.get_default_provider()
        call_kwargs = provider.generate_summary.call_args.kwargs
        assert call_kwargs["context"]["previous_summary"] == previous

    @pytest.mark.asyncio
    async def test_generate_handoff_with_custom_template(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test handoff generation with custom template."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = []
        mock_transcript_processor.extract_last_messages.return_value = []

        custom_template = "Handoff template: {transcript_summary}"

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="clean"),
            patch("gobby.workflows.summary_actions.get_file_changes", return_value="No changes"),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_handoff(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
                template=custom_template,
            )

        assert result["handoff_created"] is True
        provider = mock_llm_service.get_default_provider()
        call_kwargs = provider.generate_summary.call_args.kwargs
        assert call_kwargs["prompt_template"] == custom_template

    @pytest.mark.asyncio
    async def test_generate_handoff_missing_services(
        self,
        mock_session_manager,
        mock_transcript_processor,
    ):
        """Test handoff generation with missing LLM service."""
        result = await generate_handoff(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=None,
            transcript_processor=mock_transcript_processor,
        )

        assert result == {"error": "Missing services"}
        mock_session_manager.update_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_handoff_summary_returns_none(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test handoff generation when generate_summary returns None."""
        # This tests the edge case where summary_result is None (not a dict with error)
        # We need to patch generate_summary to return None
        with patch(
            "gobby.workflows.summary_actions.generate_summary",
            new_callable=AsyncMock,
        ) as mock_gen_summary:
            mock_gen_summary.return_value = None

            result = await generate_handoff(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
            )

        assert result == {"error": "Failed to generate summary"}
        mock_session_manager.update_status.assert_called_once_with("test-session", "handoff_ready")

    @pytest.mark.asyncio
    async def test_generate_handoff_zero_summary_length(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test handoff generation when summary has no summary_length key."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = []
        mock_transcript_processor.extract_last_messages.return_value = []

        # Mock generate_summary to return result without summary_length
        with patch(
            "gobby.workflows.summary_actions.generate_summary",
            new_callable=AsyncMock,
        ) as mock_gen_summary:
            mock_gen_summary.return_value = {"summary_generated": True}  # No summary_length

            result = await generate_handoff(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
            )

        assert result["handoff_created"] is True
        assert result["summary_length"] == 0  # Default when key missing


# =============================================================================
# Integration Tests
# =============================================================================


class TestSummaryActionsIntegration:
    """Integration tests that test multiple functions together."""

    @pytest.mark.asyncio
    async def test_full_handoff_workflow(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ):
        """Test a complete handoff workflow from transcript to handoff."""
        # Create a realistic transcript
        transcript_file = tmp_path / "transcript.jsonl"
        turns = [
            {"message": {"role": "user", "content": "Help me refactor this code"}},
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "Analyzing the request"},
                        {
                            "type": "text",
                            "text": "I'll help you refactor. Let me look at the code.",
                        },
                        {"type": "tool_use", "name": "read_file"},
                    ],
                }
            },
            {"message": {"role": "user", "content": "Thanks, that looks good!"}},
        ]
        with open(transcript_file, "w") as f:
            for turn in turns:
                f.write(json.dumps(turn) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = turns
        mock_transcript_processor.extract_last_messages.return_value = turns[-2:]

        provider = mock_llm_service.get_default_provider()
        provider.generate_summary.return_value = "Session focused on code refactoring."

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="M src/main.py"),
            patch(
                "gobby.workflows.summary_actions.get_file_changes",
                return_value="Modified/Deleted:\nM\tsrc/main.py",
            ),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_handoff(
                session_manager=mock_session_manager,
                session_id="session-123",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
            )

        assert result["handoff_created"] is True
        assert result["summary_length"] == len("Session focused on code refactoring.")
        mock_session_manager.update_summary.assert_called_once()
        mock_session_manager.update_status.assert_called_once_with("session-123", "handoff_ready")

    @pytest.mark.asyncio
    async def test_title_then_summary_workflow(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        mock_template_engine,
        tmp_path,
    ):
        """Test synthesizing title and then generating summary."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(
                json.dumps({"message": {"role": "user", "content": "Fix the authentication bug"}})
                + "\n"
            )

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = []
        mock_transcript_processor.extract_last_messages.return_value = []

        # First synthesize title
        title_result = await synthesize_title(
            session_manager=mock_session_manager,
            session_id="session-456",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            template_engine=mock_template_engine,
        )

        assert title_result is not None
        assert "title_synthesized" in title_result

        # Then generate summary
        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="clean"),
            patch("gobby.workflows.summary_actions.get_file_changes", return_value="No changes"),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            summary_result = await generate_summary(
                session_manager=mock_session_manager,
                session_id="session-456",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
            )

        assert summary_result["summary_generated"] is True


# =============================================================================
# Tests for _write_summary_file
# =============================================================================


class TestWriteSummaryFile:
    """Tests for the _write_summary_file helper function."""

    @pytest.mark.asyncio
    async def test_write_summary_file_creates_file(self, tmp_path) -> None:
        """Test that _write_summary_file creates a summary file."""
        output_dir = str(tmp_path / "session_summaries")

        result = await _write_summary_file(
            session_id="test-session-123",
            content="# Test Summary\n\nTest content",
            output_path=output_dir,
        )

        assert result is not None
        from pathlib import Path

        written = Path(result)
        assert written.exists()
        assert written.read_text() == "# Test Summary\n\nTest content"

    @pytest.mark.asyncio
    async def test_write_summary_file_creates_directory(self, tmp_path) -> None:
        """Test that _write_summary_file creates the output directory."""
        output_dir = str(tmp_path / "nested" / "summaries")

        result = await _write_summary_file(
            session_id="test-session",
            content="Content",
            output_path=output_dir,
        )

        assert result is not None
        from pathlib import Path

        assert Path(output_dir).exists()

    @pytest.mark.asyncio
    async def test_write_summary_file_uses_external_id(self, tmp_path) -> None:
        """Test that _write_summary_file uses external_id in filename."""
        output_dir = str(tmp_path / "summaries")

        mock_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.external_id = "ext-abc-123"
        mock_manager.get.return_value = mock_session

        result = await _write_summary_file(
            session_id="internal-id",
            content="Content",
            output_path=output_dir,
            session_manager=mock_manager,
        )

        assert result is not None
        assert "ext-abc-123" in result
        assert "internal-id" not in result

    @pytest.mark.asyncio
    async def test_write_summary_file_falls_back_to_session_id(self, tmp_path) -> None:
        """Test fallback to session_id when external_id unavailable."""
        output_dir = str(tmp_path / "summaries")

        result = await _write_summary_file(
            session_id="fallback-session-id",
            content="Content",
            output_path=output_dir,
            session_manager=None,
        )

        assert result is not None
        assert "fallback-session-id" in result

    @pytest.mark.asyncio
    async def test_write_summary_file_naming_format(self, tmp_path) -> None:
        """Test that files follow session_{timestamp}_{id}.md format."""
        output_dir = str(tmp_path / "summaries")

        result = await _write_summary_file(
            session_id="my-session",
            content="Content",
            output_path=output_dir,
        )

        assert result is not None
        from pathlib import Path

        filename = Path(result).name
        assert filename.startswith("session_")
        assert filename.endswith(".md")
        assert "my-session" in filename

    @pytest.mark.asyncio
    async def test_write_summary_file_error_returns_none(self, monkeypatch, tmp_path) -> None:
        """Test that write errors return None."""
        monkeypatch.setattr(
            "pathlib.Path.mkdir",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("mocked")),
        )

        result = await _write_summary_file(
            session_id="test",
            content="Content",
            output_path=str(tmp_path / "test_summary"),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_generate_summary_with_write_file(
        self,
        mock_session_manager,
        mock_llm_service,
        mock_transcript_processor,
        tmp_path,
    ) -> None:
        """Test generate_summary with write_file=True produces a file."""
        transcript_file = tmp_path / "transcript.jsonl"
        with open(transcript_file, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Test"}}) + "\n")

        session = MagicMock()
        session.jsonl_path = str(transcript_file)
        session.external_id = "ext-write-test"
        mock_session_manager.get.return_value = session

        mock_transcript_processor.extract_turns_since_clear.return_value = []
        mock_transcript_processor.extract_last_messages.return_value = []

        output_dir = str(tmp_path / "write_test_summaries")

        with (
            patch("gobby.workflows.summary_actions.get_git_status", return_value="clean"),
            patch("gobby.workflows.summary_actions.get_file_changes", return_value="No changes"),
            patch("gobby.workflows.summary_actions.get_git_diff_summary", return_value=""),
        ):
            result = await generate_summary(
                session_manager=mock_session_manager,
                session_id="test-session",
                llm_service=mock_llm_service,
                transcript_processor=mock_transcript_processor,
                write_file=True,
                output_path=output_dir,
            )

        assert result is not None
        assert result["summary_generated"] is True
        assert "summary_file" in result
        from pathlib import Path

        assert Path(result["summary_file"]).exists()
        assert "ext-write-test" in result["summary_file"]


# =============================================================================
# Tests for _format_structured_context
# =============================================================================


class TestFormatStructuredContext:
    """Tests for the _format_structured_context helper function."""

    def test_format_structured_context_with_task_progress(self) -> None:
        """Test that task_progress is formatted with task IDs and actions."""
        ctx = HandoffContext(
            task_progress=[
                {"id": "gt-001", "action": "create_task", "title": "Fix login bug"},
                {"id": "gt-001", "action": "claim_task", "title": "Task gt-001"},
                {"id": "gt-001", "action": "close_task", "title": "Task gt-001"},
            ]
        )
        result = _format_structured_context(ctx)

        assert "Task Progress:" in result
        assert "create_task: Fix login bug (gt-001)" in result
        assert "claim_task: Task gt-001 (gt-001)" in result
        assert "close_task: Task gt-001 (gt-001)" in result

    def test_format_structured_context_empty(self) -> None:
        """Test that empty HandoffContext returns empty string."""
        ctx = HandoffContext()
        result = _format_structured_context(ctx)
        assert result == ""

    def test_format_structured_context_caps_task_progress(self) -> None:
        """Test that task_progress is capped at 15 entries."""
        ctx = HandoffContext(
            task_progress=[
                {"id": f"gt-{i:03d}", "action": "update_task", "title": f"Task {i}"}
                for i in range(20)
            ]
        )
        result = _format_structured_context(ctx)

        assert "Task Progress:" in result
        # Should only show the last 15 (indices 5-19)
        assert "Task 5" in result
        assert "Task 19" in result
        # First 5 should be excluded
        assert "gt-000" not in result
        assert "gt-004" not in result
        # Count the lines
        progress_section = result.split("Task Progress:\n")[1]
        lines = [line for line in progress_section.split("\n") if line.strip().startswith("- ")]
        assert len(lines) == 15

    def test_format_structured_context_task_progress_with_other_fields(self) -> None:
        """Test that task_progress coexists with other context fields."""
        ctx = HandoffContext(
            active_gobby_task={"id": "gt-001", "title": "Active task", "status": "in_progress"},
            task_progress=[
                {"id": "gt-001", "action": "claim_task", "title": "Active task"},
            ],
            initial_goal="Fix all the bugs",
        )
        result = _format_structured_context(ctx)

        assert "Active Task:" in result
        assert "Task Progress:" in result
        assert "Original Goal:" in result
