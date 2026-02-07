"""Tests for gobby export/import CLI commands."""

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from gobby.cli.export_import import export_cmd, import_cmd

pytestmark = pytest.mark.unit


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def project_with_resources(tmp_path: Path):
    """Create a project directory with sample resources."""
    project = tmp_path / "project"
    project.mkdir()

    # Create workflows
    wf_dir = project / ".gobby" / "workflows" / "lifecycle"
    wf_dir.mkdir(parents=True)
    (wf_dir / "session-lifecycle.yaml").write_text("name: session-lifecycle\nversion: '1.0'\n")
    (project / ".gobby" / "workflows" / "custom.yaml").write_text("name: custom\n")

    # Create agents
    ag_dir = project / ".gobby" / "agents"
    ag_dir.mkdir(parents=True)
    (ag_dir / "my-agent.yaml").write_text("name: my-agent\n")

    # Create prompts
    pr_dir = project / ".gobby" / "prompts" / "expansion"
    pr_dir.mkdir(parents=True)
    (pr_dir / "system.md").write_text("You are a helpful assistant.")

    return project


class TestExportCommand:
    """Tests for the export command."""

    def test_dry_run_lists_resources(self, runner, project_with_resources) -> None:
        """Dry run lists resources without copying."""
        os.chdir(project_with_resources)
        result = runner.invoke(export_cmd, ["workflow"])
        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert "session-lifecycle.yaml" in result.output
        assert "custom.yaml" in result.output

    def test_export_to_target_directory(self, runner, project_with_resources, tmp_path) -> None:
        """Export copies to target directory."""
        os.chdir(project_with_resources)
        target = tmp_path / "target_project"
        target.mkdir()

        result = runner.invoke(export_cmd, ["agent", "--to", str(target)])
        assert result.exit_code == 0
        assert "exported" in result.output
        assert (target / ".gobby" / "agents" / "my-agent.yaml").exists()

    def test_export_global(self, runner, project_with_resources, tmp_path) -> None:
        """Export --global copies to ~/.gobby/."""
        os.chdir(project_with_resources)

        # Use a fake home to avoid polluting real ~/.gobby
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(Path, "home", classmethod(lambda cls: fake_home))
            result = runner.invoke(export_cmd, ["prompt", "--global"])

        assert result.exit_code == 0
        assert "exported" in result.output
        assert (fake_home / ".gobby" / "prompts" / "expansion" / "system.md").exists()

    def test_export_specific_name(self, runner, project_with_resources) -> None:
        """Export with name filters to specific resource."""
        os.chdir(project_with_resources)
        result = runner.invoke(export_cmd, ["workflow", "custom"])
        assert result.exit_code == 0
        assert "custom.yaml" in result.output

    def test_export_no_resources(self, runner, tmp_path) -> None:
        """Export with no resources shows appropriate message."""
        empty_project = tmp_path / "empty"
        empty_project.mkdir()
        (empty_project / ".gobby").mkdir()
        os.chdir(empty_project)

        result = runner.invoke(export_cmd, ["workflow"])
        assert result.exit_code == 0
        assert "No resources found" in result.output

    def test_export_all_types(self, runner, project_with_resources) -> None:
        """Export all lists all resource types."""
        os.chdir(project_with_resources)
        result = runner.invoke(export_cmd, ["all"])
        assert result.exit_code == 0
        assert "workflows:" in result.output
        assert "agents:" in result.output
        assert "prompts:" in result.output


class TestImportCommand:
    """Tests for the import command."""

    def test_import_from_project(self, runner, project_with_resources, tmp_path) -> None:
        """Import copies from source project to current project."""
        target = tmp_path / "target"
        target.mkdir()
        (target / ".gobby").mkdir()
        os.chdir(target)

        result = runner.invoke(
            import_cmd, ["workflow", "--from-project", str(project_with_resources)]
        )
        assert result.exit_code == 0
        assert "imported" in result.output
        assert (target / ".gobby" / "workflows" / "lifecycle" / "session-lifecycle.yaml").exists()

    def test_import_single_file(self, runner, project_with_resources, tmp_path) -> None:
        """Import a single file directly."""
        target = tmp_path / "target"
        target.mkdir()
        (target / ".gobby").mkdir()
        os.chdir(target)

        source_file = project_with_resources / ".gobby" / "agents" / "my-agent.yaml"
        result = runner.invoke(import_cmd, ["agent", "--from", str(source_file)])
        assert result.exit_code == 0
        assert (target / ".gobby" / "agents" / "my-agent.yaml").exists()

    def test_import_no_source_error(self, runner, tmp_path) -> None:
        """Import without --from or --from-project shows error."""
        os.chdir(tmp_path)
        result = runner.invoke(import_cmd, ["workflow"])
        assert result.exit_code != 0
        assert "Error" in result.output or "specify" in result.output

    def test_import_specific_name(self, runner, project_with_resources, tmp_path) -> None:
        """Import with name filters to specific resource."""
        target = tmp_path / "target"
        target.mkdir()
        (target / ".gobby").mkdir()
        os.chdir(target)

        result = runner.invoke(
            import_cmd, ["agent", "my-agent", "--from-project", str(project_with_resources)]
        )
        assert result.exit_code == 0
        assert (target / ".gobby" / "agents" / "my-agent.yaml").exists()
