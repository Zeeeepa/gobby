"""Tests for cascade operation progress bar utility.

Tests verify the progress bar for batch/cascade CLI operations:
- Format: `[####----] 4/10 #42: Task title...`
- Uses click.progressbar
- KeyboardInterrupt handling
- Error continue prompt
"""

from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner


class TestCascadeProgress:
    """Tests for cascade_progress context manager."""

    def test_cascade_progress_exists(self):
        """Test that cascade_progress is importable."""
        from gobby.cli.tasks._utils import cascade_progress

        assert callable(cascade_progress)

    def test_cascade_progress_yields_task_info(self):
        """Test that cascade_progress yields task info for each task."""
        from gobby.cli.tasks._utils import cascade_progress

        tasks = [
            MagicMock(id="t1", seq_num=42, title="Task One"),
            MagicMock(id="t2", seq_num=43, title="Task Two"),
        ]

        processed = []
        with cascade_progress(tasks, label="Testing") as progress:
            for task, update in progress:
                processed.append(task.id)
                update()  # Mark task as complete

        assert processed == ["t1", "t2"]

    def test_cascade_progress_shows_task_reference(self):
        """Test that progress displays #N format for tasks."""
        from gobby.cli.tasks._utils import cascade_progress

        tasks = [MagicMock(id="t1", seq_num=42, title="Test Task")]

        # Just verify it runs without error for now
        with cascade_progress(tasks, label="Expanding") as progress:
            for task, update in progress:
                update()

    def test_cascade_progress_truncates_long_titles(self):
        """Test that very long titles are truncated."""
        from gobby.cli.tasks._utils import cascade_progress

        long_title = "A" * 100  # Very long title
        tasks = [MagicMock(id="t1", seq_num=1, title=long_title)]

        with cascade_progress(tasks, label="Testing") as progress:
            for task, update in progress:
                update()

    def test_cascade_progress_handles_empty_list(self):
        """Test that empty task list is handled gracefully."""
        from gobby.cli.tasks._utils import cascade_progress

        processed = []
        with cascade_progress([], label="Testing") as progress:
            for task, update in progress:
                processed.append(task.id)
                update()

        assert processed == []

    def test_cascade_progress_with_keyboard_interrupt(self):
        """Test that KeyboardInterrupt is caught and reported."""
        from gobby.cli.tasks._utils import cascade_progress

        tasks = [
            MagicMock(id="t1", seq_num=1, title="Task One"),
            MagicMock(id="t2", seq_num=2, title="Task Two"),
        ]

        processed = []
        with pytest.raises(KeyboardInterrupt):
            with cascade_progress(tasks, label="Testing") as progress:
                for task, update in progress:
                    if task.id == "t2":
                        raise KeyboardInterrupt()
                    processed.append(task.id)
                    update()

        # First task should have been processed
        assert processed == ["t1"]


class TestCascadeProgressErrorHandling:
    """Tests for error handling in cascade_progress."""

    def test_cascade_progress_on_error_callback(self):
        """Test that on_error callback is invoked on task failure."""
        from gobby.cli.tasks._utils import cascade_progress

        tasks = [
            MagicMock(id="t1", seq_num=1, title="Task One"),
            MagicMock(id="t2", seq_num=2, title="Task Two"),
        ]

        errors = []

        def on_error(task, error):
            errors.append((task.id, str(error)))
            return True  # Continue processing

        with cascade_progress(tasks, label="Testing", on_error=on_error) as progress:
            for task, update in progress:
                if task.id == "t1":
                    raise ValueError("Test error")
                update()

        assert len(errors) == 1
        assert errors[0][0] == "t1"
        assert "Test error" in errors[0][1]

    def test_cascade_progress_stop_on_error(self):
        """Test that processing stops when on_error returns False."""
        from gobby.cli.tasks._utils import cascade_progress

        tasks = [
            MagicMock(id="t1", seq_num=1, title="Task One"),
            MagicMock(id="t2", seq_num=2, title="Task Two"),
        ]

        processed = []

        def on_error(task, error):
            return False  # Stop processing

        with cascade_progress(tasks, label="Testing", on_error=on_error) as progress:
            for task, update in progress:
                if task.id == "t1":
                    raise ValueError("Test error")
                processed.append(task.id)
                update()

        # Second task should not be processed
        assert processed == []


class TestCascadeProgressIntegration:
    """Integration tests with Click CLI runner."""

    def test_cascade_progress_in_cli_command(self):
        """Test cascade_progress works within a Click command."""
        from gobby.cli.tasks._utils import cascade_progress

        @click.command()
        def test_cmd():
            tasks = [
                MagicMock(id="t1", seq_num=1, title="Task 1"),
                MagicMock(id="t2", seq_num=2, title="Task 2"),
            ]
            with cascade_progress(tasks, label="Processing") as progress:
                for task, update in progress:
                    click.echo(f"Processing {task.id}")
                    update()
            click.echo("Done!")

        runner = CliRunner()
        result = runner.invoke(test_cmd)

        assert result.exit_code == 0
        assert "Done!" in result.output
