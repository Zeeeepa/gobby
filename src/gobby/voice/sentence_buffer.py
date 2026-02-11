"""Sentence buffer for chunking streaming text into complete sentences.

Used to batch text from the LLM stream before sending to TTS,
ensuring natural speech boundaries.
"""

from __future__ import annotations

import re

# Split on sentence-ending punctuation followed by whitespace or end of string
_SENTENCE_RE = re.compile(r"(?<=[.!?\n])\s+")


class SentenceBuffer:
    """Accumulates streaming text and yields complete sentences.

    Example:
        buf = SentenceBuffer()
        buf.add("Hello world. ")     -> ["Hello world."]
        buf.add("How are ")          -> []
        buf.add("you? Fine. ")       -> ["How are you?", "Fine."]
        buf.flush()                  -> None  (nothing remaining)
    """

    def __init__(self) -> None:
        self._buffer: str = ""

    def add(self, text: str) -> list[str]:
        """Add text and return any complete sentences.

        Args:
            text: Incoming text chunk from LLM stream.

        Returns:
            List of complete sentences (may be empty).
        """
        self._buffer += text
        parts = _SENTENCE_RE.split(self._buffer)

        if len(parts) <= 1:
            # No complete sentence boundary found yet
            return []

        # All parts except the last are complete sentences
        sentences = [p.strip() for p in parts[:-1] if p.strip()]
        self._buffer = parts[-1]
        return sentences

    def flush(self) -> str | None:
        """Return any remaining buffered text.

        Returns:
            Remaining text or None if buffer is empty.
        """
        remaining = self._buffer.strip()
        self._buffer = ""
        return remaining if remaining else None
