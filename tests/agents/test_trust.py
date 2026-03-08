"""Tests for workspace trust pre-approval."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from gobby.agents.trust import (
    _encode_claude_project_path,
    pre_approve_directory,
)


class TestEncodePath:
    def test_basic_path(self) -> None:
        assert (
            _encode_claude_project_path("/Users/josh/Projects/gobby")
            == "-Users-josh-Projects-gobby"
        )

    def test_clone_path(self) -> None:
        assert (
            _encode_claude_project_path("/private/tmp/gobby-clones/9990-2048-game")
            == "-private-tmp-gobby-clones-9990-2048-game"
        )

    def test_worktree_path(self) -> None:
        assert (
            _encode_claude_project_path("/private/tmp/gobby-worktrees/gobby-task-9395")
            == "-private-tmp-gobby-worktrees-gobby-task-9395"
        )


class TestPreApproveClaude:
    def test_creates_project_directory(self, tmp_path: Path) -> None:
        clone_dir = "/private/tmp/gobby-clones/test-task"
        claude_projects = tmp_path / ".claude" / "projects"

        with patch("gobby.agents.trust.Path.home", return_value=tmp_path):
            pre_approve_directory("claude", clone_dir)

        expected = claude_projects / "-private-tmp-gobby-clones-test-task"
        assert expected.is_dir()

    def test_idempotent(self, tmp_path: Path) -> None:
        clone_dir = "/private/tmp/gobby-clones/test-task"

        with patch("gobby.agents.trust.Path.home", return_value=tmp_path):
            pre_approve_directory("claude", clone_dir)
            pre_approve_directory("claude", clone_dir)

        expected = tmp_path / ".claude" / "projects" / "-private-tmp-gobby-clones-test-task"
        assert expected.is_dir()

    def test_cursor_uses_claude_trust(self, tmp_path: Path) -> None:
        clone_dir = "/private/tmp/gobby-clones/test-task"

        with patch("gobby.agents.trust.Path.home", return_value=tmp_path):
            pre_approve_directory("cursor", clone_dir)

        expected = tmp_path / ".claude" / "projects" / "-private-tmp-gobby-clones-test-task"
        assert expected.is_dir()

    def test_windsurf_uses_claude_trust(self, tmp_path: Path) -> None:
        clone_dir = "/private/tmp/gobby-clones/windsurf-test"

        with patch("gobby.agents.trust.Path.home", return_value=tmp_path):
            pre_approve_directory("windsurf", clone_dir)

        expected = tmp_path / ".claude" / "projects" / "-private-tmp-gobby-clones-windsurf-test"
        assert expected.is_dir()

    def test_copilot_uses_claude_trust(self, tmp_path: Path) -> None:
        clone_dir = "/private/tmp/gobby-clones/copilot-test"

        with patch("gobby.agents.trust.Path.home", return_value=tmp_path):
            pre_approve_directory("copilot", clone_dir)

        expected = tmp_path / ".claude" / "projects" / "-private-tmp-gobby-clones-copilot-test"
        assert expected.is_dir()

    def test_resolves_symlinks(self, tmp_path: Path) -> None:
        """On macOS /tmp -> /private/tmp; both paths should get trust entries."""
        clone_dir = "/tmp/gobby-clones/symlink-test"
        resolved_dir = "/private/tmp/gobby-clones/symlink-test"

        with (
            patch("gobby.agents.trust.Path.home", return_value=tmp_path),
            patch("gobby.agents.trust.os.path.realpath", return_value=resolved_dir),
        ):
            pre_approve_directory("claude", clone_dir)

        projects = tmp_path / ".claude" / "projects"
        assert (projects / "-tmp-gobby-clones-symlink-test").is_dir()
        assert (projects / "-private-tmp-gobby-clones-symlink-test").is_dir()


class TestPreApproveGemini:
    def test_creates_projects_json(self, tmp_path: Path) -> None:
        clone_dir = "/private/tmp/gobby-clones/test-task"

        with patch("gobby.agents.trust.Path.home", return_value=tmp_path):
            pre_approve_directory("gemini", clone_dir)

        projects_file = tmp_path / ".gemini" / "projects.json"
        assert projects_file.exists()
        data = json.loads(projects_file.read_text())
        assert clone_dir in data["projects"]
        assert data["projects"][clone_dir] == "test-task"

    def test_preserves_existing_entries(self, tmp_path: Path) -> None:
        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir()
        projects_file = gemini_dir / "projects.json"
        projects_file.write_text(json.dumps({"projects": {"/existing/path": "existing"}}))

        clone_dir = "/private/tmp/gobby-clones/test-task"

        with patch("gobby.agents.trust.Path.home", return_value=tmp_path):
            pre_approve_directory("gemini", clone_dir)

        data = json.loads(projects_file.read_text())
        assert "/existing/path" in data["projects"]
        assert clone_dir in data["projects"]

    def test_idempotent(self, tmp_path: Path) -> None:
        clone_dir = "/private/tmp/gobby-clones/test-task"

        with patch("gobby.agents.trust.Path.home", return_value=tmp_path):
            pre_approve_directory("gemini", clone_dir)
            pre_approve_directory("gemini", clone_dir)

        projects_file = tmp_path / ".gemini" / "projects.json"
        data = json.loads(projects_file.read_text())
        assert data["projects"][clone_dir] == "test-task"


class TestCodexNoop:
    def test_codex_is_noop(self, tmp_path: Path) -> None:
        """Codex uses --full-auto sandbox; no trust pre-approval needed."""
        clone_dir = "/private/tmp/gobby-clones/test-task"

        with patch("gobby.agents.trust.Path.home", return_value=tmp_path):
            pre_approve_directory("codex", clone_dir)

        # Should not create any files
        assert not (tmp_path / ".claude").exists()
        assert not (tmp_path / ".gemini").exists()
