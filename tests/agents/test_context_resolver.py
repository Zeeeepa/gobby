"""Tests for ContextResolver class."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.agents.context import (
    ContextResolutionError,
    ContextResolver,
    format_injected_prompt,
)


@pytest.fixture
def mock_session_manager():
    """Create a mock session manager."""
    return MagicMock()


@pytest.fixture
def mock_message_manager():
    """Create a mock message manager."""
    return MagicMock()


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def resolver(mock_session_manager, mock_message_manager, temp_project):
    """Create a ContextResolver instance."""
    return ContextResolver(
        session_manager=mock_session_manager,
        message_manager=mock_message_manager,
        project_path=temp_project,
    )


class TestResolveSummaryMarkdown:
    """Tests for summary_markdown resolution."""

    async def test_returns_summary(self, resolver, mock_session_manager):
        """summary_markdown returns session summary."""
        mock_session = MagicMock()
        mock_session.summary_markdown = "# Summary\n\nThis is a summary."
        mock_session_manager.get.return_value = mock_session

        result = await resolver.resolve("summary_markdown", "sess-123")

        assert result == "# Summary\n\nThis is a summary."
        mock_session_manager.get.assert_called_once_with("sess-123")

    async def test_returns_empty_when_none(self, resolver, mock_session_manager):
        """summary_markdown returns empty string when None."""
        mock_session = MagicMock()
        mock_session.summary_markdown = None
        mock_session_manager.get.return_value = mock_session

        result = await resolver.resolve("summary_markdown", "sess-123")

        assert result == ""

    async def test_raises_on_missing_session(self, resolver, mock_session_manager):
        """summary_markdown raises error for missing session."""
        mock_session_manager.get.return_value = None

        with pytest.raises(ContextResolutionError) as exc_info:
            await resolver.resolve("summary_markdown", "sess-unknown")

        assert "Session not found: sess-unknown" in str(exc_info.value)


class TestResolveCompactMarkdown:
    """Tests for compact_markdown resolution."""

    async def test_returns_handoff_context(self, resolver, mock_session_manager):
        """compact_markdown returns handoff context."""
        mock_session = MagicMock()
        mock_session.compact_markdown = "## Handoff\n\nContext here."
        mock_session_manager.get.return_value = mock_session

        result = await resolver.resolve("compact_markdown", "sess-123")

        assert result == "## Handoff\n\nContext here."

    async def test_returns_empty_when_none(self, resolver, mock_session_manager):
        """compact_markdown returns empty string when None."""
        mock_session = MagicMock()
        mock_session.compact_markdown = None
        mock_session_manager.get.return_value = mock_session

        result = await resolver.resolve("compact_markdown", "sess-123")

        assert result == ""


class TestResolveSessionId:
    """Tests for session_id:<id> resolution."""

    async def test_fetches_correct_session(self, resolver, mock_session_manager):
        """session_id:<id> fetches the correct session."""
        mock_session = MagicMock()
        mock_session.summary_markdown = "Target session summary"
        mock_session_manager.get.return_value = mock_session

        result = await resolver.resolve("session_id:sess-target", "sess-parent")

        # Should fetch the target session, not the parent
        mock_session_manager.get.assert_called_once_with("sess-target")
        assert result == "Target session summary"

    async def test_raises_on_missing_session(self, resolver, mock_session_manager):
        """session_id:<id> raises error for non-existent session."""
        mock_session_manager.get.return_value = None

        with pytest.raises(ContextResolutionError) as exc_info:
            await resolver.resolve("session_id:sess-missing", "sess-parent")

        assert "Session not found: sess-missing" in str(exc_info.value)


class TestResolveTranscript:
    """Tests for transcript:<n> resolution."""

    async def test_returns_last_n_messages(self, resolver, mock_message_manager):
        """transcript:<n> returns correct number of messages."""
        mock_message_manager.get_messages = AsyncMock(
            return_value=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "Thanks"},
            ]
        )

        result = await resolver.resolve("transcript:3", "sess-123")

        mock_message_manager.get_messages.assert_called_once_with(
            session_id="sess-123",
            limit=3,
            offset=0,
        )
        assert "**user**: Hello" in result
        assert "**assistant**: Hi there!" in result
        assert "**user**: Thanks" in result

    async def test_returns_empty_for_no_messages(self, resolver, mock_message_manager):
        """transcript:<n> returns empty string when no messages."""
        mock_message_manager.get_messages = AsyncMock(return_value=[])

        result = await resolver.resolve("transcript:10", "sess-123")

        assert result == ""

    async def test_clamps_to_max(self, resolver, mock_message_manager):
        """transcript:<n> clamps to max_transcript_messages."""
        resolver._max_transcript_messages = 50
        mock_message_manager.get_messages = AsyncMock(return_value=[])

        await resolver.resolve("transcript:1000", "sess-123")

        mock_message_manager.get_messages.assert_called_once_with(
            session_id="sess-123",
            limit=50,
            offset=0,
        )


class TestResolveFile:
    """Tests for file:<path> resolution."""

    async def test_reads_file_correctly(self, resolver, temp_project):
        """file:<path> reads file content correctly."""
        test_file = temp_project / "test.md"
        test_file.write_text("# Test File\n\nContent here.")

        result = await resolver.resolve("file:test.md", "sess-123")

        assert result == "# Test File\n\nContent here."

    async def test_rejects_path_traversal(self, resolver):
        """file:<path> rejects path traversal attempts."""
        with pytest.raises(ContextResolutionError) as exc_info:
            await resolver.resolve("file:../etc/passwd", "sess-123")

        assert "Path traversal not allowed" in str(exc_info.value)

    async def test_rejects_outside_project(self, resolver, temp_project):
        """file:<path> rejects paths outside project."""
        # Create a file outside project using absolute path trick
        with pytest.raises(ContextResolutionError) as exc_info:
            await resolver.resolve("file:/etc/passwd", "sess-123")

        # Could raise absolute path, traversal, or outside project error
        error_msg = str(exc_info.value).lower()
        assert "absolute" in error_msg or "traversal" in error_msg or "outside" in error_msg

    async def test_raises_on_missing_file(self, resolver):
        """file:<path> raises error for non-existent file."""
        with pytest.raises(ContextResolutionError) as exc_info:
            await resolver.resolve("file:nonexistent.md", "sess-123")

        assert "File not found" in str(exc_info.value)

    async def test_truncates_large_files(self, resolver, temp_project):
        """file:<path> truncates files over max size."""
        resolver._max_file_size = 100
        test_file = temp_project / "large.txt"
        test_file.write_text("A" * 200)

        result = await resolver.resolve("file:large.txt", "sess-123")

        assert len(result) < 200
        assert "truncated" in result
        assert "100 bytes remaining" in result

    async def test_rejects_binary_files(self, resolver, temp_project):
        """file:<path> rejects binary (non-UTF-8) files."""
        test_file = temp_project / "binary.bin"
        test_file.write_bytes(b"\x00\x01\x02\xff\xfe")

        with pytest.raises(ContextResolutionError) as exc_info:
            await resolver.resolve("file:binary.bin", "sess-123")

        assert "not valid UTF-8" in str(exc_info.value) or "binary" in str(exc_info.value)

    async def test_requires_project_path(self, mock_session_manager, mock_message_manager):
        """file:<path> requires project path to be configured."""
        resolver = ContextResolver(
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
            project_path=None,
        )

        with pytest.raises(ContextResolutionError) as exc_info:
            await resolver.resolve("file:test.md", "sess-123")

        assert "No project path configured" in str(exc_info.value)


class TestContentTruncation:
    """Tests for content truncation across all source types."""

    async def test_truncates_long_summary_markdown(
        self, mock_session_manager, mock_message_manager, temp_project
    ):
        """summary_markdown is truncated when over limit."""
        resolver = ContextResolver(
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
            project_path=temp_project,
            max_content_size=100,
        )

        mock_session = MagicMock()
        mock_session.summary_markdown = "A" * 200
        mock_session_manager.get.return_value = mock_session

        result = await resolver.resolve("summary_markdown", "sess-123")

        assert len(result) < 200
        assert "truncated" in result
        assert "100 bytes remaining" in result

    async def test_truncates_long_compact_markdown(
        self, mock_session_manager, mock_message_manager, temp_project
    ):
        """compact_markdown is truncated when over limit."""
        resolver = ContextResolver(
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
            project_path=temp_project,
            max_content_size=100,
        )

        mock_session = MagicMock()
        mock_session.compact_markdown = "B" * 200
        mock_session_manager.get.return_value = mock_session

        result = await resolver.resolve("compact_markdown", "sess-123")

        assert len(result) < 200
        assert "truncated" in result

    async def test_truncates_long_transcript(
        self, mock_session_manager, mock_message_manager, temp_project
    ):
        """transcript is truncated when over limit."""
        resolver = ContextResolver(
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
            project_path=temp_project,
            max_content_size=100,
        )

        mock_message_manager.get_messages = AsyncMock(
            return_value=[
                {"role": "user", "content": "C" * 100},
                {"role": "assistant", "content": "D" * 100},
            ]
        )

        result = await resolver.resolve("transcript:10", "sess-123")

        assert len(result) < 250
        assert "truncated" in result

    async def test_no_truncation_under_limit(
        self, mock_session_manager, mock_message_manager, temp_project
    ):
        """Content under limit is not truncated."""
        resolver = ContextResolver(
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
            project_path=temp_project,
            max_content_size=1000,
        )

        mock_session = MagicMock()
        mock_session.summary_markdown = "Small content"
        mock_session_manager.get.return_value = mock_session

        result = await resolver.resolve("summary_markdown", "sess-123")

        assert result == "Small content"
        assert "truncated" not in result


class TestUnknownSource:
    """Tests for unknown source formats."""

    async def test_raises_on_unknown_source(self, resolver):
        """Unknown source format raises error."""
        with pytest.raises(ContextResolutionError) as exc_info:
            await resolver.resolve("invalid_source", "sess-123")

        assert "Unknown context source format" in str(exc_info.value)

    async def test_raises_on_malformed_source(self, resolver):
        """Malformed source format raises error."""
        with pytest.raises(ContextResolutionError) as exc_info:
            await resolver.resolve("session_id:", "sess-123")

        assert "Unknown context source format" in str(exc_info.value)


class TestFormatInjectedPrompt:
    """Tests for format_injected_prompt function."""

    def test_formats_with_context(self):
        """Formats prompt with context properly."""
        result = format_injected_prompt("Context here", "Do the task")

        assert "## Context from Parent Session" in result
        assert "Context here" in result
        assert "## Task" in result
        assert "Do the task" in result

    def test_skips_empty_context(self):
        """Skips injection when context is empty."""
        result = format_injected_prompt("", "Do the task")

        assert result == "Do the task"

    def test_skips_whitespace_context(self):
        """Skips injection when context is only whitespace."""
        result = format_injected_prompt("   \n\t  ", "Do the task")

        assert result == "Do the task"

    def test_preserves_original_prompt(self):
        """Original prompt is preserved in output."""
        prompt = "This is a complex\nmulti-line\nprompt."
        result = format_injected_prompt("Context", prompt)

        assert prompt in result

    def test_uses_custom_template(self):
        """Uses custom template when provided."""
        template = "CONTEXT:\n{{ context }}\n\nTASK:\n{{ prompt }}"
        result = format_injected_prompt("My context", "My task", template=template)

        assert result == "CONTEXT:\nMy context\n\nTASK:\nMy task"
        assert "## Context from Parent Session" not in result

    def test_custom_template_with_missing_placeholder(self):
        """Custom template without placeholders is returned as-is."""
        template = "Static template without placeholders"
        result = format_injected_prompt("Context", "Task", template=template)

        assert result == "Static template without placeholders"

    def test_custom_template_partial_placeholder(self):
        """Custom template with only one placeholder works."""
        template = "Just the task: {{ prompt }}"
        result = format_injected_prompt("Context ignored", "Do something", template=template)

        assert result == "Just the task: Do something"

    def test_default_template_when_none(self):
        """Default template is used when template is None."""
        result = format_injected_prompt("Context", "Task", template=None)

        assert "## Context from Parent Session" in result
        assert "Context" in result
        assert "Task" in result

    def test_empty_context_skips_template(self):
        """Empty context returns original prompt regardless of template."""
        template = "Custom template"
        result = format_injected_prompt("", "Original prompt", template=template)

        assert result == "Original prompt"

