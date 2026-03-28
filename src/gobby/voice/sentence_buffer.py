"""Sentence buffer for streaming TTS.

Accumulates streaming text chunks and emits complete sentences
for TTS synthesis. Prevents synthesizing partial words or sentences
which would produce unnatural speech.
"""

from __future__ import annotations

import re

# Sentence-ending punctuation followed by whitespace or end of string.
# Handles: "Hello world. Next sentence", "Really?! Yes.", etc.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Minimum sentence length to emit — avoids tiny fragments like "Dr." or "e.g."
# Keep low to preserve natural prosody for short exclamations ("Wow!", "Really?")
_MIN_SENTENCE_LEN = 4


class SentenceBuffer:
    """Accumulates streaming text, yields complete sentences for TTS."""

    def __init__(self, min_length: int = _MIN_SENTENCE_LEN) -> None:
        self._buffer = ""
        self._min_length = min_length

    def feed(self, chunk: str) -> list[str]:
        """Feed a text chunk, return any complete sentences ready for TTS.

        Args:
            chunk: Partial text from the LLM stream.

        Returns:
            List of complete sentences (may be empty if no boundary found).
        """
        self._buffer += chunk

        # Split on sentence boundaries
        parts = _SENTENCE_END.split(self._buffer)

        if len(parts) <= 1:
            # No sentence boundary found yet
            return []

        # All parts except the last are complete sentences.
        # The last part is the incomplete remainder.
        sentences: list[str] = []
        for part in parts[:-1]:
            stripped = part.strip()
            if stripped:
                sentences.append(stripped)

        self._buffer = parts[-1]

        # If any sentence is too short, merge it with the next one
        merged: list[str] = []
        carry = ""
        for s in sentences:
            combined = f"{carry} {s}".strip() if carry else s
            if len(combined) < self._min_length:
                carry = combined
            else:
                merged.append(combined)
                carry = ""

        if carry:
            # Short leftover — push back to buffer
            self._buffer = f"{carry} {self._buffer}".strip() if self._buffer else carry

        return merged

    def flush(self) -> str | None:
        """Flush remaining buffer content (call at end of stream).

        Returns:
            Remaining text, or None if buffer is empty.
        """
        text = self._buffer.strip()
        self._buffer = ""
        return text or None

    def clear(self) -> None:
        """Discard all buffered text (call on cancellation)."""
        self._buffer = ""
