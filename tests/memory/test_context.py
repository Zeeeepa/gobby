"""Tests for memory context building."""

from gobby.memory.context import (
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
