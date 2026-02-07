"""
Tests for Transcript Parsers (Claude, Codex, Gemini).
Consolidated from individual files.
"""

import json
from datetime import UTC, datetime

import pytest

from gobby.sessions.transcripts.base import ParsedMessage
from gobby.sessions.transcripts.claude import ClaudeTranscriptParser
from gobby.sessions.transcripts.codex import CodexTranscriptParser
from gobby.sessions.transcripts.gemini import GeminiTranscriptParser

pytestmark = pytest.mark.unit


class TestParsedMessage:
    """Tests for ParsedMessage dataclass."""

    def test_model_field_defaults_to_none(self) -> None:
        """Test that ParsedMessage model field defaults to None."""
        msg = ParsedMessage(
            index=0,
            role="assistant",
            content="Hello",
            content_type="text",
            tool_name=None,
            tool_input=None,
            tool_result=None,
            timestamp=datetime.now(UTC),
            raw_json={},
        )
        assert msg.model is None

    def test_model_field_accepts_value(self) -> None:
        """Test that ParsedMessage model field can be set."""
        msg = ParsedMessage(
            index=0,
            role="assistant",
            content="Hello",
            content_type="text",
            tool_name=None,
            tool_input=None,
            tool_result=None,
            timestamp=datetime.now(UTC),
            raw_json={},
            model="claude-opus-4-5-20251101",
        )
        assert msg.model == "claude-opus-4-5-20251101"


class TestClaudeTranscriptParser:
    """Tests for Claude transcript parser."""

    @pytest.fixture
    def parser(self):
        return ClaudeTranscriptParser()

    def test_extract_usage_returns_tuple_with_model(self, parser) -> None:
        """Test that _extract_usage returns tuple of (TokenUsage | None, str | None)."""
        data = {
            "type": "agent",
            "message": {
                "model": "claude-opus-4-5-20251101",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                },
            },
        }
        usage, model = parser._extract_usage(data)
        assert usage is not None
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert model == "claude-opus-4-5-20251101"

    def test_extract_usage_returns_none_model_when_missing(self, parser) -> None:
        """Test that _extract_usage returns None model when not present."""
        data = {
            "type": "agent",
            "message": {
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                },
            },
        }
        usage, model = parser._extract_usage(data)
        assert usage is not None
        assert model is None

    def test_extract_usage_returns_none_tuple_when_no_usage(self, parser) -> None:
        """Test that _extract_usage returns (None, model) when no usage data."""
        data = {
            "type": "agent",
            "message": {
                "model": "claude-opus-4-5-20251101",
                "content": "Hello",
            },
        }
        usage, model = parser._extract_usage(data)
        assert usage is None
        assert model == "claude-opus-4-5-20251101"

    def test_parse_line_extracts_model(self, parser) -> None:
        """Test that parse_line sets model on ParsedMessage."""
        line = json.dumps(
            {
                "type": "agent",
                "message": {
                    "model": "claude-opus-4-5-20251101",
                    "content": [{"type": "text", "text": "Hello"}],
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                    },
                },
                "timestamp": "2024-01-01T12:00:00Z",
            }
        )
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.model == "claude-opus-4-5-20251101"

    def test_parse_line_user(self, parser) -> None:
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

    def test_parse_line_assistant_text_blocks(self, parser) -> None:
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

    def test_parse_line_tool_use(self, parser) -> None:
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

    def test_parse_line_tool_result(self, parser) -> None:
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

    def test_parse_line_invalid_json(self, parser) -> None:
        # Should handle gracefully and log warning
        msg = parser.parse_line("invalid json", 0)
        assert msg is None

    def test_parse_line_unknown_type(self, parser) -> None:
        line = json.dumps({"type": "unknown_event"})
        msg = parser.parse_line(line, 0)
        assert msg is None

    def test_parse_lines_continuous(self, parser) -> None:
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

    def test_is_session_boundary(self, parser) -> None:
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

    def test_extract_last_messages(self, parser) -> None:
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

    def test_extract_last_messages_complex_content(self, parser) -> None:
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

    def test_extract_turns_since_clear_no_clear(self, parser) -> None:
        turns = [{"type": "user"}] * 10
        extracted = parser.extract_turns_since_clear(turns, max_turns=5)
        assert len(extracted) == 5

    def test_extract_turns_since_clear_with_boundary(self, parser) -> None:
        turns = [
            {"type": "user", "message": {"content": "before"}},
            {"type": "user", "message": {"content": "<command-name>/clear</command-name>"}},
            {"type": "user", "message": {"content": "after1"}},
            {"type": "agent", "message": {"content": "after2"}},
        ]

        extracted = parser.extract_turns_since_clear(turns)
        assert len(extracted) == 2
        assert extracted[0]["message"]["content"] == "after1"

    def test_extract_turns_since_clear_consecutive(self, parser) -> None:
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

    def test_parse_line_tool_use_extracts_id(self, parser) -> None:
        """Test that tool_use_id is extracted from tool_use blocks."""
        line = json.dumps(
            {
                "type": "agent",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_abc123",
                            "name": "read_file",
                            "input": {"path": "foo.txt"},
                        }
                    ]
                },
                "timestamp": "2024-01-01T12:00:02Z",
            }
        )

        msg = parser.parse_line(line, 2)

        assert msg is not None
        assert msg.tool_use_id == "toolu_abc123"

    def test_parse_line_tool_result_extracts_id(self, parser) -> None:
        """Test that tool_use_id is extracted from tool_result messages."""
        line = json.dumps(
            {
                "type": "tool_result",
                "tool_name": "read_file",
                "tool_use_id": "toolu_abc123",
                "result": "file content",
                "timestamp": "2024-01-01T12:00:03Z",
            }
        )

        msg = parser.parse_line(line, 3)

        assert msg is not None
        assert msg.tool_use_id == "toolu_abc123"

    def test_validate_tool_pairing_empty(self, parser) -> None:
        """Test _validate_tool_pairing with empty turns."""
        cleaned, removed = parser._validate_tool_pairing([])
        assert cleaned == []
        assert removed == []

    def test_validate_tool_pairing_properly_paired(self, parser) -> None:
        """Test _validate_tool_pairing with properly paired tool_use/tool_result."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "toolu_001", "name": "read"},
                    ],
                }
            },
            {
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "toolu_001", "content": "ok"},
                    ],
                }
            },
        ]

        cleaned, removed = parser._validate_tool_pairing(turns)

        assert len(cleaned) == 2
        assert removed == []
        # Content should be unchanged
        assert cleaned[1]["message"]["content"][0]["tool_use_id"] == "toolu_001"

    def test_validate_tool_pairing_orphaned_result(self, parser) -> None:
        """Test _validate_tool_pairing removes orphaned tool_result."""
        turns = [
            # No tool_use, just an orphaned tool_result
            {
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_orphan",
                            "content": "orphaned",
                        },
                    ],
                }
            },
        ]

        cleaned, removed = parser._validate_tool_pairing(turns)

        assert len(cleaned) == 1
        assert removed == ["toolu_orphan"]
        # The tool_result block should be removed
        assert cleaned[0]["message"]["content"] == []

    def test_validate_tool_pairing_mixed(self, parser) -> None:
        """Test _validate_tool_pairing with mixed valid and orphaned results."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "toolu_valid", "name": "read"},
                    ],
                }
            },
            {
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "toolu_valid", "content": "ok"},
                        {"type": "tool_result", "tool_use_id": "toolu_orphan", "content": "bad"},
                    ],
                }
            },
        ]

        cleaned, removed = parser._validate_tool_pairing(turns)

        assert removed == ["toolu_orphan"]
        # Valid result should remain
        assert len(cleaned[1]["message"]["content"]) == 1
        assert cleaned[1]["message"]["content"][0]["tool_use_id"] == "toolu_valid"

    def test_validate_tool_pairing_multiple_tool_use(self, parser) -> None:
        """Test _validate_tool_pairing with multiple tool_use in one message."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "toolu_001", "name": "read"},
                        {"type": "tool_use", "id": "toolu_002", "name": "write"},
                    ],
                }
            },
            {
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "toolu_001", "content": "ok1"},
                        {"type": "tool_result", "tool_use_id": "toolu_002", "content": "ok2"},
                    ],
                }
            },
        ]

        cleaned, removed = parser._validate_tool_pairing(turns)

        assert removed == []
        assert len(cleaned[1]["message"]["content"]) == 2

    def test_extract_turns_since_clear_validates_tool_pairing(self, parser) -> None:
        """Test that extract_turns_since_clear removes orphaned tool_results after truncation."""
        # Create turns where truncation would orphan a tool_result
        turns = []
        # Add a tool_use that will be truncated away
        turns.append(
            {
                "type": "agent",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_truncated", "name": "read"}],
                },
            }
        )
        # Add many user messages to push the tool_use out of range
        for i in range(60):
            turns.append({"type": "user", "message": {"content": f"msg {i}"}})
        # Add a tool_result referencing the truncated tool_use (edge case)
        turns.append(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_truncated",
                            "content": "late result",
                        },
                    ],
                },
            }
        )

        # Extract with max_turns=50, which should truncate the tool_use
        extracted = parser.extract_turns_since_clear(turns, max_turns=50)

        # The orphaned tool_result should be removed from the last turn
        last_turn = extracted[-1]
        content = last_turn["message"]["content"]
        # Either content is empty list or the tool_result block was removed
        has_orphan = any(
            isinstance(b, dict) and b.get("tool_use_id") == "toolu_truncated"
            for b in (content if isinstance(content, list) else [])
        )
        assert not has_orphan, "Orphaned tool_result should have been removed"


class TestCodexTranscriptParser:
    """Tests for Codex transcript parser."""

    @pytest.fixture
    def parser(self):
        return CodexTranscriptParser()

    def test_codex_parser_simple(self, parser) -> None:
        line = json.dumps(
            {"role": "user", "content": "def hello():", "timestamp": "2023-01-01T12:00:00Z"}
        )

        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "def hello():"
        assert msg.index == 0

    def test_codex_parser_missing_role(self, parser) -> None:
        line = json.dumps({"content": "missing role"})
        msg = parser.parse_line(line, 0)
        assert msg is None

    def test_codex_parse_line_invalid_json(self, parser) -> None:
        """Test handling of invalid JSON."""
        msg = parser.parse_line("not valid json", 0)
        assert msg is None

    def test_codex_parse_line_empty(self, parser) -> None:
        """Test handling of empty/whitespace lines."""
        assert parser.parse_line("", 0) is None
        assert parser.parse_line("   ", 0) is None

    def test_codex_parse_line_assistant(self, parser) -> None:
        """Test parsing assistant messages."""
        line = json.dumps({"role": "assistant", "content": "Here is the code"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.content == "Here is the code"

    def test_codex_parse_line_system(self, parser) -> None:
        """Test parsing system messages."""
        line = json.dumps({"role": "system", "content": "System prompt"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "system"

    def test_codex_extract_last_messages(self, parser) -> None:
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

    def test_codex_extract_last_messages_empty(self, parser) -> None:
        """Test extract_last_messages with empty list."""
        msgs = parser.extract_last_messages([], num_pairs=2)
        assert msgs == []

    def test_codex_extract_turns_since_clear(self, parser) -> None:
        """Test extract_turns_since_clear."""
        turns = [{"role": "user"}] * 100

        # Should return last max_turns
        extracted = parser.extract_turns_since_clear(turns, max_turns=50)
        assert len(extracted) == 50

        # Should return all if less than max_turns
        small_turns = [{"role": "user"}] * 10
        extracted = parser.extract_turns_since_clear(small_turns, max_turns=50)
        assert len(extracted) == 10

    def test_codex_is_session_boundary(self, parser) -> None:
        """Test is_session_boundary always returns False for Codex."""
        assert parser.is_session_boundary({"role": "user"}) is False
        assert parser.is_session_boundary({}) is False

    def test_codex_parse_lines(self, parser) -> None:
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

    def test_codex_extract_usage_input_tokens(self, parser) -> None:
        """Test _extract_usage with input_tokens format."""
        line = json.dumps(
            {
                "role": "assistant",
                "content": "Response",
                "input_tokens": 100,
                "output_tokens": 50,
                "cached_tokens": 25,
                "cost": 0.005,
            }
        )
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.usage is not None
        assert msg.usage.input_tokens == 100
        assert msg.usage.output_tokens == 50
        assert msg.usage.cache_read_tokens == 25
        assert msg.usage.total_cost_usd == 0.005

    def test_codex_extract_usage_nested_usage_field(self, parser) -> None:
        """Test _extract_usage with nested usage field."""
        line = json.dumps(
            {
                "role": "assistant",
                "content": "Response",
                "usage": {
                    "inputTokens": 200,
                    "outputTokens": 100,
                    "cachedTokens": 50,
                    "total_cost": 0.01,
                },
            }
        )
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.usage is not None
        assert msg.usage.input_tokens == 200
        assert msg.usage.output_tokens == 100
        assert msg.usage.cache_read_tokens == 50
        assert msg.usage.total_cost_usd == 0.01

    def test_codex_extract_usage_no_usage(self, parser) -> None:
        """Test _extract_usage returns None when no usage data."""
        line = json.dumps({"role": "assistant", "content": "Response"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.usage is None

    def test_codex_timestamp_parsing(self, parser) -> None:
        """Test timestamp parsing from message."""
        # With timestamp
        line = json.dumps(
            {
                "role": "user",
                "content": "Hello",
                "timestamp": "2024-06-15T10:30:00Z",
            }
        )
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.timestamp.year == 2024
        assert msg.timestamp.month == 6

        # Without timestamp (uses current time)
        line = json.dumps({"role": "user", "content": "Hello"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.timestamp is not None

    def test_codex_timestamp_invalid_format(self, parser) -> None:
        """Test handling of invalid timestamp format."""
        line = json.dumps(
            {
                "role": "user",
                "content": "Hello",
                "timestamp": "not-a-date",
            }
        )
        msg = parser.parse_line(line, 0)
        assert msg is not None
        # Should use default timestamp without crashing
        assert msg.timestamp is not None


class TestGeminiTranscriptParser:
    """Tests for Gemini transcript parser."""

    @pytest.fixture
    def parser(self):
        return GeminiTranscriptParser()

    def test_gemini_parser_generic_message(self, parser) -> None:
        # Test simple user message via type-based format
        line = json.dumps(
            {
                "type": "message",
                "role": "user",
                "content": "Hello world",
                "timestamp": "2023-01-01T12:00:00Z",
            }
        )

        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "Hello world"
        assert msg.index == 0
        assert msg.timestamp.year == 2023

    def test_gemini_parser_model_response(self, parser) -> None:
        # Test model response via type-based format
        line = json.dumps(
            {
                "type": "message",
                "role": "model",
                "content": "I am Gemini",
                "timestamp": "2023-01-01T12:00:01Z",
            }
        )

        msg = parser.parse_line(line, 1)
        assert msg is not None
        assert msg.role == "assistant"  # Normalized
        assert msg.content == "I am Gemini"

    def test_gemini_parser_nested_message_structure_skipped(self, parser) -> None:
        # Legacy nested message structure without type field is now skipped
        line = json.dumps(
            {
                "message": {"role": "user", "content": "Nested content"},
                "timestamp": "2023-01-01T12:00:02Z",
            }
        )

        msg = parser.parse_line(line, 2)
        assert msg is None

    def test_gemini_parser_list_content(self, parser) -> None:
        # Test content as list of parts via type-based format
        line = json.dumps({"type": "model", "content": [{"text": "Part 1"}, "Part 2"]})

        msg = parser.parse_line(line, 3)
        assert msg is not None
        assert "Part 1" in msg.content
        assert "Part 2" in msg.content

    def test_gemini_parse_line_empty(self, parser) -> None:
        """Test handling of empty/whitespace lines."""
        assert parser.parse_line("", 0) is None
        assert parser.parse_line("   ", 0) is None

    def test_gemini_parse_line_invalid_json(self, parser) -> None:
        """Test handling of invalid JSON."""
        msg = parser.parse_line("not valid json", 0)
        assert msg is None

    def test_gemini_parse_line_unknown_type(self, parser) -> None:
        """Test handling of messages without role."""
        line = json.dumps({"data": "something"})
        msg = parser.parse_line(line, 0)
        assert msg is None

    def test_gemini_parse_line_type_field_user(self, parser) -> None:
        """Test parsing with type field as 'user'."""
        line = json.dumps({"type": "user", "content": "From type field"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "user"

    def test_gemini_parse_line_type_field_model(self, parser) -> None:
        """Test parsing with type field as 'model'."""
        line = json.dumps({"type": "model", "content": "Model response"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "assistant"

    def test_gemini_parse_line_tool_result(self, parser) -> None:
        """Test parsing tool_result event."""
        line = json.dumps(
            {
                "type": "tool_result",
                "tool_name": "read_file",
                "output": "some result",
                "status": "success",
            }
        )
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "tool"
        assert msg.content_type == "tool_result"
        assert "some result" in msg.content

    def test_gemini_parse_line_function_call(self, parser) -> None:
        """Test parsing functionCall in content via type-based format."""
        line = json.dumps(
            {
                "type": "model",
                "content": [
                    {"text": "Let me call a function"},
                    {"functionCall": {"name": "read_file", "args": {"path": "test.txt"}}},
                ],
            }
        )
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.content_type == "tool_use"
        assert msg.tool_name == "read_file"
        assert msg.tool_input == {"path": "test.txt"}
        assert "Let me call a function" in msg.content

    def test_gemini_extract_last_messages(self, parser) -> None:
        """Test extract_last_messages with type-based format."""
        turns = [
            {"type": "message", "role": "user", "content": "1"},
            {"type": "message", "role": "model", "content": "2"},
            {"type": "message", "role": "user", "content": "3"},
            {"type": "message", "role": "model", "content": "4"},
        ]

        msgs = parser.extract_last_messages(turns, num_pairs=1)
        assert len(msgs) == 2
        assert msgs[0]["content"] == "3"
        assert msgs[0]["role"] == "user"
        assert msgs[1]["content"] == "4"
        assert msgs[1]["role"] == "assistant"  # Normalized from model

    def test_gemini_extract_last_messages_list_content(self, parser) -> None:
        """Test extract_last_messages with list content."""
        turns = [
            {"type": "message", "role": "user", "content": ["part1", "part2"]},
            {"type": "message", "role": "model", "content": [{"text": "response"}]},
        ]

        msgs = parser.extract_last_messages(turns, num_pairs=1)
        assert len(msgs) == 2
        assert "part1" in msgs[0]["content"]
        assert "part2" in msgs[0]["content"]

    def test_gemini_extract_last_messages_nested_message_skipped(self, parser) -> None:
        """Test extract_last_messages skips legacy nested message structure."""
        turns = [
            {"message": {"role": "user", "content": "nested user"}},
            {"message": {"role": "assistant", "content": "nested assistant"}},
        ]

        msgs = parser.extract_last_messages(turns, num_pairs=1)
        assert len(msgs) == 0  # Legacy format is now skipped

    def test_gemini_extract_turns_since_clear(self, parser) -> None:
        """Test extract_turns_since_clear."""
        turns = [{"role": "user"}] * 100

        extracted = parser.extract_turns_since_clear(turns, max_turns=50)
        assert len(extracted) == 50

        small_turns = [{"role": "user"}] * 10
        extracted = parser.extract_turns_since_clear(small_turns, max_turns=50)
        assert len(extracted) == 10

    def test_gemini_is_session_boundary(self, parser) -> None:
        """Test is_session_boundary always returns False for Gemini."""
        assert parser.is_session_boundary({}) is False
        assert parser.is_session_boundary({"role": "user"}) is False

    def test_gemini_parse_lines(self, parser) -> None:
        """Test batch parsing with parse_lines."""
        lines = [
            json.dumps({"type": "message", "role": "user", "content": "First"}),
            "",  # Empty line
            json.dumps({"type": "message", "role": "model", "content": "Second"}),
        ]

        msgs = parser.parse_lines(lines, start_index=0)
        assert len(msgs) == 2
        assert msgs[0].index == 0
        assert msgs[0].role == "user"
        assert msgs[1].index == 1
        assert msgs[1].role == "assistant"

    def test_gemini_extract_usage(self, parser) -> None:
        """Test _extract_usage with usageMetadata."""
        line = json.dumps(
            {
                "type": "message",
                "role": "model",
                "content": "Response",
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 50,
                },
            }
        )
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.usage is not None
        assert msg.usage.input_tokens == 100
        assert msg.usage.output_tokens == 50

    def test_gemini_extract_usage_no_usage(self, parser) -> None:
        """Test _extract_usage returns None without usageMetadata."""
        line = json.dumps({"type": "message", "role": "model", "content": "Response"})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.usage is None

    def test_gemini_timestamp_invalid_format(self, parser) -> None:
        """Test handling of invalid timestamp format."""
        line = json.dumps(
            {
                "type": "message",
                "role": "user",
                "content": "Hello",
                "timestamp": "invalid-date",
            }
        )
        msg = parser.parse_line(line, 0)
        assert msg is not None
        # Should use default timestamp without crashing
        assert msg.timestamp is not None

    def test_gemini_content_none(self, parser) -> None:
        """Test handling of None content."""
        line = json.dumps({"type": "message", "role": "user", "content": None})
        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.content == ""
