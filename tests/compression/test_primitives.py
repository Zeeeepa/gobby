"""Tests for compression primitives."""

import pytest

from gobby.compression.primitives import dedup, filter_lines, group_lines, truncate

pytestmark = pytest.mark.unit


class TestFilterLines:
    def test_removes_matching_lines(self) -> None:
        lines = ["hello\n", "  \n", "world\n", "\n", "foo\n"]
        result = filter_lines(lines, patterns=[r"^\s*$"])
        assert result == ["hello\n", "world\n", "foo\n"]

    def test_multiple_patterns(self) -> None:
        lines = ["On branch main\n", "M file.py\n", "Your branch is up\n", "?? new.py\n"]
        result = filter_lines(lines, patterns=[r"^On branch", r"^Your branch"])
        assert result == ["M file.py\n", "?? new.py\n"]

    def test_no_match_preserves_all(self) -> None:
        lines = ["a\n", "b\n", "c\n"]
        result = filter_lines(lines, patterns=[r"^zzz"])
        assert result == lines

    def test_empty_input(self) -> None:
        assert filter_lines([], patterns=[r".*"]) == []


class TestTruncate:
    def test_short_input_unchanged(self) -> None:
        lines = ["a\n", "b\n", "c\n"]
        result = truncate(lines, head=5, tail=5)
        assert result == lines

    def test_truncates_middle(self) -> None:
        lines = [f"line{i}\n" for i in range(50)]
        result = truncate(lines, head=5, tail=5)
        assert len(result) == 11  # 5 head + 1 marker + 5 tail
        assert "line0\n" in result[0]
        assert "line49\n" in result[-1]
        assert "40 lines omitted" in result[5]

    def test_exact_boundary(self) -> None:
        lines = [f"line{i}\n" for i in range(10)]
        result = truncate(lines, head=5, tail=5)
        assert result == lines  # exactly head+tail, no truncation


class TestDedup:
    def test_collapses_identical_lines(self) -> None:
        lines = ["error: foo\n"] * 5
        result = dedup(lines)
        assert len(result) == 2  # one line + count
        assert "repeated 5 times" in result[1]

    def test_collapses_near_identical(self) -> None:
        lines = [
            "Processing file 1 of 100\n",
            "Processing file 2 of 100\n",
            "Processing file 3 of 100\n",
            "Done\n",
        ]
        result = dedup(lines)
        assert len(result) <= 3  # collapsed + count + Done
        assert any("repeated" in line for line in result)

    def test_no_duplicates_unchanged(self) -> None:
        lines = ["a\n", "b\n", "c\n"]
        result = dedup(lines)
        assert result == lines

    def test_empty_input(self) -> None:
        assert dedup([]) == []


class TestGroupLines:
    def test_git_status_groups_by_status(self) -> None:
        lines = [
            " M src/foo.py\n",
            " M src/bar.py\n",
            "?? new_file.py\n",
        ]
        result = group_lines(lines, mode="git_status")
        text = "".join(result)
        assert "Modified" in text
        assert "Untracked" in text

    def test_lint_by_rule_groups(self) -> None:
        lines = [
            "src/foo.py:10:5: E501 line too long\n",
            "src/bar.py:20:1: E501 line too long\n",
            "src/baz.py:5:1: F401 unused import\n",
        ]
        result = group_lines(lines, mode="lint_by_rule")
        text = "".join(result)
        assert "E501" in text
        assert "F401" in text
        assert "2 occurrences" in text

    def test_unknown_mode_passthrough(self) -> None:
        lines = ["a\n", "b\n"]
        result = group_lines(lines, mode="nonexistent_mode")
        assert result == lines

    def test_test_failures_extracts_failures(self) -> None:
        lines = [
            "test_foo ... ok\n",
            "test_bar ... ok\n",
            "FAILED test_baz\n",
            "  AssertionError: 1 != 2\n",
            "1 passed, 1 failed\n",
        ]
        result = group_lines(lines, mode="test_failures")
        text = "".join(result)
        assert "FAILED" in text

    def test_pytest_failures_extracts_section(self) -> None:
        lines = [
            "collected 5 items\n",
            "tests/test_a.py .....PASSED\n",
            "tests/test_b.py .F.\n",
            "======= FAILURES =======\n",
            "_______ test_thing _______\n",
            "    assert 1 == 2\n",
            "======= short test summary =======\n",
            "FAILED tests/test_b.py::test_thing\n",
            "======= 1 failed, 4 passed =======\n",
        ]
        result = group_lines(lines, mode="pytest_failures")
        text = "".join(result)
        assert "FAILURES" in text
        assert "assert 1 == 2" in text
        assert "1 failed" in text

    def test_by_file_groups_grep_output(self) -> None:
        lines = [
            "src/foo.py:10:match1\n",
            "src/foo.py:20:match2\n",
            "src/bar.py:5:match3\n",
        ]
        result = group_lines(lines, mode="by_file")
        text = "".join(result)
        assert "src/foo.py (2 matches)" in text
        assert "src/bar.py (1 match)" in text

    def test_errors_warnings_separates(self) -> None:
        lines = [
            "error: undefined variable\n",
            "warning: unused import\n",
            "error: type mismatch\n",
            "Build complete.\n",
        ]
        result = group_lines(lines, mode="errors_warnings")
        text = "".join(result)
        assert "Errors (2)" in text
        assert "Warnings (1)" in text

    def test_errors_warnings_no_errors_no_warnings(self) -> None:
        """When no errors or warnings, return original lines."""
        lines = ["Build complete.\n", "Done.\n"]
        result = group_lines(lines, mode="errors_warnings")
        assert result == lines

    def test_errors_warnings_many_errors_truncated(self) -> None:
        """Errors beyond 20 are indicated with a truncation marker."""
        lines = [f"error: issue {i}\n" for i in range(25)]
        result = group_lines(lines, mode="errors_warnings")
        text = "".join(result)
        assert "Errors (25)" in text
        assert "5 more errors" in text

    def test_errors_warnings_many_warnings_truncated(self) -> None:
        """Warnings beyond 10 are indicated with a truncation marker."""
        lines = [f"warning: issue {i}\n" for i in range(15)]
        result = group_lines(lines, mode="errors_warnings")
        text = "".join(result)
        assert "Warnings (15)" in text
        assert "5 more warnings" in text

    def test_by_extension_groups_files(self) -> None:
        """Group files by extension."""
        lines = [
            "src/foo.py\n",
            "src/bar.py\n",
            "src/baz.js\n",
            "README.md\n",
        ]
        result = group_lines(lines, mode="by_extension")
        text = "".join(result)
        assert ".py (2 files)" in text
        assert ".js (1 files)" in text
        assert ".md (1 files)" in text

    def test_by_extension_no_extension(self) -> None:
        """Files without extension are grouped as (no ext)."""
        lines = ["Makefile\n", "Dockerfile\n"]
        result = group_lines(lines, mode="by_extension")
        text = "".join(result)
        assert "(no ext) (2 files)" in text

    def test_by_extension_empty_input(self) -> None:
        """Empty input returns original lines."""
        result = group_lines([], mode="by_extension")
        assert result == []

    def test_by_extension_many_files_truncated(self) -> None:
        """Extensions with >10 files show truncation."""
        lines = [f"file{i}.py\n" for i in range(15)]
        result = group_lines(lines, mode="by_extension")
        text = "".join(result)
        assert "5 more" in text

    def test_by_directory_groups_paths(self) -> None:
        """Group paths by parent directory."""
        lines = [
            "src/foo.py\n",
            "src/bar.py\n",
            "tests/test_foo.py\n",
        ]
        result = group_lines(lines, mode="by_directory")
        text = "".join(result)
        assert "src/ (2 items)" in text
        assert "tests/ (1 items)" in text

    def test_by_directory_no_slash(self) -> None:
        """Paths without slash are grouped under '.'."""
        lines = ["file.py\n"]
        result = group_lines(lines, mode="by_directory")
        text = "".join(result)
        assert "./ (1 items)" in text

    def test_by_directory_empty_input(self) -> None:
        """Empty input returns original lines."""
        result = group_lines([], mode="by_directory")
        assert result == []

    def test_by_directory_many_items_truncated(self) -> None:
        """Directories with >10 items show truncation."""
        lines = [f"src/file{i}.py\n" for i in range(15)]
        result = group_lines(lines, mode="by_directory")
        text = "".join(result)
        assert "5 more" in text

    def test_by_file_single_match(self) -> None:
        """Single match shows 'match' instead of 'matches'."""
        lines = ["src/foo.py:10:content\n"]
        result = group_lines(lines, mode="by_file")
        text = "".join(result)
        assert "1 match)" in text

    def test_by_file_no_matches_returns_original(self) -> None:
        """Lines without file:line format are returned as-is."""
        lines = ["no match here\n", "also no match\n"]
        result = group_lines(lines, mode="by_file")
        assert result == lines

    def test_by_file_many_matches_truncated(self) -> None:
        """Files with >5 matches show truncation."""
        lines = [f"src/foo.py:{i}:match{i}\n" for i in range(10)]
        result = group_lines(lines, mode="by_file")
        text = "".join(result)
        assert "5 more" in text

    def test_git_status_many_files_truncated(self) -> None:
        """Git status groups with >20 files show truncation."""
        lines = [f" M src/file{i}.py\n" for i in range(25)]
        result = group_lines(lines, mode="git_status")
        text = "".join(result)
        assert "5 more" in text

    def test_git_status_empty_lines_skipped(self) -> None:
        """Empty lines in git status input are skipped."""
        lines = [" M file.py\n", "\n", "?? new.py\n"]
        result = group_lines(lines, mode="git_status")
        text = "".join(result)
        assert "Modified" in text
        assert "Untracked" in text

    def test_git_status_unknown_status(self) -> None:
        """Unknown status letters are used as-is."""
        lines = ["  ! ignored.py\n"]
        result = group_lines(lines, mode="git_status")
        text = "".join(result)
        assert "! (1)" in text

    def test_lint_by_rule_no_groups(self) -> None:
        """Lines not matching lint patterns return original lines."""
        lines = ["no lint here\n"]
        result = group_lines(lines, mode="lint_by_rule")
        assert result == lines

    def test_lint_by_rule_many_occurrences_truncated(self) -> None:
        """Lint rules with >5 occurrences show truncation."""
        lines = [f"src/file{i}.py:1:1: E501 line too long\n" for i in range(10)]
        result = group_lines(lines, mode="lint_by_rule")
        text = "".join(result)
        assert "5 more" in text

    def test_lint_by_rule_mypy_format(self) -> None:
        """Mypy-style lint output is grouped by [code]."""
        lines = [
            'src/foo.py:10: error: incompatible types [assignment]\n',
            'src/bar.py:20: error: missing return [return-value]\n',
            'src/baz.py:30: error: incompatible types [assignment]\n',
        ]
        result = group_lines(lines, mode="lint_by_rule")
        text = "".join(result)
        assert "assignment" in text
        assert "2 occurrences" in text

    def test_test_failures_all_passed(self) -> None:
        """When all tests pass and no summary, show 'All tests passed.'."""
        lines = ["test_a ... ok\n", "test_b ... ok\n"]
        result = group_lines(lines, mode="test_failures")
        text = "".join(result)
        assert "All tests passed" in text

    def test_test_failures_with_summary_line(self) -> None:
        """When no failures but summary line exists, return the summary."""
        lines = ["test_a ... ok\n", "5 passed, 0 failed\n"]
        result = group_lines(lines, mode="test_failures")
        text = "".join(result)
        assert "5 passed" in text

    def test_pytest_failures_no_failures_falls_back(self) -> None:
        """When no FAILURES section, falls back to test_failures logic."""
        lines = ["test_a ... ok\n", "1 passed\n"]
        result = group_lines(lines, mode="pytest_failures")
        text = "".join(result)
        assert "1 passed" in text


class TestTruncatePerSection:
    """Tests for per-section truncation."""

    def test_per_file_truncation(self) -> None:
        """Truncation per section using file markers."""
        lines = ["--- file1.py\n"]
        lines.extend([f"  line{i}\n" for i in range(20)])
        lines.append("--- file2.py\n")
        lines.extend([f"  line{i}\n" for i in range(5)])

        result = truncate(lines, per_file_lines=5, file_marker=r"^---")
        text = "".join(result)
        assert "omitted in section" in text
        # file2 should be unchanged (only 5+1 lines total)

    def test_per_file_no_truncation_needed(self) -> None:
        """Sections within limit are not truncated."""
        lines = ["--- file1.py\n", "  line1\n", "  line2\n"]
        result = truncate(lines, per_file_lines=10, file_marker=r"^---")
        assert result == lines

    def test_per_file_single_section(self) -> None:
        """Single section is truncated correctly."""
        lines = [f"line{i}\n" for i in range(20)]
        result = truncate(lines, per_file_lines=5, file_marker=r"^FILE:")
        # No marker matches, so it's one big section
        text = "".join(result)
        assert "omitted in section" in text


class TestDedupEdgeCases:
    """Additional edge case tests for dedup."""

    def test_single_line(self) -> None:
        """Single line returns as-is."""
        result = dedup(["hello\n"])
        assert result == ["hello\n"]

    def test_two_identical_lines(self) -> None:
        """Two identical lines show the line and a repeat count."""
        result = dedup(["same\n", "same\n"])
        assert len(result) == 2
        assert "repeated 2 times" in result[1]

    def test_alternating_lines_not_collapsed(self) -> None:
        """Alternating different lines are not collapsed."""
        lines = ["a\n", "b\n", "a\n", "b\n"]
        result = dedup(lines)
        assert result == lines

    def test_numbers_only_difference(self) -> None:
        """Lines differing only in numbers are considered near-identical."""
        lines = [
            "Step 1 done at 100ms\n",
            "Step 2 done at 200ms\n",
            "Step 3 done at 300ms\n",
        ]
        result = dedup(lines)
        assert any("repeated" in line for line in result)


class TestFilterLinesEdgeCases:
    """Additional edge cases for filter_lines."""

    def test_pattern_cache_reuse(self) -> None:
        """Same pattern is compiled only once (cache hit)."""
        from gobby.compression.primitives import _PATTERN_CACHE

        pattern = r"^UNIQUE_TEST_PATTERN_12345$"
        _PATTERN_CACHE.pop(pattern, None)
        filter_lines(["test\n"], patterns=[pattern])
        assert pattern in _PATTERN_CACHE
        # Second call reuses cached pattern
        filter_lines(["test\n"], patterns=[pattern])

    def test_all_lines_removed(self) -> None:
        """When all lines match the pattern, result is empty."""
        lines = ["remove me\n", "and me\n"]
        result = filter_lines(lines, patterns=[r".*"])
        assert result == []
