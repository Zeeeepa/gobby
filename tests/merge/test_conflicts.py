"""Tests for conflict extraction utilities (TDD Red Phase).

Tests for extract_conflict_hunks function that parses Git conflict markers
and extracts conflict regions with context windowing.
"""

from dataclasses import dataclass

import pytest


# =============================================================================
# Import Tests
# =============================================================================


class TestConflictExtractionImport:
    """Tests for module and function import."""

    def test_import_extract_conflict_hunks(self):
        """Test that extract_conflict_hunks can be imported."""
        from gobby.merge.conflicts import extract_conflict_hunks

        assert extract_conflict_hunks is not None

    def test_import_conflict_hunk_dataclass(self):
        """Test that ConflictHunk dataclass can be imported."""
        from gobby.merge.conflicts import ConflictHunk

        assert ConflictHunk is not None


# =============================================================================
# Single Conflict Tests
# =============================================================================


class TestSingleConflict:
    """Tests for extracting a single conflict from file content."""

    def test_extract_single_conflict(self):
        """Test extracting a single conflict region."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """line 1
line 2
<<<<<<< HEAD
our changes
=======
their changes
>>>>>>> feature-branch
line 3
line 4
"""
        hunks = extract_conflict_hunks(content)

        assert len(hunks) == 1
        hunk = hunks[0]
        assert "our changes" in hunk.ours
        assert "their changes" in hunk.theirs

    def test_single_conflict_preserves_markers(self):
        """Test that conflict markers are captured correctly."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """<<<<<<< HEAD
our side
=======
their side
>>>>>>> feature/test
"""
        hunks = extract_conflict_hunks(content)

        assert len(hunks) == 1
        assert hunks[0].ours_marker == "<<<<<<< HEAD"
        assert hunks[0].theirs_marker == ">>>>>>> feature/test"

    def test_single_conflict_line_numbers(self):
        """Test that line numbers are tracked correctly."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """line 1
line 2
<<<<<<< HEAD
conflict content
=======
other content
>>>>>>> branch
line 8
"""
        hunks = extract_conflict_hunks(content)

        assert len(hunks) == 1
        assert hunks[0].start_line == 3
        assert hunks[0].end_line == 7


# =============================================================================
# Multiple Conflicts Tests
# =============================================================================


class TestMultipleConflicts:
    """Tests for extracting multiple conflicts from one file."""

    def test_extract_two_conflicts(self):
        """Test extracting two separate conflicts."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """line 1
<<<<<<< HEAD
first ours
=======
first theirs
>>>>>>> branch
line between
<<<<<<< HEAD
second ours
=======
second theirs
>>>>>>> branch
line end
"""
        hunks = extract_conflict_hunks(content)

        assert len(hunks) == 2
        assert "first ours" in hunks[0].ours
        assert "second ours" in hunks[1].ours

    def test_extract_multiple_conflicts_ordering(self):
        """Test that conflicts are returned in document order."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """<<<<<<< HEAD
a
=======
a2
>>>>>>> b1
some text
<<<<<<< HEAD
b
=======
b2
>>>>>>> b2
more text
<<<<<<< HEAD
c
=======
c2
>>>>>>> b3
"""
        hunks = extract_conflict_hunks(content)

        assert len(hunks) == 3
        assert "a" in hunks[0].ours
        assert "b" in hunks[1].ours
        assert "c" in hunks[2].ours

    def test_adjacent_conflicts(self):
        """Test conflicts that are immediately adjacent."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """<<<<<<< HEAD
first
=======
first other
>>>>>>> branch
<<<<<<< HEAD
second
=======
second other
>>>>>>> branch
"""
        hunks = extract_conflict_hunks(content)

        assert len(hunks) == 2


# =============================================================================
# Context Window Tests
# =============================================================================


class TestContextWindowing:
    """Tests for context window sizing around conflicts."""

    def test_default_context_window(self):
        """Test default context includes surrounding lines."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """line 1
line 2
line 3
<<<<<<< HEAD
conflict
=======
other
>>>>>>> branch
line 4
line 5
line 6
"""
        hunks = extract_conflict_hunks(content, context_lines=2)

        assert len(hunks) == 1
        hunk = hunks[0]
        assert "line 2" in hunk.context_before
        assert "line 3" in hunk.context_before
        assert "line 4" in hunk.context_after
        assert "line 5" in hunk.context_after

    def test_custom_context_window(self):
        """Test custom context window size."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """line 1
line 2
line 3
line 4
<<<<<<< HEAD
conflict
=======
other
>>>>>>> branch
line 5
line 6
line 7
line 8
"""
        hunks = extract_conflict_hunks(content, context_lines=3)

        assert len(hunks) == 1
        hunk = hunks[0]
        assert "line 2" in hunk.context_before
        assert "line 3" in hunk.context_before
        assert "line 4" in hunk.context_before
        assert "line 5" in hunk.context_after
        assert "line 6" in hunk.context_after
        assert "line 7" in hunk.context_after

    def test_zero_context_window(self):
        """Test zero context window returns no surrounding context."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """before
<<<<<<< HEAD
conflict
=======
other
>>>>>>> branch
after
"""
        hunks = extract_conflict_hunks(content, context_lines=0)

        assert len(hunks) == 1
        assert hunks[0].context_before == ""
        assert hunks[0].context_after == ""

    def test_context_at_file_start(self):
        """Test context when conflict is at start of file."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """<<<<<<< HEAD
conflict at start
=======
other
>>>>>>> branch
line after
more after
"""
        hunks = extract_conflict_hunks(content, context_lines=3)

        assert len(hunks) == 1
        # Should handle gracefully when less context available
        assert hunks[0].context_before == ""

    def test_context_at_file_end(self):
        """Test context when conflict is at end of file."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """line before
more before
<<<<<<< HEAD
conflict at end
=======
other
>>>>>>> branch
"""
        hunks = extract_conflict_hunks(content, context_lines=3)

        assert len(hunks) == 1
        # Should handle gracefully when less context available after
        assert "line before" in hunks[0].context_before


# =============================================================================
# Malformed Marker Tests
# =============================================================================


class TestMalformedMarkers:
    """Tests for handling malformed conflict markers."""

    def test_missing_separator(self):
        """Test handling missing ======= separator."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """<<<<<<< HEAD
our stuff
>>>>>>> branch
"""
        # Should either skip or return partial info
        hunks = extract_conflict_hunks(content)
        # Implementation decides behavior - either 0 hunks or partial
        assert isinstance(hunks, list)

    def test_missing_end_marker(self):
        """Test handling missing >>>>>>> end marker."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """<<<<<<< HEAD
our stuff
=======
their stuff
remaining content
"""
        hunks = extract_conflict_hunks(content)
        # Should handle gracefully - either skip or partial
        assert isinstance(hunks, list)

    def test_missing_start_marker(self):
        """Test content with separator and end but no start."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """some content
=======
other content
>>>>>>> branch
"""
        hunks = extract_conflict_hunks(content)
        # Should not crash, return empty or skip
        assert isinstance(hunks, list)

    def test_extra_markers(self):
        """Test handling extra conflict markers."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """<<<<<<< HEAD
our stuff
=======
=======
their stuff
>>>>>>> branch
"""
        hunks = extract_conflict_hunks(content)
        # Should handle gracefully
        assert isinstance(hunks, list)


# =============================================================================
# Empty Conflict Tests
# =============================================================================


class TestEmptyConflicts:
    """Tests for handling empty conflict sections."""

    def test_empty_ours_section(self):
        """Test conflict with empty 'ours' section."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """<<<<<<< HEAD
=======
their content
>>>>>>> branch
"""
        hunks = extract_conflict_hunks(content)

        assert len(hunks) == 1
        assert hunks[0].ours.strip() == ""
        assert "their content" in hunks[0].theirs

    def test_empty_theirs_section(self):
        """Test conflict with empty 'theirs' section."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """<<<<<<< HEAD
our content
=======
>>>>>>> branch
"""
        hunks = extract_conflict_hunks(content)

        assert len(hunks) == 1
        assert "our content" in hunks[0].ours
        assert hunks[0].theirs.strip() == ""

    def test_both_sections_empty(self):
        """Test conflict with both sections empty."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """<<<<<<< HEAD
=======
>>>>>>> branch
"""
        hunks = extract_conflict_hunks(content)

        assert len(hunks) == 1
        assert hunks[0].ours.strip() == ""
        assert hunks[0].theirs.strip() == ""


# =============================================================================
# No Conflicts Tests
# =============================================================================


class TestNoConflicts:
    """Tests for files with no conflicts."""

    def test_no_conflicts_returns_empty(self):
        """Test that file without conflicts returns empty list."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """line 1
line 2
line 3
"""
        hunks = extract_conflict_hunks(content)

        assert hunks == []

    def test_empty_content_returns_empty(self):
        """Test that empty content returns empty list."""
        from gobby.merge.conflicts import extract_conflict_hunks

        hunks = extract_conflict_hunks("")

        assert hunks == []


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_multiline_conflict_content(self):
        """Test conflict with multiple lines on each side."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """<<<<<<< HEAD
line 1 ours
line 2 ours
line 3 ours
=======
line 1 theirs
line 2 theirs
>>>>>>> branch
"""
        hunks = extract_conflict_hunks(content)

        assert len(hunks) == 1
        assert "line 1 ours" in hunks[0].ours
        assert "line 3 ours" in hunks[0].ours
        assert "line 1 theirs" in hunks[0].theirs

    def test_conflict_with_special_characters(self):
        """Test conflict containing special characters."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """<<<<<<< HEAD
>>> not a marker
<<< also not
=== just equals
=======
content with >>>, <<<, ===
>>>>>>> branch
"""
        hunks = extract_conflict_hunks(content)

        assert len(hunks) == 1
        assert ">>> not a marker" in hunks[0].ours

    def test_conflict_marker_in_strings(self):
        """Test that we don't mis-parse markers in quoted strings."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = '''<<<<<<< HEAD
print("<<<<<<< this is a string")
=======
print(">>>>>>> this too")
>>>>>>> branch
'''
        hunks = extract_conflict_hunks(content)

        # Should treat them as content, not markers
        assert len(hunks) == 1

    def test_windows_line_endings(self):
        """Test handling Windows CRLF line endings."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = "<<<<<<< HEAD\r\nour content\r\n=======\r\ntheir content\r\n>>>>>>> branch\r\n"

        hunks = extract_conflict_hunks(content)

        assert len(hunks) == 1
        assert "our content" in hunks[0].ours

    def test_branch_name_with_spaces(self):
        """Test handling branch names with special chars."""
        from gobby.merge.conflicts import extract_conflict_hunks

        content = """<<<<<<< HEAD
ours
=======
theirs
>>>>>>> feature/my-branch-123
"""
        hunks = extract_conflict_hunks(content)

        assert len(hunks) == 1
        assert "feature/my-branch-123" in hunks[0].theirs_marker
