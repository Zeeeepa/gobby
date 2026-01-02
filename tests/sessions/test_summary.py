"""Tests for the SummaryFileGenerator."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.sessions.summary import SummaryFileGenerator
from gobby.sessions.transcripts.claude import ClaudeTranscriptParser


@pytest.fixture
def mock_transcript_processor():
    """Create a mock transcript processor."""
    processor = MagicMock(spec=ClaudeTranscriptParser)
    processor.extract_turns_since_clear.return_value = []
    processor.extract_last_messages.return_value = []
    return processor


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service."""
    service = MagicMock()
    mock_provider = MagicMock()
    mock_provider.generate_summary = AsyncMock(return_value="## Summary\n\nTest summary content")
    service.get_default_provider.return_value = mock_provider
    service.get_provider.return_value = mock_provider
    return service


@pytest.fixture
def summary_generator(mock_transcript_processor, mock_llm_service, temp_dir):
    """Create a SummaryFileGenerator instance for testing."""
    return SummaryFileGenerator(
        transcript_processor=mock_transcript_processor,
        summary_file_path=str(temp_dir / "session_summaries"),
        llm_service=mock_llm_service,
    )


class TestSummaryFileGeneratorInit:
    """Tests for SummaryFileGenerator initialization."""

    def test_init_with_llm_service(self, mock_transcript_processor, mock_llm_service):
        """Test initialization with LLM service."""
        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        assert gen.llm_provider is not None
        mock_llm_service.get_default_provider.assert_called_once()

    def test_init_without_llm_service(self, mock_transcript_processor):
        """Test initialization without LLM service falls back to ClaudeLLMProvider."""
        with patch("gobby.sessions.summary.load_config") as mock_load:
            mock_config = MagicMock()
            mock_load.return_value = mock_config

            with patch("gobby.sessions.summary.ClaudeLLMProvider") as mock_claude:
                gen = SummaryFileGenerator(
                    transcript_processor=mock_transcript_processor,
                )

                # Should try to create ClaudeLLMProvider as fallback
                mock_claude.assert_called_once_with(mock_config)


class TestSummaryFileGeneratorWrite:
    """Tests for summary file writing."""

    def test_write_summary_to_file(self, summary_generator, temp_dir):
        """Test writing summary to file."""
        session_id = "test-session-123"
        summary = "# Test Summary\n\nTest content"

        result = summary_generator.write_summary_to_file(session_id, summary)

        assert result is not None
        assert Path(result).exists()
        assert Path(result).read_text() == summary

    def test_write_summary_creates_directory(self, mock_transcript_processor, mock_llm_service, temp_dir):
        """Test that write_summary creates directory if it doesn't exist."""
        new_dir = temp_dir / "new_summaries"
        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            summary_file_path=str(new_dir),
            llm_service=mock_llm_service,
        )

        result = gen.write_summary_to_file("session-id", "Summary content")

        assert result is not None
        assert new_dir.exists()

    def test_write_summary_file_naming(self, summary_generator, temp_dir):
        """Test that summary files are named with timestamp and session_id."""
        session_id = "unique-session-id"

        result = summary_generator.write_summary_to_file(session_id, "Content")

        assert result is not None
        filename = Path(result).name
        assert session_id in filename
        assert filename.startswith("session_")
        assert filename.endswith(".md")


class TestSummaryFileGeneratorGenerate:
    """Tests for summary generation."""

    def test_generate_session_summary_no_external_id(self, summary_generator):
        """Test generation fails when no external_id in input."""
        result = summary_generator.generate_session_summary(
            session_id="db-session-id",
            input_data={},  # No session_id (external_id)
        )

        assert result["status"] == "no_external_id"

    def test_generate_session_summary_no_transcript(self, summary_generator):
        """Test generation handles missing transcript path."""
        result = summary_generator.generate_session_summary(
            session_id="db-session-id",
            input_data={"session_id": "external-123"},  # No transcript_path
        )

        assert result["status"] == "no_transcript"

    def test_generate_session_summary_transcript_not_found(self, summary_generator, temp_dir):
        """Test generation handles non-existent transcript file."""
        result = summary_generator.generate_session_summary(
            session_id="db-session-id",
            input_data={
                "session_id": "external-123",
                "transcript_path": str(temp_dir / "nonexistent.jsonl"),
            },
        )

        assert result["status"] == "transcript_not_found"

    def test_generate_session_summary_success(
        self, summary_generator, mock_transcript_processor, temp_dir
    ):
        """Test successful summary generation."""
        # Create a test transcript file
        transcript_path = temp_dir / "transcript.jsonl"
        turns = [
            {"message": {"role": "user", "content": "Hello"}},
            {"message": {"role": "assistant", "content": "Hi there!"}},
        ]
        with open(transcript_path, "w") as f:
            for turn in turns:
                f.write(json.dumps(turn) + "\n")

        mock_transcript_processor.extract_turns_since_clear.return_value = turns
        mock_transcript_processor.extract_last_messages.return_value = turns

        with patch.object(summary_generator, "_get_git_status", return_value="clean"):
            with patch.object(summary_generator, "_get_file_changes", return_value="No changes"):
                result = summary_generator.generate_session_summary(
                    session_id="db-session-id",
                    input_data={
                        "session_id": "external-123",
                        "transcript_path": str(transcript_path),
                    },
                )

        assert result["status"] == "success"
        assert result["external_id"] == "external-123"
        assert result["summary_length"] > 0
        assert result["file_written"] is not None

    def test_generate_session_summary_disabled_in_config(
        self, mock_transcript_processor, mock_llm_service, temp_dir
    ):
        """Test generation respects disabled config."""
        from gobby.config.app import DaemonConfig, SessionSummaryConfig

        config = DaemonConfig(
            session_summary=SessionSummaryConfig(enabled=False)
        )

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
            config=config,
        )

        result = gen.generate_session_summary(
            session_id="db-session-id",
            input_data={"session_id": "external-123", "transcript_path": "/some/path"},
        )

        assert result["status"] == "disabled"


class TestExtractTodowrite:
    """Tests for TodoWrite extraction."""

    def test_extract_todowrite_found(self, summary_generator):
        """Test extracting TodoWrite from transcript."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "TodoWrite",
                            "input": {
                                "todos": [
                                    {"content": "Task 1", "status": "completed"},
                                    {"content": "Task 2", "status": "in_progress"},
                                    {"content": "Task 3", "status": "pending"},
                                ]
                            },
                        }
                    ],
                }
            }
        ]

        result = summary_generator._extract_last_todowrite(turns)

        assert result is not None
        assert "[x] Task 1 (completed)" in result
        assert "[>] Task 2 (in_progress)" in result
        assert "[ ] Task 3 (pending)" in result

    def test_extract_todowrite_not_found(self, summary_generator):
        """Test extracting TodoWrite when not present."""
        turns = [
            {"message": {"role": "user", "content": "Hello"}},
            {"message": {"role": "assistant", "content": "Hi!"}},
        ]

        result = summary_generator._extract_last_todowrite(turns)

        assert result is None

    def test_extract_todowrite_empty_todos(self, summary_generator):
        """Test extracting TodoWrite with empty todos list."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "TodoWrite",
                            "input": {"todos": []},
                        }
                    ],
                }
            }
        ]

        result = summary_generator._extract_last_todowrite(turns)

        assert result is None


class TestFormatTurns:
    """Tests for turn formatting."""

    def test_format_turns_text_content(self, summary_generator):
        """Test formatting turns with text content."""
        turns = [
            {"message": {"role": "user", "content": "Hello world"}},
            {"message": {"role": "assistant", "content": "Hi there!"}},
        ]

        result = summary_generator._format_turns_for_llm(turns)

        assert "[Turn 1 - user]: Hello world" in result
        assert "[Turn 2 - assistant]: Hi there!" in result

    def test_format_turns_array_content(self, summary_generator):
        """Test formatting turns with array content (assistant messages)."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Here's the answer"},
                        {"type": "thinking", "thinking": "Let me think..."},
                        {"type": "tool_use", "name": "Read"},
                    ],
                }
            }
        ]

        result = summary_generator._format_turns_for_llm(turns)

        assert "Here's the answer" in result
        assert "[Thinking: Let me think...]" in result
        assert "[Tool: Read]" in result


class TestGetProviderForFeature:
    """Tests for feature-specific provider selection."""

    def test_get_provider_no_config(self, mock_transcript_processor, mock_llm_service):
        """Test getting provider when no config is set."""
        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )
        gen._config = None

        provider, prompt = gen._get_provider_for_feature("session_summary")

        assert provider is not None
        assert prompt is None

    def test_get_provider_feature_disabled(self, mock_transcript_processor, mock_llm_service):
        """Test getting provider when feature is disabled."""
        from gobby.config.app import DaemonConfig, SessionSummaryConfig

        config = DaemonConfig(
            session_summary=SessionSummaryConfig(enabled=False)
        )

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
            config=config,
        )

        provider, prompt = gen._get_provider_for_feature("session_summary")

        assert provider is None
        assert prompt is None

    def test_get_provider_with_custom_prompt(self, mock_transcript_processor, mock_llm_service):
        """Test getting provider with custom prompt from config."""
        from gobby.config.app import DaemonConfig, SessionSummaryConfig

        config = DaemonConfig(
            session_summary=SessionSummaryConfig(
                enabled=True,
                prompt="Custom prompt template",
            )
        )

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
            config=config,
        )

        provider, prompt = gen._get_provider_for_feature("session_summary")

        assert provider is not None
        assert prompt == "Custom prompt template"
