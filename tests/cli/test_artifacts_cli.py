"""Tests for CLI artifact display functions showing title, task ref, and tags."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli.artifacts import (
    _display_artifact_detail,
    _display_artifact_list,
    _display_timeline_entry,
)
from gobby.storage.artifacts import Artifact


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
