"""Tests for the SummaryFileGenerator."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.sessions.summary import SummaryFileGenerator
from gobby.sessions.transcripts.claude import ClaudeTranscriptParser

pytestmark = pytest.mark.unit


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

    def test_init_with_llm_service(self, mock_transcript_processor, mock_llm_service) -> None:
        """Test initialization with LLM service."""
        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        assert gen.llm_provider is not None
        mock_llm_service.get_default_provider.assert_called_once()

    def test_init_without_llm_service(self, mock_transcript_processor) -> None:
        """Test initialization without LLM service falls back to ClaudeLLMProvider."""
        with patch("gobby.config.app.load_config") as mock_load:
            mock_config = MagicMock()
            mock_load.return_value = mock_config

            with patch("gobby.sessions.summary.ClaudeLLMProvider") as mock_claude:
                SummaryFileGenerator(
                    transcript_processor=mock_transcript_processor,
                )

                # Should try to create ClaudeLLMProvider as fallback
                mock_claude.assert_called_once_with(mock_config)

    def test_init_llm_service_no_providers(self, mock_transcript_processor) -> None:
        """Test initialization when LLM service has no providers."""
        mock_service = MagicMock()
        mock_service.get_default_provider.side_effect = ValueError("No providers configured")

        with patch("gobby.config.app.load_config") as mock_load:
            mock_config = MagicMock()
            mock_load.return_value = mock_config

            with patch("gobby.sessions.summary.ClaudeLLMProvider") as mock_claude:
                mock_claude.return_value = MagicMock()

                gen = SummaryFileGenerator(
                    transcript_processor=mock_transcript_processor,
                    llm_service=mock_service,
                )

                # Should fall back to ClaudeLLMProvider
                mock_claude.assert_called_once_with(mock_config)
                assert gen.llm_provider is not None

    def test_init_fallback_provider_fails(self, mock_transcript_processor) -> None:
        """Test initialization when fallback ClaudeLLMProvider also fails."""
        mock_service = MagicMock()
        mock_service.get_default_provider.side_effect = ValueError("No providers")

        with patch("gobby.config.app.load_config") as mock_load:
            mock_load.side_effect = Exception("Config load failed")

            gen = SummaryFileGenerator(
                transcript_processor=mock_transcript_processor,
                llm_service=mock_service,
            )

            # llm_provider should remain None
            assert gen.llm_provider is None

    def test_init_with_config_passed(self, mock_transcript_processor, mock_llm_service) -> None:
        """Test initialization with config passed directly."""
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
            config=config,
        )

        assert gen._config is config


class TestSummaryFileGeneratorWrite:
    """Tests for summary file writing."""

    def test_write_summary_to_file(self, summary_generator, temp_dir) -> None:
        """Test writing summary to file."""
        session_id = "test-session-123"
        summary = "# Test Summary\n\nTest content"

        result = summary_generator.write_summary_to_file(session_id, summary)

        assert result is not None
        assert Path(result).exists()
        assert Path(result).read_text() == summary

    def test_write_summary_creates_directory(
        self, mock_transcript_processor, mock_llm_service, temp_dir
    ) -> None:
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

    def test_write_summary_file_naming(self, summary_generator, temp_dir) -> None:
        """Test that summary files are named with timestamp and session_id."""
        session_id = "unique-session-id"

        result = summary_generator.write_summary_to_file(session_id, "Content")

        assert result is not None
        filename = Path(result).name
        assert session_id in filename
        assert filename.startswith("session_")
        assert filename.endswith(".md")

    def test_write_summary_to_file_failure(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test write_summary_to_file handles write errors."""
        # Use an invalid path
        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            summary_file_path="/nonexistent/deeply/nested/path/that/cannot/be/created",
            llm_service=mock_llm_service,
        )

        # Mock mkdir to raise an exception
        with patch.object(Path, "mkdir", side_effect=PermissionError("Permission denied")):
            result = gen.write_summary_to_file("session-id", "content")

        assert result is None


class TestSummaryFileGeneratorGenerate:
    """Tests for summary generation."""

    def test_generate_session_summary_no_external_id(self, summary_generator) -> None:
        """Test generation fails when no external_id in input."""
        result = summary_generator.generate_session_summary(
            session_id="db-session-id",
            input_data={},  # No session_id (external_id)
        )

        assert result["status"] == "no_external_id"

    def test_generate_session_summary_no_transcript(self, summary_generator) -> None:
        """Test generation handles missing transcript path."""
        result = summary_generator.generate_session_summary(
            session_id="db-session-id",
            input_data={"session_id": "external-123"},  # No transcript_path
        )

        assert result["status"] == "no_transcript"

    def test_generate_session_summary_transcript_not_found(
        self, summary_generator, temp_dir
    ) -> None:
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
    ) -> None:
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
    ) -> None:
        """Test generation respects disabled config."""
        from gobby.config.app import DaemonConfig
        from gobby.config.sessions import SessionSummaryConfig

        config = DaemonConfig(session_summary=SessionSummaryConfig(enabled=False))

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

    def test_generate_session_summary_updates_path_from_config(
        self, mock_transcript_processor, mock_llm_service, temp_dir
    ) -> None:
        """Test generation updates summary path from config."""
        from gobby.config.app import DaemonConfig
        from gobby.config.sessions import SessionSummaryConfig

        new_path = str(temp_dir / "custom_summaries")
        config = DaemonConfig(
            session_summary=SessionSummaryConfig(
                enabled=True,
                summary_file_path=new_path,
            )
        )

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
            config=config,
            summary_file_path=str(temp_dir / "original_path"),
        )

        # Create a test transcript file
        transcript_path = temp_dir / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Hello"}}) + "\n")

        mock_transcript_processor.extract_turns_since_clear.return_value = []
        mock_transcript_processor.extract_last_messages.return_value = []

        with patch.object(gen, "_get_git_status", return_value="clean"):
            with patch.object(gen, "_get_file_changes", return_value="No changes"):
                gen.generate_session_summary(
                    session_id="db-session-id",
                    input_data={
                        "session_id": "external-123",
                        "transcript_path": str(transcript_path),
                    },
                )

        # Check that the path was updated
        assert gen._summary_file_path == new_path

    def test_generate_session_summary_exception_handling(
        self, mock_transcript_processor, mock_llm_service, temp_dir
    ) -> None:
        """Test generation handles exceptions gracefully."""
        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
            summary_file_path=str(temp_dir / "summaries"),
        )

        # Create a valid transcript file
        transcript_path = temp_dir / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write(json.dumps({"message": {"role": "user", "content": "Hello"}}) + "\n")

        # Make transcript processor raise an exception
        mock_transcript_processor.extract_turns_since_clear.side_effect = Exception(
            "Processing error"
        )

        result = gen.generate_session_summary(
            session_id="db-session-id",
            input_data={
                "session_id": "external-123",
                "transcript_path": str(transcript_path),
            },
        )

        assert result["status"] == "error"
        assert "Processing error" in result["error"]
        assert result["external_id"] == "external-123"


class TestExtractTodowrite:
    """Tests for TodoWrite extraction."""

    def test_extract_todowrite_found(self, summary_generator) -> None:
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

    def test_extract_todowrite_not_found(self, summary_generator) -> None:
        """Test extracting TodoWrite when not present."""
        turns = [
            {"message": {"role": "user", "content": "Hello"}},
            {"message": {"role": "assistant", "content": "Hi!"}},
        ]

        result = summary_generator._extract_last_todowrite(turns)

        assert result is None

    def test_extract_todowrite_empty_todos(self, summary_generator) -> None:
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

    def test_extract_todowrite_multiple_turns_gets_last(self, summary_generator) -> None:
        """Test that the last TodoWrite is extracted when multiple exist."""
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
                                    {"content": "Old task", "status": "completed"},
                                ]
                            },
                        }
                    ],
                }
            },
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "TodoWrite",
                            "input": {
                                "todos": [
                                    {"content": "New task", "status": "pending"},
                                ]
                            },
                        }
                    ],
                }
            },
        ]

        result = summary_generator._extract_last_todowrite(turns)

        assert result is not None
        assert "New task" in result
        assert "Old task" not in result

    def test_extract_todowrite_non_list_content(self, summary_generator) -> None:
        """Test extracting TodoWrite when content is not a list."""
        turns = [
            {"message": {"role": "assistant", "content": "Just text content"}},
        ]

        result = summary_generator._extract_last_todowrite(turns)

        assert result is None

    def test_extract_todowrite_non_dict_blocks(self, summary_generator) -> None:
        """Test extracting TodoWrite with non-dict blocks in content."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": ["string block", 123, None],
                }
            }
        ]

        result = summary_generator._extract_last_todowrite(turns)

        assert result is None


class TestFormatTurns:
    """Tests for turn formatting."""

    def test_format_turns_text_content(self, summary_generator) -> None:
        """Test formatting turns with text content."""
        turns = [
            {"message": {"role": "user", "content": "Hello world"}},
            {"message": {"role": "assistant", "content": "Hi there!"}},
        ]

        result = summary_generator._format_turns_for_llm(turns)

        assert "[Turn 1 - user]: Hello world" in result
        assert "[Turn 2 - assistant]: Hi there!" in result

    def test_format_turns_array_content(self, summary_generator) -> None:
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

    def test_format_turns_empty(self, summary_generator) -> None:
        """Test formatting empty turns list."""
        result = summary_generator._format_turns_for_llm([])

        assert result == ""

    def test_format_turns_missing_message(self, summary_generator) -> None:
        """Test formatting turns with missing message key."""
        turns = [
            {},  # No message key
            {"message": {}},  # Empty message
        ]

        result = summary_generator._format_turns_for_llm(turns)

        assert "[Turn 1 - unknown]:" in result
        assert "[Turn 2 - unknown]:" in result

    def test_format_turns_non_dict_blocks(self, summary_generator) -> None:
        """Test formatting turns where content array has non-dict items."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        "string item",
                        {"type": "text", "text": "valid block"},
                        123,
                    ],
                }
            }
        ]

        result = summary_generator._format_turns_for_llm(turns)

        assert "valid block" in result


class TestGetProviderForFeature:
    """Tests for feature-specific provider selection."""

    def test_get_provider_no_config(self, mock_transcript_processor, mock_llm_service) -> None:
        """Test getting provider when no config is set."""
        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )
        gen._config = None

        provider, prompt = gen._get_provider_for_feature("session_summary")

        assert provider is not None
        assert prompt is None

    def test_get_provider_feature_disabled(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test getting provider when feature is disabled."""
        from gobby.config.app import DaemonConfig
        from gobby.config.sessions import SessionSummaryConfig

        config = DaemonConfig(session_summary=SessionSummaryConfig(enabled=False))

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
            config=config,
        )

        provider, prompt = gen._get_provider_for_feature("session_summary")

        assert provider is None
        assert prompt is None

    def test_get_provider_with_custom_prompt(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test getting provider with custom prompt from config."""
        from gobby.config.app import DaemonConfig
        from gobby.config.sessions import SessionSummaryConfig

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

    def test_get_provider_unknown_feature(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test getting provider for unknown feature name."""
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
            config=config,
        )

        provider, prompt = gen._get_provider_for_feature("unknown_feature")

        # Should return default provider with no prompt
        assert provider is not None
        assert prompt is None

    def test_get_provider_no_feature_config(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test getting provider when feature config attribute is None."""
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()
        config.session_summary = None  # type: ignore

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
            config=config,
        )

        provider, prompt = gen._get_provider_for_feature("session_summary")

        assert provider is not None
        assert prompt is None

    def test_get_provider_with_named_provider(self, mock_transcript_processor) -> None:
        """Test getting provider by name from LLMService."""
        from gobby.config.app import DaemonConfig
        from gobby.config.sessions import SessionSummaryConfig

        config = DaemonConfig(
            session_summary=SessionSummaryConfig(
                enabled=True,
                provider="openai",
                prompt="Use OpenAI",
            )
        )

        # Create mock LLM service that can get provider by name
        mock_service = MagicMock()
        mock_default_provider = MagicMock()
        mock_openai_provider = MagicMock()
        mock_service.get_default_provider.return_value = mock_default_provider
        mock_service.get_provider.return_value = mock_openai_provider

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_service,
            config=config,
        )

        provider, prompt = gen._get_provider_for_feature("session_summary")

        assert provider is mock_openai_provider
        assert prompt == "Use OpenAI"
        mock_service.get_provider.assert_called_with("openai")

    def test_get_provider_named_provider_not_available(self, mock_transcript_processor) -> None:
        """Test fallback when named provider is not available."""
        from gobby.config.app import DaemonConfig
        from gobby.config.sessions import SessionSummaryConfig

        config = DaemonConfig(
            session_summary=SessionSummaryConfig(
                enabled=True,
                provider="unavailable_provider",
                prompt="Some prompt",
            )
        )

        mock_service = MagicMock()
        mock_default_provider = MagicMock()
        mock_service.get_default_provider.return_value = mock_default_provider
        mock_service.get_provider.side_effect = ValueError("Provider not found")

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_service,
            config=config,
        )

        provider, prompt = gen._get_provider_for_feature("session_summary")

        # Should fall back to default provider
        assert provider is mock_default_provider
        assert prompt == "Some prompt"

    def test_get_provider_exception_handling(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test that exceptions in _get_provider_for_feature are handled."""
        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        # Set a config that will cause an exception when accessed
        mock_config = MagicMock()
        mock_config.session_summary = MagicMock()
        # Make getattr raise an exception
        type(mock_config.session_summary).enabled = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Config error"))
        )
        gen._config = mock_config

        provider, prompt = gen._get_provider_for_feature("session_summary")

        # Should return default provider on exception
        assert provider is not None
        assert prompt is None


class TestGenerateSummaryWithLLM:
    """Tests for LLM summary generation."""

    def test_generate_summary_no_provider(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test summary generation when no provider available."""
        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )
        gen.llm_provider = None

        with patch.object(gen, "_get_provider_for_feature", return_value=(None, None)):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id="sess-123",
                session_source="Claude Code",
            )

        assert "LLM provider not initialized" in result

    def test_generate_summary_no_prompt_configured(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test summary generation when no prompt template is configured."""
        mock_provider = MagicMock()
        mock_provider.generate_summary = AsyncMock(return_value="Summary")

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        # Return provider but None for prompt
        with patch.object(gen, "_get_provider_for_feature", return_value=(mock_provider, None)):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id="sess-123",
                session_source="Claude Code",
            )

        # Should return error message instead of trying to call provider
        assert "No prompt template configured" in result
        assert "session_summary.prompt" in result
        # Provider should not be called
        mock_provider.generate_summary.assert_not_called()

    def test_generate_summary_with_custom_prompt(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test summary generation with custom prompt."""
        mock_provider = MagicMock()
        mock_provider.generate_summary = AsyncMock(return_value="Custom summary")

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        with patch.object(
            gen, "_get_provider_for_feature", return_value=(mock_provider, "Custom template")
        ):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id="sess-123",
                session_source="Claude Code",
            )

        assert "Custom summary" in result
        mock_provider.generate_summary.assert_called_once()
        call_kwargs = mock_provider.generate_summary.call_args
        assert call_kwargs[1]["prompt_template"] == "Custom template"

    def test_generate_summary_llm_returns_empty(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test summary generation when LLM returns empty string."""
        mock_provider = MagicMock()
        mock_provider.generate_summary = AsyncMock(return_value="")

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        with patch.object(
            gen, "_get_provider_for_feature", return_value=(mock_provider, "Test prompt")
        ):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id="sess-123",
                session_source="Claude Code",
            )

        # Should produce error summary
        assert "Error" in result

    def test_generate_summary_llm_exception(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test summary generation handles LLM exceptions."""
        mock_provider = MagicMock()
        mock_provider.generate_summary = AsyncMock(side_effect=Exception("LLM API error"))

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        with patch.object(
            gen, "_get_provider_for_feature", return_value=(mock_provider, "Test prompt")
        ):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id="sess-123",
                session_source="Claude Code",
            )

        assert "Error" in result
        assert "LLM API error" in result

    def test_generate_summary_header_without_session_source(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test header generation without session_source."""
        mock_provider = MagicMock()
        mock_provider.generate_summary = AsyncMock(return_value="Summary content")

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        with patch.object(
            gen, "_get_provider_for_feature", return_value=(mock_provider, "Test prompt")
        ):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id="sess-123",
                session_source=None,
            )

        assert "Session ID:     sess-123" in result
        assert "Claude Code ID: ext-123" in result

    def test_generate_summary_header_without_session_id(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test header generation without session_id."""
        mock_provider = MagicMock()
        mock_provider.generate_summary = AsyncMock(return_value="Summary content")

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        with patch.object(
            gen, "_get_provider_for_feature", return_value=(mock_provider, "Test prompt")
        ):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id=None,
                session_source="Claude Code",
            )

        assert "Claude Code ID: ext-123" in result
        # Should not have Session ID line since session_id is None
        assert "Session ID:" not in result

    def test_generate_summary_with_todowrite_in_llm_output(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test todowrite insertion when LLM output contains Claude's Todo List section."""
        mock_provider = MagicMock()
        mock_provider.generate_summary = AsyncMock(
            return_value="## Summary\n\nContent\n\n## Claude's Todo List\n\n## Next Steps\n\nMore"
        )

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        todowrite_list = "- [ ] Task 1 (pending)\n- [x] Task 2 (completed)"

        with patch.object(
            gen, "_get_provider_for_feature", return_value=(mock_provider, "Test prompt")
        ):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id="sess-123",
                session_source="Claude Code",
                todowrite_list=todowrite_list,
            )

        assert "## Claude's Todo List" in result
        assert "Task 1" in result
        assert "Task 2" in result
        assert "## Next Steps" in result

    def test_generate_summary_with_todowrite_no_next_section(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test todowrite insertion when there's no section after Claude's Todo List."""
        mock_provider = MagicMock()
        mock_provider.generate_summary = AsyncMock(
            return_value="## Summary\n\nContent\n\n## Claude's Todo List"
        )

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        todowrite_list = "- [ ] Task 1 (pending)"

        with patch.object(
            gen, "_get_provider_for_feature", return_value=(mock_provider, "Test prompt")
        ):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id="sess-123",
                session_source="Claude Code",
                todowrite_list=todowrite_list,
            )

        assert "## Claude's Todo List" in result
        assert "Task 1" in result

    def test_generate_summary_with_todowrite_fallback_before_next_steps(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test todowrite insertion before Next Steps when no Claude's Todo List section."""
        mock_provider = MagicMock()
        mock_provider.generate_summary = AsyncMock(
            return_value="## Summary\n\nContent\n\n## Next Steps\n\nDo more things"
        )

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        todowrite_list = "- [ ] Task 1 (pending)"

        with patch.object(
            gen, "_get_provider_for_feature", return_value=(mock_provider, "Test prompt")
        ):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id="sess-123",
                session_source="Claude Code",
                todowrite_list=todowrite_list,
            )

        # Todo list should be inserted before Next Steps
        assert "## Claude's Todo List" in result
        assert result.index("Claude's Todo List") < result.index("Next Steps")

    def test_generate_summary_with_todowrite_append_fallback(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test todowrite appended to end when no markers exist."""
        mock_provider = MagicMock()
        mock_provider.generate_summary = AsyncMock(return_value="## Summary\n\nJust some content")

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        todowrite_list = "- [ ] Task 1 (pending)"

        with patch.object(
            gen, "_get_provider_for_feature", return_value=(mock_provider, "Test prompt")
        ):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id="sess-123",
                session_source="Claude Code",
                todowrite_list=todowrite_list,
            )

        # Todo list should be appended at end
        assert result.endswith("## Claude's Todo List\n- [ ] Task 1 (pending)")

    def test_generate_summary_error_with_todowrite(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test error summary includes todowrite list."""
        mock_provider = MagicMock()
        mock_provider.generate_summary = AsyncMock(side_effect=Exception("API error"))

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        todowrite_list = "- [ ] Task 1 (pending)"

        with patch.object(
            gen, "_get_provider_for_feature", return_value=(mock_provider, "Test prompt")
        ):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id="sess-123",
                session_source="Claude Code",
                todowrite_list=todowrite_list,
            )

        assert "Error" in result
        assert "API error" in result
        assert "## Claude's Todo List" in result
        assert "Task 1" in result

    def test_generate_summary_error_header_variants(
        self, mock_transcript_processor, mock_llm_service
    ) -> None:
        """Test error header generation with different session_id/source combinations."""
        mock_provider = MagicMock()
        mock_provider.generate_summary = AsyncMock(side_effect=Exception("API error"))

        gen = SummaryFileGenerator(
            transcript_processor=mock_transcript_processor,
            llm_service=mock_llm_service,
        )

        # Test with session_id but no session_source
        with patch.object(
            gen, "_get_provider_for_feature", return_value=(mock_provider, "Test prompt")
        ):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id="sess-123",
                session_source=None,
            )

        assert "Session ID:     sess-123" in result
        assert "Claude Code ID: ext-123" in result

        # Test with no session_id
        with patch.object(
            gen, "_get_provider_for_feature", return_value=(mock_provider, "Test prompt")
        ):
            result = gen._generate_summary_with_llm(
                last_turns=[],
                last_messages=[],
                git_status="clean",
                file_changes="No changes",
                external_id="ext-123",
                session_id=None,
                session_source="Claude Code",
            )

        assert "Claude Code ID: ext-123" in result
        assert "Session ID:" not in result


class TestGitOperations:
    """Tests for git status and file changes methods."""

    def test_get_git_status_success(self, summary_generator) -> None:
        """Test successful git status retrieval."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=" M src/file.py\n?? new_file.py\n")

            result = summary_generator._get_git_status()

        assert "M src/file.py" in result
        assert "new_file.py" in result

    def test_get_git_status_not_git_repo(self, summary_generator) -> None:
        """Test git status when not in a git repo."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Not a git repository")

            result = summary_generator._get_git_status()

        assert result == "Not a git repository or git not available"

    def test_get_git_status_timeout(self, summary_generator) -> None:
        """Test git status when command times out."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 5)

            result = summary_generator._get_git_status()

        assert result == "Not a git repository or git not available"

    def test_get_file_changes_with_modifications(self, summary_generator) -> None:
        """Test file changes with modified files."""
        with patch("subprocess.run") as mock_run:
            # Mock diff result
            diff_result = MagicMock(stdout="M\tsrc/file1.py\nD\tsrc/file2.py\n")
            # Mock untracked result
            untracked_result = MagicMock(stdout="new_file.py\n")

            mock_run.side_effect = [diff_result, untracked_result]

            result = summary_generator._get_file_changes()

        assert "Modified/Deleted:" in result
        assert "src/file1.py" in result
        assert "Untracked:" in result
        assert "new_file.py" in result

    def test_get_file_changes_no_changes(self, summary_generator) -> None:
        """Test file changes when there are no changes."""
        with patch("subprocess.run") as mock_run:
            diff_result = MagicMock(stdout="")
            untracked_result = MagicMock(stdout="")

            mock_run.side_effect = [diff_result, untracked_result]

            result = summary_generator._get_file_changes()

        assert result == "No changes"

    def test_get_file_changes_only_untracked(self, summary_generator) -> None:
        """Test file changes with only untracked files."""
        with patch("subprocess.run") as mock_run:
            diff_result = MagicMock(stdout="")
            untracked_result = MagicMock(stdout="new_file.py\n")

            mock_run.side_effect = [diff_result, untracked_result]

            result = summary_generator._get_file_changes()

        assert "Untracked:" in result
        assert "new_file.py" in result
        assert "Modified/Deleted:" not in result

    def test_get_file_changes_only_modified(self, summary_generator) -> None:
        """Test file changes with only modified files."""
        with patch("subprocess.run") as mock_run:
            diff_result = MagicMock(stdout="M\tsrc/file.py\n")
            untracked_result = MagicMock(stdout="")

            mock_run.side_effect = [diff_result, untracked_result]

            result = summary_generator._get_file_changes()

        assert "Modified/Deleted:" in result
        assert "src/file.py" in result
        assert "Untracked:" not in result

    def test_get_file_changes_exception(self, summary_generator) -> None:
        """Test file changes when exception occurs."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Git command failed")

            result = summary_generator._get_file_changes()

        assert result == "Unable to determine file changes"


class TestTranscriptProcessor:
    """Tests for the TranscriptProcessor backward-compatible alias."""

    def test_transcript_processor_alias(self) -> None:
        """Test that TranscriptProcessor is an alias for ClaudeTranscriptParser."""
        from gobby.sessions.summary import TranscriptProcessor

        assert TranscriptProcessor is ClaudeTranscriptParser
