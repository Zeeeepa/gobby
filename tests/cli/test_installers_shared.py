"""Tests for shared content installer."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from gobby.cli.installers.shared import (
    install_shared_content,
)

pytestmark = pytest.mark.unit


class TestInstallSharedContent:
    """Tests for install_shared_content — only plugins and docs are file-based."""

    def test_copies_plugins_and_docs(self, tmp_path: Path) -> None:
        """install_shared_content copies plugins and docs."""
        project = tmp_path / "myproject"
        project.mkdir()
        (project / ".gobby").mkdir()

        # Create a fake install dir with shared content
        install_dir = tmp_path / "install"
        shared = install_dir / "shared"
        (shared / "plugins").mkdir(parents=True)
        (shared / "plugins" / "test_plugin.py").write_text("# plugin")
        (shared / "docs").mkdir(parents=True)
        (shared / "docs" / "guide.md").write_text("# guide")

        with patch("gobby.cli.installers.shared.get_install_dir", return_value=install_dir):
            result = install_shared_content(project / ".claude", project)

        plugins_target = project / ".gobby" / "plugins"
        assert not plugins_target.is_symlink()
        assert plugins_target.is_dir()
        assert "test_plugin.py" in result["plugins"]

        docs_target = project / ".gobby" / "docs"
        assert docs_target.is_dir()
        assert "guide.md" in result["docs"]

        # Workflows and agents should NOT be in result (DB-managed)
        assert "workflows" not in result
        assert "agents" not in result

    def test_migrates_symlink_to_copy(self, tmp_path: Path) -> None:
        """install_shared_content migrates existing symlinks to copies."""
        project = tmp_path / "myproject"
        project.mkdir()
        (project / ".gobby").mkdir()

        # Create a fake install dir with shared content
        install_dir = tmp_path / "install"
        shared = install_dir / "shared"
        (shared / "plugins").mkdir(parents=True)
        (shared / "plugins" / "test_plugin.py").write_text("# plugin")

        # Create an existing symlink (simulating old dev-mode install)
        old_source = tmp_path / "old_plugins"
        old_source.mkdir()
        (old_source / "old_plugin.py").write_text("# old")
        plugins_target = project / ".gobby" / "plugins"
        os.symlink(old_source.resolve(), plugins_target)

        with patch("gobby.cli.installers.shared.get_install_dir", return_value=install_dir):
            result = install_shared_content(project / ".claude", project)

        # Should be a regular dir now, not a symlink
        assert not plugins_target.is_symlink()
        assert plugins_target.is_dir()
        assert "test_plugin.py" in result["plugins"]
        # Old source should still be intact
        assert (old_source / "old_plugin.py").read_text() == "# old"
