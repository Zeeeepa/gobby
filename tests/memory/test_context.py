"""Tests for memory context building."""

from unittest.mock import MagicMock

import pytest

from gobby.memory.context import (
    DEFAULT_COMPRESSION_THRESHOLD,
    _strip_leading_bullet,
    build_memory_context,
)
from gobby.storage.memories import Memory


class TestStripLeadingBullet:
    """Tests for _strip_leading_bullet function."""

    def test_dash_bullet(self):
        """Test stripping dash bullet."""
        assert _strip_leading_bullet("- item") == "item"

    def test_asterisk_bullet(self):
        """Test stripping asterisk bullet."""
        assert _strip_leading_bullet("* item") == "item"

    def test_bullet_point_character(self):
        """Test stripping bullet point character."""
        assert _strip_leading_bullet("• item") == "item"

    def test_no_bullet(self):
        """Test content without bullet."""
        assert _strip_leading_bullet("item") == "item"

    def test_leading_whitespace(self):
        """Test content with leading whitespace."""
        assert _strip_leading_bullet("  - item") == "item"
        assert _strip_leading_bullet("  item") == "item"

    def test_empty_content(self):
        """Test empty content."""
        assert _strip_leading_bullet("") == ""
        assert _strip_leading_bullet("   ") == ""

    def test_only_bullet(self):
        """Test content that is only a bullet marker."""
        # Single dash without space is stripped (matches bullet pattern)
        assert _strip_leading_bullet("-") == ""
        assert _strip_leading_bullet("- ") == ""
        assert _strip_leading_bullet("*") == ""
        assert _strip_leading_bullet("•") == ""

    def test_preserves_internal_dashes(self):
        """Test that internal dashes are preserved."""
        assert _strip_leading_bullet("- use foo-bar") == "use foo-bar"
        assert _strip_leading_bullet("use foo-bar") == "use foo-bar"


class TestBuildMemoryContext:
    """Tests for build_memory_context function."""

    def test_empty_memories(self):
        """Test with empty memory list."""
        assert build_memory_context([]) == ""

    def test_single_preference(self):
        """Test with single preference memory."""
        mem = Memory(
            id="m1",
            content="- Use TypeScript",
            memory_type="preference",
            importance=0.8,
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
        result = build_memory_context([mem])
        assert "## Preferences" in result
        assert "- Use TypeScript" in result
        # Should not have double bullets
        assert "- - " not in result

    def test_handles_various_bullet_formats(self):
        """Test that various bullet formats are normalized."""
        memories = [
            Memory(
                id="m1",
                content="- dash item",
                memory_type="preference",
                importance=0.8,
                created_at="2024-01-01",
                updated_at="2024-01-01",
            ),
            Memory(
                id="m2",
                content="* asterisk item",
                memory_type="preference",
                importance=0.8,
                created_at="2024-01-01",
                updated_at="2024-01-01",
            ),
            Memory(
                id="m3",
                content="• bullet item",
                memory_type="preference",
                importance=0.8,
                created_at="2024-01-01",
                updated_at="2024-01-01",
            ),
        ]
        result = build_memory_context(memories)
        # All should be normalized to "- "
        assert "- dash item" in result
        assert "- asterisk item" in result
        assert "- bullet item" in result
        # No double bullets
        assert "- - " not in result
        assert "- * " not in result
        assert "- • " not in result


class TestBuildMemoryContextWithCompressor:
    """Tests for build_memory_context with compressor parameter."""

    @pytest.fixture
    def mock_compressor(self):
        """Create a mock compressor."""
        compressor = MagicMock()
        compressor.compress.return_value = "Compressed memory content"
        return compressor

    @pytest.fixture
    def large_memory_list(self):
        """Create memory list that exceeds default threshold."""
        # Each memory adds roughly 50-100 chars, need ~40+ memories to exceed 4000 chars
        memories = []
        for i in range(60):
            memories.append(
                Memory(
                    id=f"m{i}",
                    content=f"This is memory item number {i} with some additional content to make it longer",
                    memory_type="preference",
                    importance=0.8,
                    created_at="2024-01-01",
                    updated_at="2024-01-01",
                )
            )
        return memories

    @pytest.fixture
    def small_memory_list(self):
        """Create memory list under default threshold."""
        return [
            Memory(
                id="m1",
                content="Short memory",
                memory_type="preference",
                importance=0.8,
                created_at="2024-01-01",
                updated_at="2024-01-01",
            )
        ]

    def test_accepts_optional_compressor_parameter(self, small_memory_list):
        """Test that function accepts optional compressor parameter."""
        # Should work with no compressor (default)
        result1 = build_memory_context(small_memory_list)
        assert result1 != ""

        # Should work with None compressor
        result2 = build_memory_context(small_memory_list, compressor=None)
        assert result2 == result1

    def test_compression_applied_when_content_exceeds_threshold(
        self, mock_compressor, large_memory_list
    ):
        """Test that compression is applied when content exceeds threshold."""
        result = build_memory_context(large_memory_list, compressor=mock_compressor)

        # Compressor should have been called
        mock_compressor.compress.assert_called_once()

        # Call should use context_type="memory"
        call_args = mock_compressor.compress.call_args
        assert call_args.kwargs.get("context_type") == "memory"

        # Result should contain compressed content wrapped in tags
        assert "<project-memory>" in result
        assert "</project-memory>" in result
        assert "Compressed memory content" in result

    def test_content_unchanged_when_under_threshold(
        self, mock_compressor, small_memory_list
    ):
        """Test that content is returned unchanged when under threshold."""
        result = build_memory_context(small_memory_list, compressor=mock_compressor)

        # Compressor should NOT have been called since content is under threshold
        mock_compressor.compress.assert_not_called()

        # Result should contain original content
        assert "Short memory" in result

    def test_no_compression_when_compressor_is_none(self, large_memory_list):
        """Test that no compression happens when compressor is None."""
        result = build_memory_context(large_memory_list, compressor=None)

        # Result should contain original content, not compressed
        assert "<project-memory>" in result
        assert "This is memory item number 0" in result
        # Should be over threshold but not compressed
        assert len(result) > DEFAULT_COMPRESSION_THRESHOLD

    def test_custom_compression_threshold(self, mock_compressor, small_memory_list):
        """Test that custom compression threshold is respected."""
        # Use a very low threshold to force compression on small content
        result = build_memory_context(
            small_memory_list, compressor=mock_compressor, compression_threshold=10
        )

        # Compressor should have been called due to low threshold
        mock_compressor.compress.assert_called_once()

    def test_compression_preserves_outer_tags(
        self, mock_compressor, large_memory_list
    ):
        """Test that compression preserves the outer project-memory tags."""
        result = build_memory_context(large_memory_list, compressor=mock_compressor)

        # Tags should be preserved even after compression
        assert result.startswith("<project-memory>")
        assert result.endswith("</project-memory>")

    def test_compression_only_compresses_inner_content(
        self, mock_compressor, large_memory_list
    ):
        """Test that only inner content (between tags) is compressed."""
        result = build_memory_context(large_memory_list, compressor=mock_compressor)

        # Check that compress was called with inner content (no tags)
        call_args = mock_compressor.compress.call_args
        inner_content = call_args.args[0]
        assert "<project-memory>" not in inner_content
        assert "</project-memory>" not in inner_content

    def test_default_compression_threshold_value(self):
        """Test that default compression threshold is 4000."""
        assert DEFAULT_COMPRESSION_THRESHOLD == 4000
