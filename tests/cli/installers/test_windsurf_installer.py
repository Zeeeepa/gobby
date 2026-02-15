"""Tests for the Windsurf installer module.

Exercises the real install_windsurf() and uninstall_windsurf() functions
with real filesystem operations. Only get_install_dir() and _is_dev_mode()
are mocked.

Targets 90%+ statement coverage of src/gobby/cli/installers/windsurf.py.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gobby.cli.installers.windsurf import install_windsurf, uninstall_windsurf

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_install_dir(base: Path) -> Path:
    """Create a realistic install directory with windsurf hook sources."""
    install_dir = base / "install"
    windsurf_dir = install_dir / "windsurf"
    hooks_dir = windsurf_dir / "hooks"
    hooks_dir.mkdir(parents=True)

    (hooks_dir / "hook_dispatcher.py").write_text("#!/usr/bin/env python3\n# dispatcher\n")

    template = {
        "hooks": {
            "pre_save": [
                {
                    "command": "python $PROJECT_PATH/.windsurf/hooks/hook_dispatcher.py pre_save",
                    "events": ["pre_save"],
                }
            ],
            "post_save": [
                {
                    "command": "python $PROJECT_PATH/.windsurf/hooks/hook_dispatcher.py post_save",
                    "events": ["post_save"],
                }
            ],
        }
    }
    (windsurf_dir / "hooks-template.json").write_text(json.dumps(template))

    return install_dir


# ---------------------------------------------------------------------------
# install_windsurf
# ---------------------------------------------------------------------------


class TestInstallWindsurf:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        p = tmp_path / "project"
        p.mkdir()
        return p

    @pytest.fixture
    def install_dir(self, tmp_path: Path) -> Path:
        return _create_install_dir(tmp_path)

    def test_fresh_install_success(self, project: Path, install_dir: Path) -> None:
        """Full install on a clean project directory."""
        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
            patch(
                "gobby.cli.installers.windsurf.install_shared_content",
                return_value={
                    "workflows": ["lifecycle.yaml"],
                    "agents": ["agent.yaml"],
                    "plugins": ["plugin.py"],
                    "prompts": ["prompt.md"],
                    "docs": ["doc.md"],
                },
            ),
        ):
            result = install_windsurf(project)

        assert result["success"] is True
        assert result["error"] is None
        assert "pre_save" in result["hooks_installed"]
        assert "post_save" in result["hooks_installed"]
        assert result["workflows_installed"] == ["lifecycle.yaml"]
        assert result["agents_installed"] == ["agent.yaml"]
        assert result["plugins_installed"] == ["plugin.py"]
        assert result["prompts_installed"] == ["prompt.md"]
        assert result["docs_installed"] == ["doc.md"]

        # Verify directory structure
        assert (project / ".windsurf").is_dir()
        assert (project / ".windsurf" / "hooks").is_dir()
        assert (project / ".windsurf" / "hooks" / "hook_dispatcher.py").exists()

        # Verify hooks.json content
        hooks_file = project / ".windsurf" / "hooks.json"
        assert hooks_file.exists()
        with open(hooks_file) as f:
            data = json.load(f)
        # Windsurf does NOT have version key (unlike cursor)
        assert "version" not in data
        assert "hooks" in data
        assert "pre_save" in data["hooks"]
        assert "post_save" in data["hooks"]

        # Verify $PROJECT_PATH was replaced
        cmd = data["hooks"]["pre_save"][0]["command"]
        assert "$PROJECT_PATH" not in cmd
        assert str(project.resolve()) in cmd

    def test_missing_hook_dispatcher(self, project: Path, tmp_path: Path) -> None:
        """Fails when hook_dispatcher.py source is missing."""
        install_dir = tmp_path / "install"
        windsurf_dir = install_dir / "windsurf"
        (windsurf_dir / "hooks").mkdir(parents=True)
        (windsurf_dir / "hooks-template.json").write_text(json.dumps({"hooks": {}}))

        with patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir):
            result = install_windsurf(project)

        assert result["success"] is False
        assert "Missing source files" in result["error"]
        assert "hook_dispatcher.py" in result["error"]

    def test_missing_hooks_template(self, project: Path, tmp_path: Path) -> None:
        """Fails when hooks-template.json is missing."""
        install_dir = tmp_path / "install"
        windsurf_dir = install_dir / "windsurf"
        hooks_dir = windsurf_dir / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "hook_dispatcher.py").write_text("# dispatcher")

        with patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir):
            result = install_windsurf(project)

        assert result["success"] is False
        assert "Missing source files" in result["error"]
        assert "hooks-template.json" in result["error"]

    def test_missing_both_source_files(self, project: Path, tmp_path: Path) -> None:
        """Fails when both source files are missing."""
        install_dir = tmp_path / "install"
        (install_dir / "windsurf" / "hooks").mkdir(parents=True)

        with patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir):
            result = install_windsurf(project)

        assert result["success"] is False
        assert "Missing source files" in result["error"]

    def test_install_file_oserror(self, project: Path, install_dir: Path) -> None:
        """Fails when _install_file raises OSError."""
        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
            patch(
                "gobby.cli.installers.windsurf._install_file",
                side_effect=OSError("Permission denied"),
            ),
        ):
            result = install_windsurf(project)

        assert result["success"] is False
        assert "Failed to install hook files" in result["error"]

    def test_shared_content_failure_is_non_fatal(self, project: Path, install_dir: Path) -> None:
        """install_shared_content failure does not block hooks installation."""
        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
            patch(
                "gobby.cli.installers.windsurf.install_shared_content",
                side_effect=RuntimeError("Shared content kaboom"),
            ),
        ):
            result = install_windsurf(project)

        assert result["success"] is True
        assert result["error"] is None
        assert (project / ".windsurf" / "hooks.json").exists()

    def test_shared_content_missing_keys(self, project: Path, install_dir: Path) -> None:
        """Shared content result missing optional keys handled via .get()."""
        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
            patch(
                "gobby.cli.installers.windsurf.install_shared_content",
                return_value={"workflows": ["w.yaml"]},
            ),
        ):
            result = install_windsurf(project)

        assert result["success"] is True
        assert result["workflows_installed"] == ["w.yaml"]

    def test_existing_hooks_json_backup_and_merge(self, project: Path, install_dir: Path) -> None:
        """Existing hooks.json is backed up and merged."""
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)
        existing = {
            "hooks": {
                "custom_hook": [{"command": "my_custom_command"}],
            }
        }
        (windsurf_path / "hooks.json").write_text(json.dumps(existing))

        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
            patch(
                "gobby.cli.installers.windsurf.install_shared_content",
                return_value={
                    "workflows": [],
                    "agents": [],
                    "plugins": [],
                    "prompts": [],
                    "docs": [],
                },
            ),
        ):
            result = install_windsurf(project)

        assert result["success"] is True

        # Verify backup
        backups = list(windsurf_path.glob("hooks.json.*.backup"))
        assert len(backups) == 1
        with open(backups[0]) as f:
            assert json.load(f) == existing

        # Verify merged
        with open(windsurf_path / "hooks.json") as f:
            merged = json.load(f)
        assert "custom_hook" in merged["hooks"]
        assert "pre_save" in merged["hooks"]
        assert "post_save" in merged["hooks"]

    def test_corrupt_hooks_json_starts_fresh(self, project: Path, install_dir: Path) -> None:
        """Corrupt hooks.json causes a fresh start."""
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)
        (windsurf_path / "hooks.json").write_text("{ invalid json !!!")

        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
            patch(
                "gobby.cli.installers.windsurf.install_shared_content",
                return_value={
                    "workflows": [],
                    "agents": [],
                    "plugins": [],
                    "prompts": [],
                    "docs": [],
                },
            ),
        ):
            result = install_windsurf(project)

        assert result["success"] is True
        with open(windsurf_path / "hooks.json") as f:
            data = json.load(f)
        assert "hooks" in data
        assert "pre_save" in data["hooks"]

    def test_hooks_json_read_oserror(self, project: Path, install_dir: Path) -> None:
        """OSError reading existing hooks.json returns error."""
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)
        hooks_file = windsurf_path / "hooks.json"
        hooks_file.write_text(json.dumps({"hooks": {}}))
        hooks_file.chmod(0o000)

        try:
            with (
                patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
                patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
                patch(
                    "gobby.cli.installers.windsurf.install_shared_content",
                    return_value={
                        "workflows": [],
                        "agents": [],
                        "plugins": [],
                        "prompts": [],
                        "docs": [],
                    },
                ),
            ):
                result = install_windsurf(project)

            assert result["success"] is False
            assert "Failed" in result["error"]
        finally:
            hooks_file.chmod(0o644)

    def test_template_read_oserror(self, project: Path, tmp_path: Path) -> None:
        """OSError reading template returns error."""
        install_dir = tmp_path / "install2"
        windsurf_dir = install_dir / "windsurf"
        hooks_dir = windsurf_dir / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "hook_dispatcher.py").write_text("# dispatcher")
        template = windsurf_dir / "hooks-template.json"
        template.write_text(json.dumps({"hooks": {}}))
        template.chmod(0o000)

        try:
            with (
                patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
                patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
                patch(
                    "gobby.cli.installers.windsurf.install_shared_content",
                    return_value={
                        "workflows": [],
                        "agents": [],
                        "plugins": [],
                        "prompts": [],
                        "docs": [],
                    },
                ),
            ):
                result = install_windsurf(project)

            assert result["success"] is False
            assert "Failed to read hooks template" in result["error"]
        finally:
            template.chmod(0o644)

    def test_template_parse_error(self, project: Path, tmp_path: Path) -> None:
        """Invalid JSON in template returns error."""
        install_dir = tmp_path / "install3"
        windsurf_dir = install_dir / "windsurf"
        hooks_dir = windsurf_dir / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "hook_dispatcher.py").write_text("# dispatcher")
        (windsurf_dir / "hooks-template.json").write_text("{ not json !!!")

        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
            patch(
                "gobby.cli.installers.windsurf.install_shared_content",
                return_value={
                    "workflows": [],
                    "agents": [],
                    "plugins": [],
                    "prompts": [],
                    "docs": [],
                },
            ),
        ):
            result = install_windsurf(project)

        assert result["success"] is False
        assert "Failed to parse hooks template" in result["error"]

    def test_backup_failure_returns_error(self, project: Path, install_dir: Path) -> None:
        """Backup failure returns error."""
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)
        (windsurf_path / "hooks.json").write_text(json.dumps({"hooks": {}}))

        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
            patch(
                "gobby.cli.installers.windsurf.install_shared_content",
                return_value={
                    "workflows": [],
                    "agents": [],
                    "plugins": [],
                    "prompts": [],
                    "docs": [],
                },
            ),
            patch("gobby.cli.installers.windsurf.copy2", side_effect=OSError("Permission denied")),
        ):
            result = install_windsurf(project)

        assert result["success"] is False
        assert "Failed to create backup" in result["error"]

    def test_atomic_write_failure_restores_backup(self, project: Path, install_dir: Path) -> None:
        """Atomic write failure restores from backup."""
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)
        original = {"hooks": {"original": [{"command": "keep_me"}]}}
        hooks_file = windsurf_path / "hooks.json"
        hooks_file.write_text(json.dumps(original))

        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
            patch(
                "gobby.cli.installers.windsurf.install_shared_content",
                return_value={
                    "workflows": [],
                    "agents": [],
                    "plugins": [],
                    "prompts": [],
                    "docs": [],
                },
            ),
            patch(
                "gobby.cli.installers.windsurf.tempfile.mkstemp",
                side_effect=OSError("Disk full"),
            ),
        ):
            result = install_windsurf(project)

        assert result["success"] is False
        assert "Failed to write hooks.json" in result["error"]

        # Original restored from backup
        with open(hooks_file) as f:
            restored = json.load(f)
        assert "original" in restored["hooks"]

    def test_atomic_write_failure_no_backup(self, project: Path, install_dir: Path) -> None:
        """Atomic write failure with no backup (fresh install) just returns error."""
        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
            patch(
                "gobby.cli.installers.windsurf.install_shared_content",
                return_value={
                    "workflows": [],
                    "agents": [],
                    "plugins": [],
                    "prompts": [],
                    "docs": [],
                },
            ),
            patch(
                "gobby.cli.installers.windsurf.tempfile.mkstemp",
                side_effect=OSError("Disk full"),
            ),
        ):
            result = install_windsurf(project)

        assert result["success"] is False
        assert "Failed to write hooks.json" in result["error"]

    def test_ensures_hooks_key(self, project: Path, install_dir: Path) -> None:
        """Existing hooks.json missing hooks key gets it added."""
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)
        (windsurf_path / "hooks.json").write_text(json.dumps({"other": "value"}))

        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
            patch(
                "gobby.cli.installers.windsurf.install_shared_content",
                return_value={
                    "workflows": [],
                    "agents": [],
                    "plugins": [],
                    "prompts": [],
                    "docs": [],
                },
            ),
        ):
            result = install_windsurf(project)

        assert result["success"] is True
        with open(windsurf_path / "hooks.json") as f:
            data = json.load(f)
        assert "hooks" in data

    def test_dev_mode_uses_symlinks(self, project: Path, install_dir: Path) -> None:
        """In dev mode, _install_file is called with dev_mode=True."""
        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=True),
            patch("gobby.cli.installers.windsurf._install_file") as mock_install_file,
            patch(
                "gobby.cli.installers.windsurf.install_shared_content",
                return_value={
                    "workflows": [],
                    "agents": [],
                    "plugins": [],
                    "prompts": [],
                    "docs": [],
                },
            ),
        ):
            result = install_windsurf(project)

        assert result["success"] is True
        call_kwargs = mock_install_file.call_args
        assert call_kwargs[1]["dev_mode"] is True

    def test_hooks_json_open_oserror_after_backup(self, project: Path, install_dir: Path) -> None:
        """OSError on open() reading hooks.json (after backup succeeds) returns error.

        We need copy2 (backup) to succeed, but the subsequent open() for reading
        to fail with OSError. We achieve this by making the file unreadable AFTER
        the backup copy is made, using a patched copy2.
        """
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)
        hooks_file = windsurf_path / "hooks.json"
        hooks_file.write_text(json.dumps({"hooks": {}}))

        from shutil import copy2 as real_copy2

        def copy2_then_lock(src, dst, *args, **kwargs):
            """Do the real backup copy, then make the source unreadable."""
            result = real_copy2(src, dst, *args, **kwargs)
            hooks_file.chmod(0o000)
            return result

        try:
            with (
                patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
                patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
                patch(
                    "gobby.cli.installers.windsurf.install_shared_content",
                    return_value={
                        "workflows": [],
                        "agents": [],
                        "plugins": [],
                        "prompts": [],
                        "docs": [],
                    },
                ),
                patch("gobby.cli.installers.windsurf.copy2", side_effect=copy2_then_lock),
            ):
                result = install_windsurf(project)

            assert result["success"] is False
            assert "Failed to read hooks.json" in result["error"]
        finally:
            hooks_file.chmod(0o644)

    def test_atomic_write_failure_backup_restore_also_fails(
        self, project: Path, install_dir: Path
    ) -> None:
        """When atomic write fails AND backup restore also fails."""
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)
        original_hooks = {"hooks": {"custom": [{"command": "echo hi"}]}}
        hooks_file = windsurf_path / "hooks.json"
        hooks_file.write_text(json.dumps(original_hooks))

        copy2_call_count = 0
        from shutil import copy2 as real_copy2

        def patched_copy2(src, dst, *args, **kwargs):
            nonlocal copy2_call_count
            copy2_call_count += 1
            if copy2_call_count == 1:
                return real_copy2(src, dst, *args, **kwargs)
            else:
                raise OSError("Restore failed")

        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
            patch(
                "gobby.cli.installers.windsurf.install_shared_content",
                return_value={
                    "workflows": [],
                    "agents": [],
                    "plugins": [],
                    "prompts": [],
                    "docs": [],
                },
            ),
            patch(
                "gobby.cli.installers.windsurf.tempfile.mkstemp",
                side_effect=OSError("Disk full"),
            ),
            patch("gobby.cli.installers.windsurf.copy2", side_effect=patched_copy2),
        ):
            result = install_windsurf(project)

        assert result["success"] is False
        assert "Failed to write hooks.json" in result["error"]

    def test_atomic_write_inner_exception_cleans_temp(
        self, project: Path, install_dir: Path
    ) -> None:
        """Inner exception during atomic write cleans up temp file."""
        import tempfile as real_tempfile

        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)

        with (
            patch("gobby.cli.installers.windsurf.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.windsurf._is_dev_mode", return_value=False),
            patch(
                "gobby.cli.installers.windsurf.install_shared_content",
                return_value={
                    "workflows": [],
                    "agents": [],
                    "plugins": [],
                    "prompts": [],
                    "docs": [],
                },
            ),
        ):
            fd, temp_path = real_tempfile.mkstemp(
                dir=str(windsurf_path), suffix=".tmp", prefix="hooks_"
            )
            os.close(fd)

            with (
                patch(
                    "gobby.cli.installers.windsurf.tempfile.mkstemp",
                    return_value=(999, temp_path),
                ),
                patch("gobby.cli.installers.windsurf.os.fdopen", side_effect=OSError("Bad fd")),
            ):
                result = install_windsurf(project)

        assert result["success"] is False
        assert not os.path.exists(temp_path)


# ---------------------------------------------------------------------------
# uninstall_windsurf
# ---------------------------------------------------------------------------


class TestUninstallWindsurf:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        p = tmp_path / "project"
        p.mkdir()
        return p

    def test_uninstall_removes_dispatcher_and_hooks(self, project: Path) -> None:
        """Full uninstall removes dispatcher and Gobby hooks."""
        windsurf_path = project / ".windsurf"
        hooks_dir = windsurf_path / "hooks"
        hooks_dir.mkdir(parents=True)

        dispatcher = hooks_dir / "hook_dispatcher.py"
        dispatcher.write_text("# dispatcher")

        hooks_config = {
            "hooks": {
                "pre_save": [
                    {"command": "python /path/.windsurf/hooks/hook_dispatcher.py pre_save"}
                ],
                "post_save": [
                    {"command": "python /path/.windsurf/hooks/hook_dispatcher.py post_save"}
                ],
                "custom_hook": [{"command": "my_custom_script.sh"}],
            }
        }
        (windsurf_path / "hooks.json").write_text(json.dumps(hooks_config))

        result = uninstall_windsurf(project)

        assert result["success"] is True
        assert result["error"] is None
        assert not dispatcher.exists()
        assert str(dispatcher) in result["files_removed"]
        assert "pre_save" in result["hooks_removed"]
        assert "post_save" in result["hooks_removed"]
        assert "custom_hook" not in result["hooks_removed"]

        with open(windsurf_path / "hooks.json") as f:
            data = json.load(f)
        assert "pre_save" not in data["hooks"]
        assert "custom_hook" in data["hooks"]

    def test_uninstall_no_windsurf_dir(self, project: Path) -> None:
        """Uninstall succeeds when .windsurf doesn't exist."""
        result = uninstall_windsurf(project)
        assert result["success"] is True
        assert result["files_removed"] == []
        assert result["hooks_removed"] == []

    def test_uninstall_no_hooks_json(self, project: Path) -> None:
        """Uninstall succeeds when hooks.json doesn't exist."""
        hooks_dir = project / ".windsurf" / "hooks"
        hooks_dir.mkdir(parents=True)

        result = uninstall_windsurf(project)
        assert result["success"] is True
        assert result["hooks_removed"] == []

    def test_uninstall_dispatcher_does_not_exist(self, project: Path) -> None:
        """No error when dispatcher doesn't exist."""
        hooks_dir = project / ".windsurf" / "hooks"
        hooks_dir.mkdir(parents=True)

        result = uninstall_windsurf(project)
        assert result["success"] is True
        assert result["files_removed"] == []

    def test_uninstall_corrupt_hooks_json(self, project: Path) -> None:
        """Corrupt hooks.json handled gracefully."""
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)
        (windsurf_path / "hooks.json").write_text("{ broken json !!!")

        result = uninstall_windsurf(project)
        assert result["success"] is True
        assert result["hooks_removed"] == []

    def test_uninstall_hooks_json_oserror(self, project: Path) -> None:
        """OSError reading hooks.json is handled gracefully."""
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)
        hooks_file = windsurf_path / "hooks.json"
        hooks_file.write_text(json.dumps({"hooks": {}}))
        hooks_file.chmod(0o000)

        try:
            result = uninstall_windsurf(project)
            assert result["success"] is True
        finally:
            hooks_file.chmod(0o644)

    def test_uninstall_preserves_non_gobby_hooks(self, project: Path) -> None:
        """Hooks not referencing hook_dispatcher.py are preserved."""
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)

        hooks_config = {
            "hooks": {
                "lint": [{"command": "eslint --fix"}],
                "format": [{"command": "prettier --write"}],
            }
        }
        (windsurf_path / "hooks.json").write_text(json.dumps(hooks_config))

        result = uninstall_windsurf(project)
        assert result["success"] is True
        assert result["hooks_removed"] == []

        with open(windsurf_path / "hooks.json") as f:
            data = json.load(f)
        assert "lint" in data["hooks"]
        assert "format" in data["hooks"]

    def test_uninstall_hooks_not_list_skipped(self, project: Path) -> None:
        """Hook entries that are not lists are skipped."""
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)

        hooks_config = {
            "hooks": {
                "dict_hook": {"command": "python hook_dispatcher.py"},
                "list_hook": [{"command": "python /path/hook_dispatcher.py list_hook"}],
            }
        }
        (windsurf_path / "hooks.json").write_text(json.dumps(hooks_config))

        result = uninstall_windsurf(project)
        assert result["success"] is True
        assert "list_hook" in result["hooks_removed"]
        assert "dict_hook" not in result["hooks_removed"]

    def test_uninstall_dispatcher_removal_failure(self, project: Path) -> None:
        """Continues when dispatcher removal fails."""
        windsurf_path = project / ".windsurf"
        hooks_dir = windsurf_path / "hooks"
        hooks_dir.mkdir(parents=True)
        dispatcher = hooks_dir / "hook_dispatcher.py"
        dispatcher.write_text("# dispatcher")

        with patch.object(Path, "unlink", side_effect=OSError("Permission denied")):
            result = uninstall_windsurf(project)

        assert result["success"] is True

    def test_uninstall_result_structure(self, project: Path) -> None:
        """Result dictionary has expected structure."""
        result = uninstall_windsurf(project)
        expected_keys = {"success", "hooks_removed", "files_removed", "error"}
        assert set(result.keys()) == expected_keys

    def test_uninstall_empty_hooks_section(self, project: Path) -> None:
        """Uninstall with empty hooks section."""
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)
        (windsurf_path / "hooks.json").write_text(json.dumps({"hooks": {}}))

        result = uninstall_windsurf(project)
        assert result["success"] is True
        assert result["hooks_removed"] == []

    def test_uninstall_no_hooks_key(self, project: Path) -> None:
        """Uninstall when hooks.json has no 'hooks' key."""
        windsurf_path = project / ".windsurf"
        windsurf_path.mkdir(parents=True)
        (windsurf_path / "hooks.json").write_text(json.dumps({"other": "value"}))

        result = uninstall_windsurf(project)
        assert result["success"] is True
        assert result["hooks_removed"] == []
