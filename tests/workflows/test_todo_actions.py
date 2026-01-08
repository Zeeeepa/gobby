"""Tests for todo file workflow actions.

Tests the write_todos and mark_todo_complete functions from todo_actions.py.
"""

import os
from unittest.mock import patch

import pytest

from gobby.workflows.todo_actions import mark_todo_complete, write_todos


class TestWriteTodos:
    """Tests for the write_todos function."""

    def test_write_todos_basic(self, tmp_path):
        """Test writing a basic list of todos to a file."""
        todo_file = tmp_path / "TODO.md"
        todos = ["Buy milk", "Walk the dog", "Fix bug"]

        result = write_todos(todos, filename=str(todo_file))

        assert result["todos_written"] == 3
        assert result["file"] == str(todo_file)

        content = todo_file.read_text()
        assert "# TODOs" in content
        assert "- [ ] Buy milk" in content
        assert "- [ ] Walk the dog" in content
        assert "- [ ] Fix bug" in content

    def test_write_todos_default_filename(self, tmp_path, monkeypatch):
        """Test using default filename TODO.md."""
        monkeypatch.chdir(tmp_path)
        todos = ["Task one"]

        result = write_todos(todos)

        assert result["todos_written"] == 1
        assert result["file"] == "TODO.md"
        assert (tmp_path / "TODO.md").exists()

    def test_write_todos_empty_list(self, tmp_path):
        """Test writing an empty list of todos."""
        todo_file = tmp_path / "TODO.md"
        todos = []

        result = write_todos(todos, filename=str(todo_file))

        assert result["todos_written"] == 0
        content = todo_file.read_text()
        assert "# TODOs" in content

    def test_write_todos_single_item(self, tmp_path):
        """Test writing a single todo item."""
        todo_file = tmp_path / "TODO.md"
        todos = ["Single task"]

        result = write_todos(todos, filename=str(todo_file))

        assert result["todos_written"] == 1
        content = todo_file.read_text()
        assert "- [ ] Single task" in content

    def test_write_todos_overwrite_mode(self, tmp_path):
        """Test that write mode overwrites existing content."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("Old content\n- [ ] Old task\n")

        result = write_todos(["New task"], filename=str(todo_file), mode="w")

        assert result["todos_written"] == 1
        content = todo_file.read_text()
        assert "Old content" not in content
        assert "Old task" not in content
        assert "- [ ] New task" in content
        assert "# TODOs" in content

    def test_write_todos_append_mode_existing_file(self, tmp_path):
        """Test appending todos to an existing file."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("# TODOs\n\n- [ ] Existing task\n")

        result = write_todos(["Appended task"], filename=str(todo_file), mode="append")

        assert result["todos_written"] == 1
        content = todo_file.read_text()
        assert "# TODOs" in content  # Original header preserved
        assert "- [ ] Existing task" in content
        assert "- [ ] Appended task" in content

    def test_write_todos_append_mode_nonexistent_file(self, tmp_path):
        """Test append mode on a file that doesn't exist creates new file."""
        todo_file = tmp_path / "NEW_TODO.md"

        result = write_todos(["First task"], filename=str(todo_file), mode="append")

        assert result["todos_written"] == 1
        content = todo_file.read_text()
        # Should create file with header since file didn't exist
        assert "# TODOs" in content
        assert "- [ ] First task" in content

    def test_write_todos_special_characters(self, tmp_path):
        """Test writing todos with special characters."""
        todo_file = tmp_path / "TODO.md"
        todos = [
            "Fix bug #123",
            "Review PR: user/repo#456",
            "Add [feature] support",
            "Test `code` blocks",
        ]

        result = write_todos(todos, filename=str(todo_file))

        assert result["todos_written"] == 4
        content = todo_file.read_text()
        assert "- [ ] Fix bug #123" in content
        assert "- [ ] Review PR: user/repo#456" in content
        assert "- [ ] Add [feature] support" in content
        assert "- [ ] Test `code` blocks" in content

    def test_write_todos_unicode(self, tmp_path):
        """Test writing todos with unicode characters."""
        todo_file = tmp_path / "TODO.md"
        todos = ["Fix emoji support", "Add internationalization"]

        result = write_todos(todos, filename=str(todo_file))

        assert result["todos_written"] == 2
        content = todo_file.read_text()
        assert "- [ ] Fix emoji support" in content

    def test_write_todos_multiline_format(self, tmp_path):
        """Test that each todo is on its own line."""
        todo_file = tmp_path / "TODO.md"
        todos = ["Task 1", "Task 2", "Task 3"]

        write_todos(todos, filename=str(todo_file))

        lines = todo_file.read_text().split("\n")
        todo_lines = [line for line in lines if line.startswith("- [ ]")]
        assert len(todo_lines) == 3

    def test_write_todos_error_handling_permission_denied(self, tmp_path):
        """Test error handling when file cannot be written."""
        # Create a directory to prevent file creation
        dir_path = tmp_path / "read_only_dir"
        dir_path.mkdir()
        os.chmod(dir_path, 0o444)  # Read-only directory

        try:
            result = write_todos(["Task"], filename=str(dir_path / "TODO.md"))
            assert "error" in result
        finally:
            os.chmod(dir_path, 0o755)  # Restore permissions for cleanup

    def test_write_todos_error_handling_invalid_path(self, tmp_path):
        """Test error handling for invalid file paths."""
        # Path with null byte is invalid
        with patch("builtins.open", side_effect=OSError("Invalid path")):
            result = write_todos(["Task"], filename="/invalid/path/TODO.md")
            assert "error" in result
            assert "Invalid path" in result["error"]

    def test_write_todos_custom_filename(self, tmp_path):
        """Test writing to a custom filename."""
        todo_file = tmp_path / "my_tasks.md"

        result = write_todos(["Custom task"], filename=str(todo_file))

        assert result["file"] == str(todo_file)
        assert todo_file.exists()

    def test_write_todos_nested_directory(self, tmp_path):
        """Test writing to a file in a nested directory."""
        nested_dir = tmp_path / "docs" / "tasks"
        nested_dir.mkdir(parents=True)
        todo_file = nested_dir / "TODO.md"

        result = write_todos(["Nested task"], filename=str(todo_file))

        assert result["todos_written"] == 1
        assert todo_file.exists()


class TestMarkTodoComplete:
    """Tests for the mark_todo_complete function."""

    def test_mark_todo_complete_basic(self, tmp_path):
        """Test marking a basic todo as complete."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("# TODOs\n\n- [ ] Task A\n- [ ] Task B\n")

        result = mark_todo_complete("Task A", filename=str(todo_file))

        assert result["todo_completed"] is True
        assert result["text"] == "Task A"

        content = todo_file.read_text()
        assert "- [x] Task A" in content
        assert "- [ ] Task B" in content

    def test_mark_todo_complete_middle_item(self, tmp_path):
        """Test marking a todo in the middle of the list."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] First\n- [ ] Second\n- [ ] Third\n")

        result = mark_todo_complete("Second", filename=str(todo_file))

        assert result["todo_completed"] is True
        content = todo_file.read_text()
        assert "- [ ] First" in content
        assert "- [x] Second" in content
        assert "- [ ] Third" in content

    def test_mark_todo_complete_last_item(self, tmp_path):
        """Test marking the last todo as complete."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] First\n- [ ] Last\n")

        result = mark_todo_complete("Last", filename=str(todo_file))

        assert result["todo_completed"] is True
        content = todo_file.read_text()
        assert "- [x] Last" in content

    def test_mark_todo_complete_partial_match(self, tmp_path):
        """Test that partial text matching works."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] Complete the implementation of feature X\n")

        result = mark_todo_complete("feature X", filename=str(todo_file))

        assert result["todo_completed"] is True
        content = todo_file.read_text()
        assert "- [x] Complete the implementation of feature X" in content

    def test_mark_todo_complete_first_occurrence_only(self, tmp_path):
        """Test that only the first matching todo is marked complete."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] Task with keyword\n- [ ] Another task with keyword\n")

        result = mark_todo_complete("keyword", filename=str(todo_file))

        assert result["todo_completed"] is True
        content = todo_file.read_text()
        assert "- [x] Task with keyword" in content
        assert "- [ ] Another task with keyword" in content

    def test_mark_todo_complete_not_found(self, tmp_path):
        """Test marking a todo that doesn't exist."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] Existing task\n")

        result = mark_todo_complete("Nonexistent task", filename=str(todo_file))

        assert result["todo_completed"] is False
        assert result["text"] == "Nonexistent task"

    def test_mark_todo_complete_already_complete(self, tmp_path):
        """Test that already completed todos are not modified again."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [x] Already done\n- [ ] Not done\n")

        result = mark_todo_complete("Already done", filename=str(todo_file))

        # Should return False since the todo checkbox is already marked
        # The function only matches "- [ ]" not "- [x]"
        assert result["todo_completed"] is False

    def test_mark_todo_complete_empty_todo_text(self, tmp_path):
        """Test error handling for empty todo text."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] Task\n")

        result = mark_todo_complete("", filename=str(todo_file))

        assert "error" in result
        assert result["error"] == "Missing todo_text"

    def test_mark_todo_complete_file_not_found(self, tmp_path):
        """Test error handling when file doesn't exist."""
        result = mark_todo_complete("Task", filename=str(tmp_path / "nonexistent.md"))

        assert "error" in result
        assert result["error"] == "File not found"

    def test_mark_todo_complete_default_filename(self, tmp_path, monkeypatch):
        """Test using default filename TODO.md."""
        monkeypatch.chdir(tmp_path)
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] Default file task\n")

        result = mark_todo_complete("Default file task")

        assert result["todo_completed"] is True

    def test_mark_todo_complete_preserves_formatting(self, tmp_path):
        """Test that file formatting is preserved."""
        original = "# My TODOs\n\nSome intro text.\n\n- [ ] Task 1\n- [ ] Task 2\n\nFooter text.\n"
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text(original)

        mark_todo_complete("Task 1", filename=str(todo_file))

        content = todo_file.read_text()
        assert "# My TODOs" in content
        assert "Some intro text." in content
        assert "Footer text." in content
        assert "- [x] Task 1" in content
        assert "- [ ] Task 2" in content

    def test_mark_todo_complete_special_characters(self, tmp_path):
        """Test marking todos with special characters."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] Fix bug #123\n- [ ] Review PR: user/repo#456\n")

        result = mark_todo_complete("bug #123", filename=str(todo_file))

        assert result["todo_completed"] is True
        content = todo_file.read_text()
        assert "- [x] Fix bug #123" in content

    def test_mark_todo_complete_case_sensitive(self, tmp_path):
        """Test that matching is case-sensitive."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] Important TASK\n- [ ] important task\n")

        result = mark_todo_complete("TASK", filename=str(todo_file))

        assert result["todo_completed"] is True
        content = todo_file.read_text()
        assert "- [x] Important TASK" in content
        assert "- [ ] important task" in content

    def test_mark_todo_complete_whitespace_handling(self, tmp_path):
        """Test handling of whitespace in todo text."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] Task with    spaces\n")

        result = mark_todo_complete("Task with", filename=str(todo_file))

        assert result["todo_completed"] is True

    def test_mark_todo_complete_read_error(self, tmp_path):
        """Test error handling during file read."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] Task\n")

        with patch("builtins.open", side_effect=IOError("Read error")):
            result = mark_todo_complete("Task", filename=str(todo_file))

            assert "error" in result
            assert "Read error" in result["error"]

    def test_mark_todo_complete_write_error(self, tmp_path):
        """Test error handling during file write after successful read."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] Task\n")

        original_open = open

        def mock_open(file, mode="r", *args, **kwargs):
            if mode == "w":
                raise IOError("Write error")
            return original_open(file, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open):
            result = mark_todo_complete("Task", filename=str(todo_file))

            assert "error" in result
            assert "Write error" in result["error"]

    def test_mark_todo_complete_empty_file(self, tmp_path):
        """Test marking todo in an empty file."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("")

        result = mark_todo_complete("Task", filename=str(todo_file))

        assert result["todo_completed"] is False

    def test_mark_todo_complete_no_checkboxes(self, tmp_path):
        """Test marking todo in a file with no checkboxes."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("# TODOs\n\nJust some text, no checkboxes.\n")

        result = mark_todo_complete("some text", filename=str(todo_file))

        assert result["todo_completed"] is False

    def test_mark_todo_complete_indented_checkboxes(self, tmp_path):
        """Test marking an indented checkbox."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] Parent\n  - [ ] Child task\n")

        result = mark_todo_complete("Child task", filename=str(todo_file))

        assert result["todo_completed"] is True
        content = todo_file.read_text()
        assert "- [x] Child task" in content


class TestIntegration:
    """Integration tests for todo actions working together."""

    def test_write_then_mark_complete(self, tmp_path):
        """Test writing todos and then marking one complete."""
        todo_file = tmp_path / "TODO.md"

        # Write todos
        write_result = write_todos(
            ["Task A", "Task B", "Task C"],
            filename=str(todo_file),
        )
        assert write_result["todos_written"] == 3

        # Mark one complete
        complete_result = mark_todo_complete("Task B", filename=str(todo_file))
        assert complete_result["todo_completed"] is True

        # Verify final state
        content = todo_file.read_text()
        assert "- [ ] Task A" in content
        assert "- [x] Task B" in content
        assert "- [ ] Task C" in content

    def test_append_and_complete_cycle(self, tmp_path):
        """Test append mode followed by marking complete."""
        todo_file = tmp_path / "TODO.md"

        # Initial write
        write_todos(["Initial task"], filename=str(todo_file))

        # Mark complete
        mark_todo_complete("Initial task", filename=str(todo_file))

        # Append new task
        write_todos(["New task"], filename=str(todo_file), mode="append")

        content = todo_file.read_text()
        assert "- [x] Initial task" in content
        assert "- [ ] New task" in content

    def test_multiple_complete_operations(self, tmp_path):
        """Test marking multiple todos complete in sequence."""
        todo_file = tmp_path / "TODO.md"
        write_todos(["Task 1", "Task 2", "Task 3"], filename=str(todo_file))

        mark_todo_complete("Task 1", filename=str(todo_file))
        mark_todo_complete("Task 3", filename=str(todo_file))

        content = todo_file.read_text()
        assert "- [x] Task 1" in content
        assert "- [ ] Task 2" in content
        assert "- [x] Task 3" in content


class TestEdgeCases:
    """Edge case tests for todo actions."""

    def test_write_todos_very_long_list(self, tmp_path):
        """Test writing a large number of todos."""
        todo_file = tmp_path / "TODO.md"
        todos = [f"Task {i}" for i in range(100)]

        result = write_todos(todos, filename=str(todo_file))

        assert result["todos_written"] == 100
        content = todo_file.read_text()
        assert "- [ ] Task 0" in content
        assert "- [ ] Task 99" in content

    def test_write_todos_very_long_text(self, tmp_path):
        """Test writing a todo with very long text."""
        todo_file = tmp_path / "TODO.md"
        long_text = "A" * 1000

        result = write_todos([long_text], filename=str(todo_file))

        assert result["todos_written"] == 1
        content = todo_file.read_text()
        assert long_text in content

    def test_mark_complete_exact_checkbox_pattern(self, tmp_path):
        """Test that only exact - [ ] pattern is matched."""
        todo_file = tmp_path / "TODO.md"
        # Various checkbox-like patterns
        todo_file.write_text(
            "[ ] No dash\n"
            "-[ ] No space\n"
            "- [] No space inside\n"
            "- [ ] Correct pattern\n"
            "- [X] Already complete uppercase\n"
        )

        result = mark_todo_complete("Correct", filename=str(todo_file))

        assert result["todo_completed"] is True
        content = todo_file.read_text()
        assert "- [x] Correct pattern" in content

    def test_mark_complete_preserves_line_endings(self, tmp_path):
        """Test that line endings are preserved."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] Task 1\n- [ ] Task 2\n")

        mark_todo_complete("Task 1", filename=str(todo_file))

        # Read as binary to check line endings
        content = todo_file.read_bytes()
        # Should have LF line endings preserved
        assert b"\n" in content

    def test_none_todo_text(self, tmp_path):
        """Test handling of None todo text."""
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("- [ ] Task\n")

        # mark_todo_complete expects a string, but let's see how it handles None
        # The function checks "if not todo_text" which catches None
        result = mark_todo_complete(None, filename=str(todo_file))

        assert "error" in result
        assert result["error"] == "Missing todo_text"
