"""
Tests for Transcript Parsers (Claude, Codex, Gemini).
Consolidated from individual files.
"""

import json

import pytest

from gobby.sessions.transcripts.claude import ClaudeTranscriptParser
from gobby.sessions.transcripts.codex import CodexTranscriptParser
from gobby.sessions.transcripts.gemini import GeminiTranscriptParser


class TestClaudeTranscriptParser:
    """Tests for Claude transcript parser."""

    @pytest.fixture
    def parser(self):
        return ClaudeTranscriptParser()

    def test_parse_line_user(self, parser):
        line = json.dumps(
            {
                "type": "user",
                "message": {"content": "Hello world"},
                "timestamp": "2024-01-01T12:00:00Z",
            }
        )

        msg = parser.parse_line(line, 0)

        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "Hello world"
        assert msg.content_type == "text"
        assert msg.index == 0

    def test_parse_line_assistant_text_blocks(self, parser):
        line = json.dumps(
            {
                "type": "agent",
                "message": {
                    "content": [
                        {"type": "text", "text": "Part 1"},
                        {"type": "text", "text": "Part 2"},
                    ]
                },
                "timestamp": "2024-01-01T12:00:01Z",
            }
        )

        msg = parser.parse_line(line, 1)

        assert msg is not None
        assert msg.role == "assistant"
        # Parser joins with space
        assert msg.content == "Part 1 Part 2"

    def test_parse_line_tool_use(self, parser):
        line = json.dumps(
            {
                "type": "agent",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "read_file", "input": {"path": "foo.txt"}}
                    ]
                },
                "timestamp": "2024-01-01T12:00:02Z",
            }
        )

        msg = parser.parse_line(line, 2)

        assert msg is not None
        assert msg.role == "assistant"
        assert msg.content_type == "tool_use"
        assert msg.tool_name == "read_file"
        assert msg.tool_input == {"path": "foo.txt"}

    def test_parse_line_tool_result(self, parser):
        line = json.dumps(
            {
                "type": "tool_result",
                "tool_name": "read_file",
                "result": "file content",
                "timestamp": "2024-01-01T12:00:03Z",
            }
        )

        msg = parser.parse_line(line, 3)

        assert msg is not None
        assert msg.role == "tool"
        assert msg.content_type == "tool_result"
        assert msg.tool_name == "read_file"
        assert msg.content == "file content"

    def test_parse_line_invalid_json(self, parser):
        # Should handle gracefully and log warning
        msg = parser.parse_line("invalid json", 0)
        assert msg is None

    def test_parse_line_unknown_type(self, parser):
        line = json.dumps({"type": "unknown_event"})
        msg = parser.parse_line(line, 0)
        assert msg is None

    def test_parse_lines_continuous(self, parser):
        lines = [
            json.dumps({"type": "user", "message": {"content": "Hi"}}),
            json.dumps(
                {"type": "agent", "message": {"content": [{"type": "text", "text": "Hello"}]}}
            ),
        ]

        msgs = parser.parse_lines(lines, start_index=10)

        assert len(msgs) == 2
        assert msgs[0].index == 10
        assert msgs[0].role == "user"
        assert msgs[1].index == 11
        assert msgs[1].role == "assistant"

    def test_is_session_boundary(self, parser):
        # Standard user message
        assert not parser.is_session_boundary({"type": "user", "message": {"content": "hello"}})

        # Clear command
        assert parser.is_session_boundary(
            {
                "type": "user",
                "message": {"content": "blah <command-name>/clear</command-name> blah"},
            }
        )

        # Agent message (never a boundary)
        assert not parser.is_session_boundary(
            {"type": "agent", "message": {"content": "cleaning up..."}}
        )

    def test_extract_last_messages(self, parser):
        turns = [
            {"message": {"role": "user", "content": "1"}},
            {"message": {"role": "assistant", "content": "2"}},
            {"message": {"role": "user", "content": "3"}},
            {"message": {"role": "assistant", "content": "4"}},
        ]

        # helper to mock turn format
        msgs = parser.extract_last_messages(turns, num_pairs=1)
        assert len(msgs) == 2
        assert msgs[0]["content"] == "3"
        assert msgs[1]["content"] == "4"

        msgs = parser.extract_last_messages(turns, num_pairs=2)
        assert len(msgs) == 4
        assert msgs[0]["content"] == "1"

    def test_extract_last_messages_complex_content(self, parser):
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Part 1"},
                        {"type": "text", "text": "Part 2"},
                    ],
                }
            }
        ]
        msgs = parser.extract_last_messages(turns, 1)
        assert msgs[0]["content"] == "Part 1 Part 2"

    def test_extract_turns_since_clear_no_clear(self, parser):
        turns = [{"type": "user"}] * 10
        extracted = parser.extract_turns_since_clear(turns, max_turns=5)
        assert len(extracted) == 5

    def test_extract_turns_since_clear_with_boundary(self, parser):
        turns = [
            {"type": "user", "message": {"content": "before"}},
            {"type": "user", "message": {"content": "<command-name>/clear</command-name>"}},
            {"type": "user", "message": {"content": "after1"}},
            {"type": "agent", "message": {"content": "after2"}},
        ]

        extracted = parser.extract_turns_since_clear(turns)
        assert len(extracted) == 2
        assert extracted[0]["message"]["content"] == "after1"

    def test_extract_turns_since_clear_consecutive(self, parser):
        turns = [
            {"type": "user", "message": {"content": "<command-name>/clear</command-name>"}},
            {
                "type": "user",
                "message": {"content": "<command-name>/clear</command-name>"},
            },  # consecutive
            {"type": "user", "message": {"content": "real start"}},
        ]
        extracted = parser.extract_turns_since_clear(turns)
        assert len(extracted) == 1
        assert extracted[0]["message"]["content"] == "real start"


class TestCodexTranscriptParser:
    """Tests for Codex transcript parser."""

    @pytest.fixture
    def parser(self):
        return CodexTranscriptParser()

    def test_codex_parser_simple(self, parser):
        line = json.dumps(
            {"role": "user", "content": "def hello():", "timestamp": "2023-01-01T12:00:00Z"}
        )

        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "def hello():"
        assert msg.index == 0

    def test_codex_parser_missing_role(self, parser):
        line = json.dumps({"content": "missing role"})
        msg = parser.parse_line(line, 0)
        assert msg is None

    def test_codex_parse_line_invalid_json(self, parser):
        """Test handling of invalid JSON."""
        msg = parser.parse_line("not valid json", 0)
        assert msg is None

    def test_codex_parse_line_empty(self, parser):
        """Test handling of empty/whitespace lines."""
        assert parser.parse_line("", 0) is None
        assert parser.parse_line("   ", 0) is None

    def test_codex_parse_line_assistant(self, parser):
        """Test parsing assistant messages."""
        line = json.dumps({"role": "assistant", "content": "Here is the code"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.content == "Here is the code"

    def test_codex_parse_line_system(self, parser):
        """Test parsing system messages."""
        line = json.dumps({"role": "system", "content": "System prompt"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "system"

    def test_codex_extract_last_messages(self, parser):
        """Test extract_last_messages with various num_pairs."""
        turns = [
            {"role": "user", "content": "1"},
            {"role": "assistant", "content": "2"},
            {"role": "user", "content": "3"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "5"},
            {"role": "assistant", "content": "6"},
        ]

        # Get last 1 pair (2 messages)
        msgs = parser.extract_last_messages(turns, num_pairs=1)
        assert len(msgs) == 2
        assert msgs[0]["content"] == "5"
        assert msgs[1]["content"] == "6"

        # Get last 2 pairs (4 messages)
        msgs = parser.extract_last_messages(turns, num_pairs=2)
        assert len(msgs) == 4
        assert msgs[0]["content"] == "3"

        # Get more than available
        msgs = parser.extract_last_messages(turns, num_pairs=10)
        assert len(msgs) == 6

    def test_codex_extract_last_messages_empty(self, parser):
        """Test extract_last_messages with empty list."""
        msgs = parser.extract_last_messages([], num_pairs=2)
        assert msgs == []

    def test_codex_extract_turns_since_clear(self, parser):
        """Test extract_turns_since_clear."""
        turns = [{"role": "user"}] * 100

        # Should return last max_turns
        extracted = parser.extract_turns_since_clear(turns, max_turns=50)
        assert len(extracted) == 50

        # Should return all if less than max_turns
        small_turns = [{"role": "user"}] * 10
        extracted = parser.extract_turns_since_clear(small_turns, max_turns=50)
        assert len(extracted) == 10

    def test_codex_is_session_boundary(self, parser):
        """Test is_session_boundary always returns False for Codex."""
        assert parser.is_session_boundary({"role": "user"}) is False
        assert parser.is_session_boundary({}) is False

    def test_codex_parse_lines(self, parser):
        """Test batch parsing with parse_lines."""
        lines = [
            json.dumps({"role": "user", "content": "First"}),
            "",  # Empty line should be skipped
            json.dumps({"role": "assistant", "content": "Second"}),
            "invalid json",  # Should be skipped
            json.dumps({"role": "user", "content": "Third"}),
        ]

        msgs = parser.parse_lines(lines, start_index=5)

        # Should parse 3 valid messages
        assert len(msgs) == 3
        assert msgs[0].index == 5
        assert msgs[0].content == "First"
        assert msgs[1].index == 6
        assert msgs[1].content == "Second"
        assert msgs[2].index == 7
        assert msgs[2].content == "Third"

    def test_codex_extract_usage_input_tokens(self, parser):
        """Test _extract_usage with input_tokens format."""
        line = json.dumps({
            "role": "assistant",
            "content": "Response",
            "input_tokens": 100,
            "output_tokens": 50,
            "cached_tokens": 25,
            "cost": 0.005,
        })
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.usage is not None
        assert msg.usage.input_tokens == 100
        assert msg.usage.output_tokens == 50
        assert msg.usage.cache_read_tokens == 25
        assert msg.usage.total_cost_usd == 0.005

    def test_codex_extract_usage_nested_usage_field(self, parser):
        """Test _extract_usage with nested usage field."""
        line = json.dumps({
            "role": "assistant",
            "content": "Response",
            "usage": {
                "inputTokens": 200,
                "outputTokens": 100,
                "cachedTokens": 50,
                "total_cost": 0.01,
            },
        })
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.usage is not None
        assert msg.usage.input_tokens == 200
        assert msg.usage.output_tokens == 100
        assert msg.usage.cache_read_tokens == 50
        assert msg.usage.total_cost_usd == 0.01

    def test_codex_extract_usage_no_usage(self, parser):
        """Test _extract_usage returns None when no usage data."""
        line = json.dumps({"role": "assistant", "content": "Response"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.usage is None

    def test_codex_timestamp_parsing(self, parser):
        """Test timestamp parsing from message."""
        # With timestamp
        line = json.dumps({
            "role": "user",
            "content": "Hello",
            "timestamp": "2024-06-15T10:30:00Z",
        })
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.timestamp.year == 2024
        assert msg.timestamp.month == 6

        # Without timestamp (uses current time)
        line = json.dumps({"role": "user", "content": "Hello"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.timestamp is not None

    def test_codex_timestamp_invalid_format(self, parser):
        """Test handling of invalid timestamp format."""
        line = json.dumps({
            "role": "user",
            "content": "Hello",
            "timestamp": "not-a-date",
        })
        msg = parser.parse_line(line, 0)
        assert msg is not None
        # Should use default timestamp without crashing
        assert msg.timestamp is not None


class TestGeminiTranscriptParser:
    """Tests for Gemini transcript parser."""

    @pytest.fixture
    def parser(self):
        return GeminiTranscriptParser()

    def test_gemini_parser_generic_message(self, parser):
        # Test simple user message
        line = json.dumps(
            {"role": "user", "content": "Hello world", "timestamp": "2023-01-01T12:00:00Z"}
        )

        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "Hello world"
        assert msg.index == 0
        assert msg.timestamp.year == 2023

    def test_gemini_parser_model_response(self, parser):
        # Test model response
        line = json.dumps(
            {"role": "model", "content": "I am Gemini", "timestamp": "2023-01-01T12:00:01Z"}
        )

        msg = parser.parse_line(line, 1)
        assert msg is not None
        assert msg.role == "assistant"  # Normalized
        assert msg.content == "I am Gemini"

    def test_gemini_parser_nested_message_structure(self, parser):
        # Test nested message structure often seen in Google APIs
        line = json.dumps(
            {
                "message": {"role": "user", "content": "Nested content"},
                "timestamp": "2023-01-01T12:00:02Z",
            }
        )

        msg = parser.parse_line(line, 2)
        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "Nested content"

    def test_gemini_parser_list_content(self, parser):
        # Test content as list of parts
        line = json.dumps({"role": "model", "content": [{"text": "Part 1"}, "Part 2"]})

        msg = parser.parse_line(line, 3)
        assert msg is not None
        assert "Part 1" in msg.content
        assert "Part 2" in msg.content

    def test_gemini_parse_line_empty(self, parser):
        """Test handling of empty/whitespace lines."""
        assert parser.parse_line("", 0) is None
        assert parser.parse_line("   ", 0) is None

    def test_gemini_parse_line_invalid_json(self, parser):
        """Test handling of invalid JSON."""
        msg = parser.parse_line("not valid json", 0)
        assert msg is None

    def test_gemini_parse_line_unknown_type(self, parser):
        """Test handling of messages without role."""
        line = json.dumps({"data": "something"})
        msg = parser.parse_line(line, 0)
        assert msg is None

    def test_gemini_parse_line_type_field_user(self, parser):
        """Test parsing with type field as 'user'."""
        line = json.dumps({"type": "user", "content": "From type field"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "user"

    def test_gemini_parse_line_type_field_model(self, parser):
        """Test parsing with type field as 'model'."""
        line = json.dumps({"type": "model", "content": "Model response"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "assistant"

    def test_gemini_parse_line_tool_result(self, parser):
        """Test parsing tool_result message."""
        line = json.dumps({"tool_result": {"output": "some result"}})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "tool"
        assert "output" in msg.content

    def test_gemini_parse_line_function_call(self, parser):
        """Test parsing functionCall in content."""
        line = json.dumps({
            "role": "model",
            "content": [
                {"text": "Let me call a function"},
                {"functionCall": {"name": "read_file", "args": {"path": "test.txt"}}},
            ],
        })
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.content_type == "tool_use"
        assert msg.tool_name == "read_file"
        assert msg.tool_input == {"path": "test.txt"}
        assert "Let me call a function" in msg.content

    def test_gemini_extract_last_messages(self, parser):
        """Test extract_last_messages."""
        turns = [
            {"role": "user", "content": "1"},
            {"role": "model", "content": "2"},
            {"role": "user", "content": "3"},
            {"role": "model", "content": "4"},
        ]

        msgs = parser.extract_last_messages(turns, num_pairs=1)
        assert len(msgs) == 2
        assert msgs[0]["content"] == "3"
        assert msgs[0]["role"] == "user"
        assert msgs[1]["content"] == "4"
        assert msgs[1]["role"] == "assistant"  # Normalized from model

    def test_gemini_extract_last_messages_list_content(self, parser):
        """Test extract_last_messages with list content."""
        turns = [
            {"role": "user", "content": ["part1", "part2"]},
            {"role": "model", "content": [{"text": "response"}]},
        ]

        msgs = parser.extract_last_messages(turns, num_pairs=1)
        assert len(msgs) == 2
        assert "part1" in msgs[0]["content"]
        assert "part2" in msgs[0]["content"]

    def test_gemini_extract_last_messages_nested_message(self, parser):
        """Test extract_last_messages with nested message structure."""
        turns = [
            {"message": {"role": "user", "content": "nested user"}},
            {"message": {"role": "assistant", "content": "nested assistant"}},
        ]

        msgs = parser.extract_last_messages(turns, num_pairs=1)
        assert len(msgs) == 2
        assert msgs[0]["content"] == "nested user"
        assert msgs[1]["content"] == "nested assistant"

    def test_gemini_extract_turns_since_clear(self, parser):
        """Test extract_turns_since_clear."""
        turns = [{"role": "user"}] * 100

        extracted = parser.extract_turns_since_clear(turns, max_turns=50)
        assert len(extracted) == 50

        small_turns = [{"role": "user"}] * 10
        extracted = parser.extract_turns_since_clear(small_turns, max_turns=50)
        assert len(extracted) == 10

    def test_gemini_is_session_boundary(self, parser):
        """Test is_session_boundary always returns False for Gemini."""
        assert parser.is_session_boundary({}) is False
        assert parser.is_session_boundary({"role": "user"}) is False

    def test_gemini_parse_lines(self, parser):
        """Test batch parsing with parse_lines."""
        lines = [
            json.dumps({"role": "user", "content": "First"}),
            "",  # Empty line
            json.dumps({"role": "model", "content": "Second"}),
        ]

        msgs = parser.parse_lines(lines, start_index=0)
        assert len(msgs) == 2
        assert msgs[0].index == 0
        assert msgs[0].role == "user"
        assert msgs[1].index == 1
        assert msgs[1].role == "assistant"

    def test_gemini_extract_usage(self, parser):
        """Test _extract_usage with usageMetadata."""
        line = json.dumps({
            "role": "model",
            "content": "Response",
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 50,
            },
        })
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.usage is not None
        assert msg.usage.input_tokens == 100
        assert msg.usage.output_tokens == 50

    def test_gemini_extract_usage_no_usage(self, parser):
        """Test _extract_usage returns None without usageMetadata."""
        line = json.dumps({"role": "model", "content": "Response"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.usage is None

    def test_gemini_timestamp_invalid_format(self, parser):
        """Test handling of invalid timestamp format."""
        line = json.dumps({
            "role": "user",
            "content": "Hello",
            "timestamp": "invalid-date",
        })
        msg = parser.parse_line(line, 0)
        assert msg is not None
        # Should use default timestamp without crashing
        assert msg.timestamp is not None

    def test_gemini_content_none(self, parser):
        """Test handling of None content."""
        line = json.dumps({"role": "user", "content": None})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.content == ""
