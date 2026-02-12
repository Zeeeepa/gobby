"""Tests for CLI artifact display and export functions."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli.artifacts import (
    _display_artifact_detail,
    _display_artifact_list,
    _display_timeline_entry,
    _get_extension,
    artifacts,
)
from gobby.storage.artifacts import Artifact

pytestmark = pytest.mark.unit


def _make_artifact(
    id: str = "abc123",
    session_id: str = "sess-1",
    artifact_type: str = "code",
    content: str = "x = 1",
    created_at: str = "2025-01-01T00:00:00",
    title: str | None = None,
    task_id: str | None = None,
    source_file: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Artifact:
    return Artifact(
        id=id,
        session_id=session_id,
        artifact_type=artifact_type,
        content=content,
        created_at=created_at,
        title=title,
        task_id=task_id,
        source_file=source_file,
        metadata=metadata,
    )


class TestDisplayArtifactList:
    def test_shows_title_column(self, capsys: pytest.CaptureFixture[str]) -> None:
        artifacts = [_make_artifact(title="def hello()")]
        _display_artifact_list(artifacts)
        output = capsys.readouterr().out
        assert "Title" in output
        assert "def hello()" in output

    def test_truncates_long_title(self, capsys: pytest.CaptureFixture[str]) -> None:
        artifacts = [_make_artifact(title="A" * 50)]
        _display_artifact_list(artifacts)
        output = capsys.readouterr().out
        assert "..." in output

    def test_shows_task_ref(self, capsys: pytest.CaptureFixture[str]) -> None:
        artifacts = [_make_artifact(task_id="12345678-abcd-efgh")]
        _display_artifact_list(artifacts)
        output = capsys.readouterr().out
        assert "Task" in output
        assert "12345678.." in output

    def test_shows_dash_for_missing_title_and_task(self, capsys: pytest.CaptureFixture[str]) -> None:
        artifacts = [_make_artifact()]
        _display_artifact_list(artifacts)
        output = capsys.readouterr().out
        lines = output.strip().split("\n")
        # Data row should have dashes for missing title and task
        assert lines[2].count("-") > 0


class TestDisplayArtifactDetail:
    @patch("gobby.cli.artifacts.get_artifact_manager")
    def test_shows_title(self, mock_mgr: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        mock_mgr.return_value.get_tags.return_value = []
        artifact = _make_artifact(title="my function")
        _display_artifact_detail(artifact, verbose=False)
        output = capsys.readouterr().out
        assert "Title: my function" in output

    @patch("gobby.cli.artifacts.get_artifact_manager")
    def test_shows_task_id(self, mock_mgr: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        mock_mgr.return_value.get_tags.return_value = []
        artifact = _make_artifact(task_id="task-uuid-123")
        _display_artifact_detail(artifact, verbose=False)
        output = capsys.readouterr().out
        assert "Task: task-uuid-123" in output

    @patch("gobby.cli.artifacts.get_artifact_manager")
    def test_shows_tags(self, mock_mgr: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        mock_mgr.return_value.get_tags.return_value = ["auth", "bugfix"]
        artifact = _make_artifact()
        _display_artifact_detail(artifact, verbose=False)
        output = capsys.readouterr().out
        assert "Tags: auth, bugfix" in output

    @patch("gobby.cli.artifacts.get_artifact_manager")
    def test_no_tags_line_when_empty(self, mock_mgr: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        mock_mgr.return_value.get_tags.return_value = []
        artifact = _make_artifact()
        _display_artifact_detail(artifact, verbose=False)
        output = capsys.readouterr().out
        assert "Tags:" not in output

    @patch("gobby.cli.artifacts.get_artifact_manager")
    def test_no_title_line_when_none(self, mock_mgr: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        mock_mgr.return_value.get_tags.return_value = []
        artifact = _make_artifact(title=None)
        _display_artifact_detail(artifact, verbose=False)
        output = capsys.readouterr().out
        assert "Title:" not in output

    @patch("gobby.cli.artifacts.get_artifact_manager")
    def test_no_task_line_when_none(self, mock_mgr: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        mock_mgr.return_value.get_tags.return_value = []
        artifact = _make_artifact(task_id=None)
        _display_artifact_detail(artifact, verbose=False)
        output = capsys.readouterr().out
        assert "Task:" not in output


class TestDisplayTimelineEntry:
    def test_shows_title_in_header(self, capsys: pytest.CaptureFixture[str]) -> None:
        artifact = _make_artifact(title="def hello()")
        _display_timeline_entry(artifact)
        output = capsys.readouterr().out
        assert "CODE: def hello()" in output

    def test_falls_back_to_id(self, capsys: pytest.CaptureFixture[str]) -> None:
        artifact = _make_artifact(id="abc123", title=None)
        _display_timeline_entry(artifact)
        output = capsys.readouterr().out
        assert "CODE: abc123" in output


# =============================================================================
# Export command
# =============================================================================


class TestGetExtension:
    def test_python_from_metadata(self) -> None:
        a = _make_artifact(artifact_type="code", metadata={"language": "python"})
        assert _get_extension(a) == ".py"

    def test_diff_type(self) -> None:
        a = _make_artifact(artifact_type="diff")
        assert _get_extension(a) == ".diff"

    def test_error_type(self) -> None:
        a = _make_artifact(artifact_type="error")
        assert _get_extension(a) == ".log"

    def test_plan_type(self) -> None:
        a = _make_artifact(artifact_type="plan")
        assert _get_extension(a) == ".md"

    def test_unknown_type_defaults_to_txt(self) -> None:
        a = _make_artifact(artifact_type="unknown_thing")
        assert _get_extension(a) == ".txt"

    def test_language_takes_precedence(self) -> None:
        a = _make_artifact(artifact_type="code", metadata={"language": "rust"})
        assert _get_extension(a) == ".rs"


class TestExportCommand:
    @patch("gobby.cli.artifacts.get_artifact_manager")
    def test_export_to_stdout(self, mock_mgr: MagicMock) -> None:
        mock_mgr.return_value.get_artifact.return_value = _make_artifact(
            content="def hello(): pass"
        )
        runner = CliRunner()
        result = runner.invoke(artifacts, ["export", "abc123"])
        assert result.exit_code == 0
        assert "def hello(): pass" in result.output

    @patch("gobby.cli.artifacts.get_artifact_manager")
    def test_export_to_file(self, mock_mgr: MagicMock, tmp_path: Path) -> None:
        mock_mgr.return_value.get_artifact.return_value = _make_artifact(
            content="x = 1\ny = 2",
            artifact_type="code",
            metadata={"language": "python"},
        )
        out_file = tmp_path / "output.py"
        runner = CliRunner()
        result = runner.invoke(artifacts, ["export", "abc123", "-o", str(out_file)])
        assert result.exit_code == 0
        assert out_file.read_text() == "x = 1\ny = 2"

    @patch("gobby.cli.artifacts.get_artifact_manager")
    def test_export_to_file_derives_extension(self, mock_mgr: MagicMock, tmp_path: Path) -> None:
        mock_mgr.return_value.get_artifact.return_value = _make_artifact(
            content="--- a/f.py\n+++ b/f.py",
            artifact_type="diff",
        )
        out_base = tmp_path / "changes"
        runner = CliRunner()
        result = runner.invoke(artifacts, ["export", "abc123", "-o", str(out_base)])
        assert result.exit_code == 0
        expected_file = tmp_path / "changes.diff"
        assert expected_file.exists()
        assert expected_file.read_text() == "--- a/f.py\n+++ b/f.py"

    @patch("gobby.cli.artifacts.get_artifact_manager")
    def test_export_not_found(self, mock_mgr: MagicMock) -> None:
        mock_mgr.return_value.get_artifact.return_value = None
        runner = CliRunner()
        result = runner.invoke(artifacts, ["export", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output
