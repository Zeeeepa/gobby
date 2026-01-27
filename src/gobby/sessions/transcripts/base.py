"""
Base transcript parser protocol.

Defines the interface for CLI-specific transcript parsers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Token usage metrics for a message or session."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    total_cost_usd: float | None = None


@dataclass
class ParsedMessage:
    """Normalized message from any CLI transcript."""

    index: int
    role: str
    content: str
    content_type: str  # text, thinking, tool_use, tool_result
    tool_name: str | None
    tool_input: dict[str, Any] | None
    tool_result: dict[str, Any] | None
    timestamp: datetime
    raw_json: dict[str, Any]
    usage: TokenUsage | None = None
    tool_use_id: str | None = None
    model: str | None = None


@runtime_checkable
class TranscriptParser(Protocol):
    """
    Protocol for transcript parsers.

    Each CLI tool (Claude Code, Codex, Gemini, Antigravity) has its own
    transcript format. Implementations of this protocol handle parsing
    and extracting conversation data from each format.
    """

    def parse_line(self, line: str, index: int) -> ParsedMessage | None:
        """
        Parse a single line from the transcript JSONL.

        Args:
            line: Raw JSON line string
            index: Line index (0-based)

        Returns:
            ParsedMessage object or None if line should be skipped
        """
        ...

    def parse_lines(self, lines: list[str], start_index: int = 0) -> list[ParsedMessage]:
        """
        Parse multiple lines from the transcript.

        Args:
            lines: List of raw JSON line strings
            start_index: Starting line index for first line in list

        Returns:
            List of ParsedMessage objects
        """
        ...

    def extract_last_messages(
        self, turns: list[dict[str, Any]], num_pairs: int = 2
    ) -> list[dict[str, Any]]:
        """
        Extract last N user<>agent message pairs from transcript.

        Args:
            turns: List of transcript turns
            num_pairs: Number of user/agent message pairs to extract

        Returns:
            List of message dicts with "role" and "content" fields
        """
        ...

    def extract_turns_since_clear(
        self, turns: list[dict[str, Any]], max_turns: int = 50
    ) -> list[dict[str, Any]]:
        """
        Extract turns since the most recent session boundary, up to max_turns.

        What constitutes a "session boundary" varies by CLI:
        - Claude Code: /clear command
        - Codex: New session in history
        - Gemini: Session delimiter

        Args:
            turns: List of all transcript turns
            max_turns: Maximum number of turns to extract

        Returns:
            List of turns representing the current conversation segment
        """
        ...

    def is_session_boundary(self, turn: dict[str, Any]) -> bool:
        """
        Check if a turn represents a session boundary.

        Args:
            turn: Transcript turn dict

        Returns:
            True if turn marks a session boundary
        """
        ...
