"""Tests for ID generation utilities."""

import pytest

from gobby.utils.id import generate_prefixed_id

pytestmark = pytest.mark.unit

class TestGeneratePrefixedId:
    """Tests for generate_prefixed_id function."""

    def test_basic_generation(self) -> None:
        """Test basic ID generation with content."""
        result = generate_prefixed_id("mm", "test content")
        assert result.startswith("mm-")
        assert len(result) == 11  # "mm-" + 8 chars

    def test_deterministic_with_content(self) -> None:
        """Test that same content produces same ID."""
        id1 = generate_prefixed_id("mm", "same content")
        id2 = generate_prefixed_id("mm", "same content")
        assert id1 == id2

    def test_random_without_content(self) -> None:
        """Test that None content produces random IDs."""
        id1 = generate_prefixed_id("mm")
        id2 = generate_prefixed_id("mm")
        # Should be different (extremely high probability)
        assert id1 != id2

    def test_custom_length(self) -> None:
        """Test custom length parameter."""
        result = generate_prefixed_id("mm", "test", length=12)
        assert result.startswith("mm-")
        assert len(result) == 15  # "mm-" + 12 chars

    def test_empty_prefix_raises(self) -> None:
        """Test that empty prefix raises ValueError."""
        with pytest.raises(ValueError, match="prefix cannot be empty"):
            generate_prefixed_id("", "content")

    def test_length_zero_raises(self) -> None:
        """Test that length=0 raises ValueError."""
        with pytest.raises(ValueError, match="length must be positive"):
            generate_prefixed_id("mm", "content", length=0)

    def test_length_negative_raises(self) -> None:
        """Test that negative length raises ValueError."""
        with pytest.raises(ValueError, match="length must be positive"):
            generate_prefixed_id("mm", "content", length=-1)

    def test_length_too_large_raises(self) -> None:
        """Test that length > 64 raises ValueError."""
        with pytest.raises(ValueError, match="length cannot exceed 64"):
            generate_prefixed_id("mm", "content", length=65)

    def test_max_valid_length(self) -> None:
        """Test maximum valid length (64)."""
        result = generate_prefixed_id("mm", "content", length=64)
        assert result.startswith("mm-")
        assert len(result) == 67  # "mm-" + 64 chars

    def test_different_prefixes(self) -> None:
        """Test different prefixes work correctly."""
        mem_id = generate_prefixed_id("mem", "test")
        task_id = generate_prefixed_id("task", "test")
        assert mem_id.startswith("mem-")
        assert task_id.startswith("task-")
