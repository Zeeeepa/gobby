"""Tests for the SentenceBuffer used in voice TTS streaming."""

import pytest

from gobby.voice.sentence_buffer import SentenceBuffer


class TestSentenceBuffer:
    def test_complete_sentence(self):
        buf = SentenceBuffer()
        result = buf.add("Hello world. ")
        assert result == ["Hello world."]

    def test_incomplete_sentence(self):
        buf = SentenceBuffer()
        result = buf.add("Hello world")
        assert result == []

    def test_multiple_sentences(self):
        buf = SentenceBuffer()
        result = buf.add("First. Second. Third. ")
        assert result == ["First.", "Second.", "Third."]

    def test_incremental_accumulation(self):
        buf = SentenceBuffer()
        assert buf.add("How are ") == []
        # "you? " contains sentence boundary (? followed by space at end)
        assert buf.add("you? ") == ["How are you?"]
        assert buf.add("Fine. ") == ["Fine."]

    def test_question_mark_boundary(self):
        buf = SentenceBuffer()
        result = buf.add("What is this? It is a test. ")
        assert result == ["What is this?", "It is a test."]

    def test_exclamation_boundary(self):
        buf = SentenceBuffer()
        result = buf.add("Wow! Amazing! ")
        assert result == ["Wow!", "Amazing!"]

    def test_newline_boundary(self):
        buf = SentenceBuffer()
        result = buf.add("Line one.\nLine two. ")
        assert len(result) >= 1  # At least first sentence

    def test_flush_remaining(self):
        buf = SentenceBuffer()
        buf.add("Some incomplete")
        result = buf.flush()
        assert result == "Some incomplete"

    def test_flush_empty(self):
        buf = SentenceBuffer()
        assert buf.flush() is None

    def test_flush_after_complete(self):
        buf = SentenceBuffer()
        buf.add("Complete. ")
        # The "Complete." is returned via add(), remaining buffer is empty after split
        result = buf.flush()
        # After split, there may be empty remainder
        assert result is None or result == ""

    def test_empty_input(self):
        buf = SentenceBuffer()
        result = buf.add("")
        assert result == []

    def test_whitespace_only(self):
        buf = SentenceBuffer()
        result = buf.add("   ")
        assert result == []

    def test_single_word_with_period(self):
        buf = SentenceBuffer()
        result = buf.add("Done. ")
        assert result == ["Done."]
