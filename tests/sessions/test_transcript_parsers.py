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

    def test_codex_parser_simple(self):
        parser = CodexTranscriptParser()

        line = json.dumps(
            {"role": "user", "content": "def hello():", "timestamp": "2023-01-01T12:00:00Z"}
        )

        msg = parser.parse_line(line, 0)
        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "def hello():"
        assert msg.index == 0

    def test_codex_parser_missing_role(self):
        parser = CodexTranscriptParser()
        line = json.dumps({"content": "missing role"})
        msg = parser.parse_line(line, 0)
        assert msg is None


class TestGeminiTranscriptParser:
    """Tests for Gemini transcript parser."""

    def test_gemini_parser_generic_message(self):
        parser = GeminiTranscriptParser()

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

    def test_gemini_parser_model_response(self):
        parser = GeminiTranscriptParser()

        # Test model response
        line = json.dumps(
            {"role": "model", "content": "I am Gemini", "timestamp": "2023-01-01T12:00:01Z"}
        )

        msg = parser.parse_line(line, 1)
        assert msg is not None
        assert msg.role == "assistant"  # Normalized
        assert msg.content == "I am Gemini"

    def test_gemini_parser_nested_message_structure(self):
        parser = GeminiTranscriptParser()

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

    def test_gemini_parser_list_content(self):
        parser = GeminiTranscriptParser()

        # Test content as list of parts
        line = json.dumps({"role": "model", "content": [{"text": "Part 1"}, "Part 2"]})

        msg = parser.parse_line(line, 3)
        assert msg is not None
        assert "Part 1" in msg.content
        assert "Part 2" in msg.content
