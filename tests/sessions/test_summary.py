"""Tests for the summary module backward-compatible alias."""

import pytest

pytestmark = pytest.mark.unit


class TestTranscriptProcessor:
    """Tests for the TranscriptProcessor backward-compatible alias."""

    def test_transcript_processor_alias(self) -> None:
        """Test that TranscriptProcessor is an alias for ClaudeTranscriptParser."""
        from gobby.sessions.summary import TranscriptProcessor
        from gobby.sessions.transcripts.claude import ClaudeTranscriptParser

        assert TranscriptProcessor is ClaudeTranscriptParser
