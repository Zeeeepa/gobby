"""Tests for shared content installer with dev-mode symlink support."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from gobby.cli.installers.shared import (
    _install_resource_dir,
    _is_dev_mode,
    install_shared_content,
)

pytestmark = pytest.mark.unit


class TestDevModeDetection:
    """Tests for _is_dev_mode detection."""

    def test_dev_mode_in_gobby_repo(self, tmp_path: Path) -> None:
        """Dev-mode detection returns True in gobby source repo."""
        # Simulate gobby source repo layout
        (tmp_path / "src" / "gobby" / "install" / "shared").mkdir(parents=True)
        assert _is_dev_mode(tmp_path) is True

    def test_dev_mode_false_in_normal_project(self, tmp_path: Path) -> None:
        """Dev-mode detection returns False in normal projects."""
        (tmp_path / ".gobby").mkdir()
        assert _is_dev_mode(tmp_path) is False

    def test_dev_mode_false_with_partial_path(self, tmp_path: Path) -> None:
        """Dev-mode detection returns False when path is only partially matching."""
        (tmp_path / "src" / "gobby").mkdir(parents=True)
        # Missing install/shared
        assert _is_dev_mode(tmp_path) is False


class TestInstallResourceDir:
    """Tests for _install_resource_dir."""

    def test_symlink_created_in_dev_mode(self, tmp_path: Path) -> None:
        """Symlinks created in dev mode instead of copies."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "file.yaml").write_text("test")
        target = tmp_path / "target"

        _install_resource_dir(source, target, dev_mode=True)

        assert target.is_symlink()
        assert target.resolve() == source.resolve()
        # Content should be accessible through symlink
        assert (target / "file.yaml").read_text() == "test"

    def test_copy_in_normal_mode(self, tmp_path: Path) -> None:
        """Directories are copied in normal mode."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "file.yaml").write_text("test")
        target = tmp_path / "target"

        _install_resource_dir(source, target, dev_mode=False)

        assert not target.is_symlink()
        assert target.is_dir()
        assert (target / "file.yaml").read_text() == "test"

    def test_existing_symlink_safely_removed(self, tmp_path: Path) -> None:
        """Existing symlinks are safely removed (not followed) before reinstall."""
        source_old = tmp_path / "source_old"
        source_old.mkdir()
        (source_old / "old.yaml").write_text("old")

        source_new = tmp_path / "source_new"
        source_new.mkdir()
        (source_new / "new.yaml").write_text("new")

        target = tmp_path / "target"
        os.symlink(source_old.resolve(), target)

        # Reinstall with new source — should NOT delete source_old contents
        _install_resource_dir(source_new, target, dev_mode=True)

        assert target.is_symlink()
        assert target.resolve() == source_new.resolve()
        # Old source should still be intact (symlink was unlinked, not followed)
        assert (source_old / "old.yaml").read_text() == "old"

    def test_existing_dir_replaced_with_symlink(self, tmp_path: Path) -> None:
        """Existing regular directory is replaced when switching to dev mode."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "file.yaml").write_text("test")

        target = tmp_path / "target"
        target.mkdir()
        (target / "stale.yaml").write_text("stale")

        _install_resource_dir(source, target, dev_mode=True)

        assert target.is_symlink()
        assert (target / "file.yaml").read_text() == "test"


class TestInstallSharedContent:
    """Tests for install_shared_content — only plugins and docs are file-based."""

    def test_dev_mode_creates_symlinks_for_plugins(self, tmp_path: Path) -> None:
        """install_shared_content creates symlinks for plugins in dev mode."""
        # Set up a fake gobby source repo
        project = tmp_path / "gobby"
        shared = project / "src" / "gobby" / "install" / "shared"
        (shared / "plugins").mkdir(parents=True)
        (shared / "plugins" / "test_plugin.py").write_text("# plugin")
        (project / ".gobby").mkdir(parents=True)

        with patch(
            "gobby.cli.installers.shared.get_install_dir",
            return_value=project / "src" / "gobby" / "install",
        ):
            result = install_shared_content(project / ".claude", project)

        # Plugins should be a symlink
        plugins_target = project / ".gobby" / "plugins"
        assert plugins_target.is_symlink()
        assert "symlink" in result["plugins"][0]

        # Workflows and agents should NOT be installed (DB-managed)
        assert "workflows" not in result
        assert "agents" not in result

    def test_normal_mode_copies_plugins_and_docs(self, tmp_path: Path) -> None:
        """install_shared_content copies plugins and docs in normal projects."""
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
