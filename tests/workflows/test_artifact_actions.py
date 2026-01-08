"""Comprehensive tests for artifact_actions.py module.

Tests cover:
- capture_artifact: glob pattern matching, deterministic selection, state storage
- read_artifact: artifact key lookup, glob pattern lookup, file reading, error handling
"""

import os
from unittest.mock import MagicMock

import pytest

from gobby.workflows.artifact_actions import capture_artifact, read_artifact
from gobby.workflows.definitions import WorkflowState


@pytest.fixture
def workflow_state():
    """Create a fresh WorkflowState for testing."""
    return WorkflowState(
        session_id="test-session-id",
        workflow_name="test-workflow",
        step="test-step",
    )


@pytest.fixture
def temp_artifact_dir(tmp_path):
    """Create a temporary directory with test files."""
    # Create some test files
    (tmp_path / "file_a.txt").write_text("Content A")
    (tmp_path / "file_b.txt").write_text("Content B")
    (tmp_path / "file_c.txt").write_text("Content C")
    (tmp_path / "plan.md").write_text("# Plan\n\nThis is the plan.")
    (tmp_path / "data.json").write_text('{"key": "value"}')

    # Create nested directory structure
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "deep_file.txt").write_text("Deep content")

    return tmp_path


class TestCaptureArtifact:
    """Tests for capture_artifact function."""

    def test_capture_artifact_returns_none_when_no_pattern(self, workflow_state):
        """Should return None when pattern is None."""
        result = capture_artifact(workflow_state, pattern=None)
        assert result is None

    def test_capture_artifact_returns_none_when_pattern_empty(self, workflow_state):
        """Should return None when pattern is empty string."""
        result = capture_artifact(workflow_state, pattern="")
        assert result is None

    def test_capture_artifact_returns_none_when_no_match(self, workflow_state, temp_artifact_dir):
        """Should return None when glob pattern doesn't match any files."""
        # Use a pattern that won't match anything
        result = capture_artifact(
            workflow_state,
            pattern=str(temp_artifact_dir / "nonexistent_*.xyz"),
        )
        assert result is None

    def test_capture_artifact_matches_single_file(self, workflow_state, temp_artifact_dir):
        """Should capture a single matching file."""
        pattern = str(temp_artifact_dir / "plan.md")
        result = capture_artifact(workflow_state, pattern=pattern)

        assert result is not None
        assert "captured" in result
        assert result["captured"] == str(temp_artifact_dir / "plan.md")

    def test_capture_artifact_matches_glob_pattern(self, workflow_state, temp_artifact_dir):
        """Should capture files matching glob pattern."""
        pattern = str(temp_artifact_dir / "*.txt")
        result = capture_artifact(workflow_state, pattern=pattern)

        assert result is not None
        assert "captured" in result
        # Should capture the lexicographically smallest match (file_a.txt)
        assert result["captured"].endswith("file_a.txt")

    def test_capture_artifact_selects_lexicographically_smallest(
        self, workflow_state, temp_artifact_dir
    ):
        """Should select lexicographically smallest file for determinism."""
        pattern = str(temp_artifact_dir / "file_*.txt")
        result = capture_artifact(workflow_state, pattern=pattern)

        assert result is not None
        # file_a.txt < file_b.txt < file_c.txt lexicographically
        assert result["captured"].endswith("file_a.txt")

    def test_capture_artifact_recursive_glob(self, workflow_state, temp_artifact_dir):
        """Should support recursive glob patterns."""
        pattern = str(temp_artifact_dir / "**" / "*.txt")
        result = capture_artifact(workflow_state, pattern=pattern)

        assert result is not None
        assert "captured" in result
        # Should find files in nested directories too

    def test_capture_artifact_saves_to_state_with_save_as(self, workflow_state, temp_artifact_dir):
        """Should save artifact path to state.artifacts when save_as is provided."""
        pattern = str(temp_artifact_dir / "plan.md")
        result = capture_artifact(
            workflow_state,
            pattern=pattern,
            save_as="current_plan",
        )

        assert result is not None
        assert "current_plan" in workflow_state.artifacts
        assert workflow_state.artifacts["current_plan"] == result["captured"]

    def test_capture_artifact_initializes_artifacts_dict_if_none(
        self, workflow_state, temp_artifact_dir
    ):
        """Should initialize state.artifacts if it's None."""
        # Set artifacts to None (edge case)
        workflow_state.artifacts = None  # type: ignore

        pattern = str(temp_artifact_dir / "plan.md")
        result = capture_artifact(
            workflow_state,
            pattern=pattern,
            save_as="my_artifact",
        )

        assert result is not None
        assert workflow_state.artifacts is not None
        assert "my_artifact" in workflow_state.artifacts

    def test_capture_artifact_without_save_as_does_not_modify_state(
        self, workflow_state, temp_artifact_dir
    ):
        """Should not modify state.artifacts when save_as is None."""
        original_artifacts = dict(workflow_state.artifacts)
        pattern = str(temp_artifact_dir / "plan.md")

        result = capture_artifact(workflow_state, pattern=pattern, save_as=None)

        assert result is not None
        assert workflow_state.artifacts == original_artifacts

    def test_capture_artifact_returns_absolute_path(self, workflow_state, temp_artifact_dir):
        """Should return absolute file path."""
        pattern = str(temp_artifact_dir / "plan.md")
        result = capture_artifact(workflow_state, pattern=pattern)

        assert result is not None
        assert os.path.isabs(result["captured"])

    def test_capture_artifact_multiple_captures(self, workflow_state, temp_artifact_dir):
        """Should handle multiple captures with different save_as names."""
        capture_artifact(
            workflow_state,
            pattern=str(temp_artifact_dir / "plan.md"),
            save_as="plan",
        )
        capture_artifact(
            workflow_state,
            pattern=str(temp_artifact_dir / "data.json"),
            save_as="data",
        )

        assert "plan" in workflow_state.artifacts
        assert "data" in workflow_state.artifacts
        assert workflow_state.artifacts["plan"].endswith("plan.md")
        assert workflow_state.artifacts["data"].endswith("data.json")


class TestReadArtifact:
    """Tests for read_artifact function."""

    def test_read_artifact_returns_none_when_no_pattern(self, workflow_state):
        """Should return None when pattern is None."""
        result = read_artifact(workflow_state, pattern=None, variable_name="var")
        assert result is None

    def test_read_artifact_returns_none_when_pattern_empty(self, workflow_state):
        """Should return None when pattern is empty string."""
        result = read_artifact(workflow_state, pattern="", variable_name="var")
        assert result is None

    def test_read_artifact_returns_none_when_no_variable_name(self, workflow_state):
        """Should return None and log warning when variable_name is missing."""
        result = read_artifact(workflow_state, pattern="some_key", variable_name=None)
        assert result is None

    def test_read_artifact_returns_none_when_variable_name_empty(self, workflow_state):
        """Should return None when variable_name is empty string."""
        result = read_artifact(workflow_state, pattern="some_key", variable_name="")
        assert result is None

    def test_read_artifact_from_artifact_key(self, workflow_state, temp_artifact_dir):
        """Should read content from file referenced by artifact key."""
        # First capture an artifact
        artifact_path = str(temp_artifact_dir / "plan.md")
        workflow_state.artifacts["my_plan"] = artifact_path

        result = read_artifact(
            workflow_state,
            pattern="my_plan",
            variable_name="plan_content",
        )

        assert result is not None
        assert result["read_artifact"] is True
        assert result["variable"] == "plan_content"
        assert result["length"] > 0
        assert workflow_state.variables["plan_content"] == "# Plan\n\nThis is the plan."

    def test_read_artifact_from_glob_pattern(self, workflow_state, temp_artifact_dir):
        """Should read content from file matching glob pattern."""
        pattern = str(temp_artifact_dir / "plan.md")
        result = read_artifact(
            workflow_state,
            pattern=pattern,
            variable_name="plan_var",
        )

        assert result is not None
        assert result["read_artifact"] is True
        assert workflow_state.variables["plan_var"] == "# Plan\n\nThis is the plan."

    def test_read_artifact_glob_pattern_selects_first_sorted_match(
        self, workflow_state, temp_artifact_dir
    ):
        """Should select first file alphabetically when multiple matches."""
        pattern = str(temp_artifact_dir / "file_*.txt")
        result = read_artifact(
            workflow_state,
            pattern=pattern,
            variable_name="file_content",
        )

        assert result is not None
        # file_a.txt is first alphabetically
        assert workflow_state.variables["file_content"] == "Content A"

    def test_read_artifact_recursive_glob(self, workflow_state, temp_artifact_dir):
        """Should support recursive glob patterns."""
        pattern = str(temp_artifact_dir / "**" / "deep_file.txt")
        result = read_artifact(
            workflow_state,
            pattern=pattern,
            variable_name="deep_content",
        )

        assert result is not None
        assert workflow_state.variables["deep_content"] == "Deep content"

    def test_read_artifact_returns_none_when_file_not_found(
        self, workflow_state, temp_artifact_dir
    ):
        """Should return None and log warning when file doesn't exist."""
        result = read_artifact(
            workflow_state,
            pattern=str(temp_artifact_dir / "nonexistent.txt"),
            variable_name="var",
        )
        assert result is None

    def test_read_artifact_returns_none_when_artifact_key_file_missing(
        self,
        workflow_state,
    ):
        """Should return None when artifact key points to non-existent file."""
        workflow_state.artifacts["missing_file"] = "/nonexistent/path/file.txt"

        result = read_artifact(
            workflow_state,
            pattern="missing_file",
            variable_name="var",
        )
        assert result is None

    def test_read_artifact_initializes_variables_dict_if_none(
        self, workflow_state, temp_artifact_dir
    ):
        """Should initialize state.variables if it's None."""
        workflow_state.variables = None  # type: ignore
        pattern = str(temp_artifact_dir / "plan.md")

        result = read_artifact(
            workflow_state,
            pattern=pattern,
            variable_name="plan_content",
        )

        assert result is not None
        assert workflow_state.variables is not None
        assert "plan_content" in workflow_state.variables

    def test_read_artifact_handles_binary_content_with_replace(self, workflow_state, tmp_path):
        """Should handle non-UTF8 content with error replacement."""
        # Create a file with invalid UTF-8 bytes
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"Hello \xff\xfe World")

        result = read_artifact(
            workflow_state,
            pattern=str(binary_file),
            variable_name="binary_content",
        )

        assert result is not None
        # Content should be read with replacement characters
        assert "Hello" in workflow_state.variables["binary_content"]
        assert "World" in workflow_state.variables["binary_content"]

    def test_read_artifact_handles_read_exception(self, workflow_state, tmp_path):
        """Should return None and log error on read exception."""
        # Create a directory instead of a file to cause read error
        dir_path = tmp_path / "not_a_file"
        dir_path.mkdir()

        result = read_artifact(
            workflow_state,
            pattern=str(dir_path),
            variable_name="var",
        )
        # Reading a directory should fail
        assert result is None

    def test_read_artifact_artifact_key_takes_precedence(self, workflow_state, temp_artifact_dir):
        """Artifact key lookup should take precedence over glob pattern."""
        # Store a file path under an artifact key that looks like a glob pattern
        # The key "*.txt" should be treated as a literal key, not a glob
        workflow_state.artifacts["*.txt"] = str(temp_artifact_dir / "plan.md")

        result = read_artifact(
            workflow_state,
            pattern="*.txt",
            variable_name="content",
        )

        assert result is not None
        # Should read plan.md content, not any *.txt files
        assert "# Plan" in workflow_state.variables["content"]

    def test_read_artifact_empty_artifacts_dict(self, workflow_state, temp_artifact_dir):
        """Should handle empty artifacts dict and fall back to glob."""
        workflow_state.artifacts = {}
        pattern = str(temp_artifact_dir / "plan.md")

        result = read_artifact(
            workflow_state,
            pattern=pattern,
            variable_name="plan_content",
        )

        assert result is not None
        assert workflow_state.variables["plan_content"] == "# Plan\n\nThis is the plan."

    def test_read_artifact_none_artifacts(self, workflow_state, temp_artifact_dir):
        """Should handle None artifacts and fall back to glob."""
        workflow_state.artifacts = None  # type: ignore
        pattern = str(temp_artifact_dir / "plan.md")

        result = read_artifact(
            workflow_state,
            pattern=pattern,
            variable_name="plan_content",
        )

        assert result is not None
        assert result["read_artifact"] is True

    def test_read_artifact_returns_correct_length(self, workflow_state, temp_artifact_dir):
        """Should return correct content length in result."""
        pattern = str(temp_artifact_dir / "plan.md")
        expected_content = "# Plan\n\nThis is the plan."

        result = read_artifact(
            workflow_state,
            pattern=pattern,
            variable_name="plan_content",
        )

        assert result is not None
        assert result["length"] == len(expected_content)

    def test_read_artifact_empty_file(self, workflow_state, tmp_path):
        """Should handle reading empty files."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        result = read_artifact(
            workflow_state,
            pattern=str(empty_file),
            variable_name="empty_content",
        )

        assert result is not None
        assert result["read_artifact"] is True
        assert result["length"] == 0
        assert workflow_state.variables["empty_content"] == ""

    def test_read_artifact_large_file(self, workflow_state, tmp_path):
        """Should handle reading large files."""
        large_file = tmp_path / "large.txt"
        large_content = "x" * 100000  # 100KB
        large_file.write_text(large_content)

        result = read_artifact(
            workflow_state,
            pattern=str(large_file),
            variable_name="large_content",
        )

        assert result is not None
        assert result["length"] == 100000
        assert workflow_state.variables["large_content"] == large_content


@pytest.mark.integration
class TestIntegrationCaptureAndRead:
    """Integration tests for capture and read workflow."""

    def test_capture_then_read_workflow(self, workflow_state, temp_artifact_dir):
        """Should capture artifact and then read its content."""
        # Step 1: Capture the artifact
        capture_result = capture_artifact(
            workflow_state,
            pattern=str(temp_artifact_dir / "data.json"),
            save_as="json_data",
        )
        assert capture_result is not None

        # Step 2: Read the artifact by key
        read_result = read_artifact(
            workflow_state,
            pattern="json_data",
            variable_name="json_content",
        )

        assert read_result is not None
        assert workflow_state.variables["json_content"] == '{"key": "value"}'

    def test_multiple_captures_and_reads(self, workflow_state, temp_artifact_dir):
        """Should handle multiple capture and read operations."""
        # Capture multiple artifacts
        capture_artifact(
            workflow_state,
            pattern=str(temp_artifact_dir / "plan.md"),
            save_as="plan",
        )
        capture_artifact(
            workflow_state,
            pattern=str(temp_artifact_dir / "data.json"),
            save_as="data",
        )

        # Read both
        read_artifact(
            workflow_state,
            pattern="plan",
            variable_name="plan_content",
        )
        read_artifact(
            workflow_state,
            pattern="data",
            variable_name="data_content",
        )

        assert "plan_content" in workflow_state.variables
        assert "data_content" in workflow_state.variables
        assert "# Plan" in workflow_state.variables["plan_content"]
        assert '{"key": "value"}' in workflow_state.variables["data_content"]


class TestEdgeCases:
    """Edge case tests for artifact actions."""

    def test_capture_artifact_special_characters_in_filename(self, workflow_state, tmp_path):
        """Should handle filenames with special characters."""
        special_file = tmp_path / "file with spaces & symbols.txt"
        special_file.write_text("Special content")

        result = capture_artifact(
            workflow_state,
            pattern=str(special_file),
            save_as="special",
        )

        assert result is not None
        assert workflow_state.artifacts["special"].endswith("file with spaces & symbols.txt")

    def test_read_artifact_unicode_content(self, workflow_state, tmp_path):
        """Should handle unicode content correctly."""
        unicode_file = tmp_path / "unicode.txt"
        unicode_content = "Hello, \u4e16\u754c! \U0001f600 \u00e9\u00e8\u00ea"
        unicode_file.write_text(unicode_content, encoding="utf-8")

        result = read_artifact(
            workflow_state,
            pattern=str(unicode_file),
            variable_name="unicode_var",
        )

        assert result is not None
        assert workflow_state.variables["unicode_var"] == unicode_content

    def test_capture_artifact_symlink(self, workflow_state, tmp_path):
        """Should handle symlinks correctly."""
        original = tmp_path / "original.txt"
        original.write_text("Original content")

        link = tmp_path / "link.txt"
        try:
            link.symlink_to(original)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

        result = capture_artifact(
            workflow_state,
            pattern=str(link),
            save_as="linked",
        )

        assert result is not None
        # The captured path should be the absolute path to the symlink
        assert result["captured"].endswith("link.txt")

    def test_read_artifact_through_symlink(self, workflow_state, tmp_path):
        """Should read content through symlink."""
        original = tmp_path / "original.txt"
        original.write_text("Symlinked content")

        link = tmp_path / "link.txt"
        try:
            link.symlink_to(original)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

        result = read_artifact(
            workflow_state,
            pattern=str(link),
            variable_name="link_content",
        )

        assert result is not None
        assert workflow_state.variables["link_content"] == "Symlinked content"

    def test_capture_artifact_relative_becomes_absolute(self, workflow_state, tmp_path):
        """Captured paths should be absolute even from relative patterns."""
        # Create file in temp dir
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        # Change to temp dir and use relative pattern
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = capture_artifact(
                workflow_state,
                pattern="test.txt",
                save_as="test",
            )
            assert result is not None
            assert os.path.isabs(result["captured"])
        finally:
            os.chdir(original_cwd)

    def test_read_artifact_preserves_newlines(self, workflow_state, tmp_path):
        """Should preserve different newline styles."""
        # Test with Unix-style newlines
        unix_file = tmp_path / "unix.txt"
        unix_content = "line1\nline2\nline3"
        unix_file.write_text(unix_content)

        result = read_artifact(
            workflow_state,
            pattern=str(unix_file),
            variable_name="unix_content",
        )

        assert result is not None
        assert workflow_state.variables["unix_content"] == unix_content
        assert workflow_state.variables["unix_content"].count("\n") == 2


class TestMockedState:
    """Tests using mocked state objects."""

    def test_capture_artifact_with_mock_state(self, tmp_path):
        """Should work with a mock state object that has artifacts attribute."""
        mock_state = MagicMock()
        mock_state.artifacts = None

        test_file = tmp_path / "test.txt"
        test_file.write_text("mock test")

        result = capture_artifact(
            mock_state,
            pattern=str(test_file),
            save_as="mock_artifact",
        )

        assert result is not None
        # Verify artifacts dict was created and populated
        assert mock_state.artifacts is not None
        assert "mock_artifact" in mock_state.artifacts

    def test_read_artifact_with_mock_state(self, tmp_path):
        """Should work with a mock state object."""
        mock_state = MagicMock()
        mock_state.artifacts = {}
        mock_state.variables = None

        test_file = tmp_path / "test.txt"
        test_file.write_text("mock content")

        result = read_artifact(
            mock_state,
            pattern=str(test_file),
            variable_name="mock_var",
        )

        assert result is not None
        assert mock_state.variables is not None
        assert mock_state.variables["mock_var"] == "mock content"
