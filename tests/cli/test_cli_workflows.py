import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli.workflows import workflows
from gobby.workflows.definitions import WorkflowDefinition, WorkflowState, WorkflowStep

pytestmark = pytest.mark.unit

@pytest.fixture
def mock_loader():
    loader = MagicMock()
    loader.global_dirs = []
    return loader


@pytest.fixture
def mock_state_manager():
    return MagicMock()


@pytest.fixture
def cli_runner():
    return CliRunner()


def test_list_workflows_empty(cli_runner, mock_loader) -> None:
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_project_path", return_value=None):
            result = cli_runner.invoke(workflows, ["list"])
            assert result.exit_code == 0
            assert "No workflows found" in result.output


def test_list_workflows_found(cli_runner, mock_loader, tmp_path) -> None:
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_project_path", return_value=tmp_path):
            # Mock glob
            wf_file = tmp_path / "test_wf.yaml"
            wf_file.write_text("name: Test Workflow\ntype: step\ndescription: A test")

            mock_loader.global_dirs = [tmp_path]

            result = cli_runner.invoke(workflows, ["list", "--global"])

            # This test relies on globbing which mock_loader doesn't do, list_workflows does globbing on dirs from loader
            # So actual filesystem is used if we point loader there.

            assert result.exit_code == 0
            assert "test_wf" in result.output
            assert "(step)" in result.output


def test_show_workflow(cli_runner, mock_loader) -> None:
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_project_path", return_value=None):
            defi = WorkflowDefinition(
                name="test", steps=[WorkflowStep(name="step1", description="step desc")]
            )
            mock_loader.load_workflow.return_value = defi

            result = cli_runner.invoke(workflows, ["show", "test"])

            assert result.exit_code == 0
            assert "Workflow: test" in result.output
            assert "step1" in result.output
            assert "step desc" in result.output


def test_status_no_session(cli_runner, mock_state_manager) -> None:
    import click

    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        # Mock resolve_session_id to raise no active session error
        # The CLI catches this and does SystemExit(1) without message
        with patch(
            "gobby.cli.workflows.resolve_session_id",
            side_effect=click.ClickException("No active session found"),
        ):
            result = cli_runner.invoke(workflows, ["status"])
            # Exit code 1 indicates no session found
            assert result.exit_code == 1


def test_status_active(cli_runner, mock_state_manager) -> None:
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            state = MagicMock(spec=WorkflowState)
            state.workflow_name = "active_wf"
            state.step = "step1"
            state.step_action_count = 5
            state.total_action_count = 10
            state.disabled = False
            state.artifacts = {}
            state.task_list = None
            state.reflection_pending = False
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["status", "--session", "sess1"])

            assert result.exit_code == 0
            assert "Workflow: active_wf" in result.output
            assert "Step: step1" in result.output


def test_set_workflow(cli_runner, mock_loader, mock_state_manager) -> None:
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
            with patch("gobby.cli.workflows.get_project_path", return_value=None):
                with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
                    # Mock definition
                    defi = WorkflowDefinition(name="new_wf", steps=[WorkflowStep(name="start")])
                    mock_loader.load_workflow.return_value = defi

                    # Mock no existing state
                    mock_state_manager.get_state.return_value = None

                    result = cli_runner.invoke(workflows, ["set", "new_wf", "--session", "sess1"])

                    assert result.exit_code == 0
                    assert "Activated workflow 'new_wf'" in result.output
                    mock_state_manager.save_state.assert_called_once()


def test_clear_workflow(cli_runner, mock_state_manager) -> None:
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            state = MagicMock(spec=WorkflowState)
            state.workflow_name = "w1"
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["clear", "--session", "sess1", "--force"])

            assert result.exit_code == 0
            assert "Cleared workflow" in result.output
            mock_state_manager.delete_state.assert_called_with("sess1")


# ==============================================================================
# Additional Tests for list_workflows
# ==============================================================================


def test_list_workflows_json_format(cli_runner, mock_loader, tmp_path) -> None:
    """Test list workflows with JSON output format."""
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_project_path", return_value=tmp_path):
            wf_file = tmp_path / "my_workflow.yaml"
            wf_file.write_text("name: My Workflow\ntype: step\ndescription: Test")
            mock_loader.global_dirs = [tmp_path]

            result = cli_runner.invoke(workflows, ["list", "--json", "--global"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "workflows" in data
            assert "count" in data


def test_list_workflows_with_all_flag(cli_runner, mock_loader, tmp_path) -> None:
    """Test list workflows with --all flag."""
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_project_path", return_value=tmp_path):
            wf_file = tmp_path / "lifecycle_wf.yaml"
            wf_file.write_text(
                "name: Lifecycle\ntype: lifecycle\ndescription: A lifecycle workflow"
            )
            mock_loader.global_dirs = [tmp_path]

            result = cli_runner.invoke(workflows, ["list", "--all", "--global"])

            assert result.exit_code == 0
            assert "lifecycle_wf" in result.output


# ==============================================================================
# Additional Tests for show_workflow
# ==============================================================================


def test_show_workflow_not_found(cli_runner, mock_loader) -> None:
    """Test show workflow when workflow not found."""
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_project_path", return_value=None):
            mock_loader.load_workflow.return_value = None

            result = cli_runner.invoke(workflows, ["show", "nonexistent"])

            assert result.exit_code == 1
            assert "not found" in result.output


def test_show_workflow_json_format(cli_runner, mock_loader) -> None:
    """Test show workflow with JSON output."""
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_project_path", return_value=None):
            defi = WorkflowDefinition(
                name="test",
                steps=[WorkflowStep(name="step1", description="step desc")],
            )
            mock_loader.load_workflow.return_value = defi

            result = cli_runner.invoke(workflows, ["show", "test", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["name"] == "test"


def test_show_workflow_with_tools(cli_runner, mock_loader) -> None:
    """Test show workflow with allowed/blocked tools."""
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_project_path", return_value=None):
            defi = WorkflowDefinition(
                name="test",
                steps=[
                    WorkflowStep(
                        name="plan",
                        description="Planning step",
                        allowed_tools=["Read", "Glob", "Grep"],
                        blocked_tools=["Edit", "Write"],
                    )
                ],
            )
            mock_loader.load_workflow.return_value = defi

            result = cli_runner.invoke(workflows, ["show", "test"])

            assert result.exit_code == 0
            assert "Allowed tools:" in result.output
            assert "Blocked tools:" in result.output


# ==============================================================================
# Tests for status with more states
# ==============================================================================


def test_status_json_format(cli_runner, mock_state_manager) -> None:
    """Test status with JSON output format."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            state = MagicMock(spec=WorkflowState)
            state.workflow_name = "test_wf"
            state.step = "planning"
            state.step_action_count = 3
            state.total_action_count = 7
            state.disabled = False
            state.disabled_reason = None
            state.artifacts = {"plan": "/path/to/plan.md"}
            state.task_list = None
            state.reflection_pending = False
            state.updated_at = None
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["status", "--session", "sess1", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["has_workflow"] is True
            assert data["workflow_name"] == "test_wf"
            assert data["step"] == "planning"


def test_status_no_workflow(cli_runner, mock_state_manager) -> None:
    """Test status when no workflow is active."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            mock_state_manager.get_state.return_value = None

            result = cli_runner.invoke(workflows, ["status", "--session", "sess1"])

            assert result.exit_code == 0
            assert "No workflow active" in result.output


def test_status_disabled_workflow(cli_runner, mock_state_manager) -> None:
    """Test status showing disabled workflow."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            state = MagicMock(spec=WorkflowState)
            state.workflow_name = "test_wf"
            state.step = "blocked"
            state.step_action_count = 0
            state.total_action_count = 5
            state.disabled = True
            state.disabled_reason = "Manual override"
            state.artifacts = {}
            state.task_list = None
            state.reflection_pending = False
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["status", "--session", "sess1"])

            assert result.exit_code == 0
            assert "DISABLED" in result.output
            assert "Manual override" in result.output


# ==============================================================================
# Tests for set_workflow with more cases
# ==============================================================================


def test_set_workflow_lifecycle_rejected(cli_runner, mock_loader, mock_state_manager) -> None:
    """Test that lifecycle workflows cannot be manually set."""
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
            with patch("gobby.cli.workflows.get_project_path", return_value=None):
                with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
                    defi = WorkflowDefinition(name="lifecycle_wf", type="lifecycle")
                    mock_loader.load_workflow.return_value = defi

                    result = cli_runner.invoke(
                        workflows, ["set", "lifecycle_wf", "--session", "sess1"]
                    )

                    assert result.exit_code == 1
                    assert "lifecycle workflow" in result.output


def test_set_workflow_already_active(cli_runner, mock_loader, mock_state_manager) -> None:
    """Test setting workflow when another is already active."""
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
            with patch("gobby.cli.workflows.get_project_path", return_value=None):
                with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
                    defi = WorkflowDefinition(name="new_wf", steps=[WorkflowStep(name="start")])
                    mock_loader.load_workflow.return_value = defi

                    existing_state = MagicMock(spec=WorkflowState)
                    existing_state.workflow_name = "existing_wf"
                    mock_state_manager.get_state.return_value = existing_state

                    result = cli_runner.invoke(workflows, ["set", "new_wf", "--session", "sess1"])

                    assert result.exit_code == 1
                    assert "already has workflow" in result.output


def test_set_workflow_with_initial_step(cli_runner, mock_loader, mock_state_manager) -> None:
    """Test setting workflow with specific initial step."""
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
            with patch("gobby.cli.workflows.get_project_path", return_value=None):
                with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
                    defi = WorkflowDefinition(
                        name="multi_step",
                        steps=[
                            WorkflowStep(name="plan"),
                            WorkflowStep(name="implement"),
                            WorkflowStep(name="review"),
                        ],
                    )
                    mock_loader.load_workflow.return_value = defi
                    mock_state_manager.get_state.return_value = None

                    result = cli_runner.invoke(
                        workflows,
                        ["set", "multi_step", "--session", "sess1", "--step", "implement"],
                    )

                    assert result.exit_code == 0
                    assert "Starting step: implement" in result.output


# ==============================================================================
# Tests for step command
# ==============================================================================


def test_step_transition(cli_runner, mock_loader, mock_state_manager) -> None:
    """Test transitioning to a different step."""
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
            with patch("gobby.cli.workflows.get_project_path", return_value=None):
                with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
                    defi = WorkflowDefinition(
                        name="test_wf",
                        steps=[WorkflowStep(name="plan"), WorkflowStep(name="implement")],
                    )
                    mock_loader.load_workflow.return_value = defi

                    state = MagicMock(spec=WorkflowState)
                    state.workflow_name = "test_wf"
                    state.step = "plan"
                    mock_state_manager.get_state.return_value = state

                    result = cli_runner.invoke(
                        workflows, ["step", "implement", "--session", "sess1", "--force"]
                    )

                    assert result.exit_code == 0
                    assert "Transitioned from 'plan' to 'implement'" in result.output


def test_step_invalid_step(cli_runner, mock_loader, mock_state_manager) -> None:
    """Test transitioning to invalid step."""
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
            with patch("gobby.cli.workflows.get_project_path", return_value=None):
                with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
                    defi = WorkflowDefinition(
                        name="test_wf",
                        steps=[WorkflowStep(name="plan")],
                    )
                    mock_loader.load_workflow.return_value = defi

                    state = MagicMock(spec=WorkflowState)
                    state.workflow_name = "test_wf"
                    state.step = "plan"
                    mock_state_manager.get_state.return_value = state

                    result = cli_runner.invoke(
                        workflows, ["step", "nonexistent", "--session", "sess1", "--force"]
                    )

                    assert result.exit_code == 1
                    assert "not found" in result.output


def test_step_no_workflow(cli_runner, mock_state_manager) -> None:
    """Test step command when no workflow is active."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            mock_state_manager.get_state.return_value = None

            result = cli_runner.invoke(workflows, ["step", "plan", "--session", "sess1", "--force"])

            assert result.exit_code == 1
            assert "No workflow active" in result.output


# ==============================================================================
# Tests for reset command
# ==============================================================================


def test_reset_workflow(cli_runner, mock_state_manager) -> None:
    """Test resetting workflow to initial step."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            state = MagicMock(spec=WorkflowState)
            state.workflow_name = "test_wf"
            state.step = "implement"
            state.initial_step = "plan"
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["reset", "--session", "sess1", "--force"])

            assert result.exit_code == 0
            assert "Reset workflow to initial step" in result.output


def test_reset_workflow_already_at_initial(cli_runner, mock_state_manager) -> None:
    """Test reset when already at initial step."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            state = MagicMock(spec=WorkflowState)
            state.workflow_name = "test_wf"
            state.step = "plan"
            state.initial_step = "plan"
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["reset", "--session", "sess1"])

            assert result.exit_code == 0
            assert "already at initial step" in result.output


# ==============================================================================
# Tests for disable/enable commands
# ==============================================================================


def test_disable_workflow(cli_runner, mock_state_manager) -> None:
    """Test disabling a workflow."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            state = MagicMock(spec=WorkflowState)
            state.workflow_name = "test_wf"
            state.disabled = False
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(
                workflows, ["disable", "--session", "sess1", "--reason", "debugging"]
            )

            assert result.exit_code == 0
            assert "Disabled workflow" in result.output


def test_disable_already_disabled(cli_runner, mock_state_manager) -> None:
    """Test disabling an already disabled workflow."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            state = MagicMock(spec=WorkflowState)
            state.workflow_name = "test_wf"
            state.disabled = True
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["disable", "--session", "sess1"])

            assert result.exit_code == 0
            assert "already disabled" in result.output


def test_enable_workflow(cli_runner, mock_state_manager) -> None:
    """Test enabling a disabled workflow."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            state = MagicMock(spec=WorkflowState)
            state.workflow_name = "test_wf"
            state.disabled = True
            state.step = "plan"
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["enable", "--session", "sess1"])

            assert result.exit_code == 0
            assert "Re-enabled workflow" in result.output


def test_enable_not_disabled(cli_runner, mock_state_manager) -> None:
    """Test enabling a workflow that's not disabled."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            state = MagicMock(spec=WorkflowState)
            state.workflow_name = "test_wf"
            state.disabled = False
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["enable", "--session", "sess1"])

            assert result.exit_code == 0
            assert "not disabled" in result.output


# ==============================================================================
# Tests for artifact command
# ==============================================================================


def test_mark_artifact(cli_runner, mock_state_manager) -> None:
    """Test marking an artifact as complete."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            state = MagicMock(spec=WorkflowState)
            state.workflow_name = "test_wf"
            state.artifacts = {}
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(
                workflows, ["artifact", "plan", "/path/to/plan.md", "--session", "sess1"]
            )

            assert result.exit_code == 0
            assert "Marked 'plan' artifact complete" in result.output


def test_mark_multiple_artifacts(cli_runner, mock_state_manager) -> None:
    """Test marking multiple artifacts."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            state = MagicMock(spec=WorkflowState)
            state.workflow_name = "test_wf"
            state.artifacts = {"spec": "/path/to/spec.md"}
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(
                workflows, ["artifact", "plan", "/path/to/plan.md", "--session", "sess1"]
            )

            assert result.exit_code == 0
            assert "All artifacts:" in result.output


# ==============================================================================
# Tests for import command
# ==============================================================================


def test_import_workflow_file(cli_runner, tmp_path) -> None:
    """Test importing a workflow from a file."""
    # Create a source workflow file
    source_file = tmp_path / "source_wf.yaml"
    source_file.write_text("name: Imported Workflow\ntype: step\ndescription: Test")

    # Create a project directory
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    gobby_dir = project_dir / ".gobby"
    gobby_dir.mkdir()

    with patch("gobby.cli.workflows.get_project_path", return_value=project_dir):
        result = cli_runner.invoke(workflows, ["import", str(source_file)])

        assert result.exit_code == 0
        assert "Imported workflow" in result.output


def test_import_workflow_not_yaml(cli_runner, tmp_path) -> None:
    """Test importing a non-YAML file fails."""
    source_file = tmp_path / "source.txt"
    source_file.write_text("not yaml")

    result = cli_runner.invoke(workflows, ["import", str(source_file)])

    assert result.exit_code == 1
    assert ".yaml extension" in result.output


def test_import_workflow_file_not_found(cli_runner) -> None:
    """Test importing non-existent file."""
    result = cli_runner.invoke(workflows, ["import", "/nonexistent/path.yaml"])

    assert result.exit_code == 1
    assert "not found" in result.output


# ==============================================================================
# Tests for audit command
# ==============================================================================


def test_audit_no_entries(cli_runner, mock_state_manager) -> None:
    """Test audit with no entries."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            with patch("gobby.storage.workflow_audit.WorkflowAuditManager") as MockAudit:
                mock_audit = MagicMock()
                mock_audit.get_entries.return_value = []
                MockAudit.return_value = mock_audit

                result = cli_runner.invoke(workflows, ["audit", "--session", "sess1"])

                assert result.exit_code == 0
                assert "No audit entries found" in result.output


def test_audit_with_entries(cli_runner, mock_state_manager) -> None:
    """Test audit with entries."""
    from datetime import UTC, datetime

    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            with patch("gobby.storage.workflow_audit.WorkflowAuditManager") as MockAudit:
                mock_entry = MagicMock()
                mock_entry.id = "entry-1"
                mock_entry.timestamp = datetime.now(UTC)
                mock_entry.step = "plan"
                mock_entry.event_type = "tool_call"
                mock_entry.tool_name = "Edit"
                mock_entry.rule_id = None
                mock_entry.condition = None
                mock_entry.result = "block"
                mock_entry.reason = "Edit not allowed in plan step"
                mock_entry.context = {}

                mock_audit = MagicMock()
                mock_audit.get_entries.return_value = [mock_entry]
                MockAudit.return_value = mock_audit

                result = cli_runner.invoke(workflows, ["audit", "--session", "sess1"])

                assert result.exit_code == 0
                assert "BLOCK" in result.output
                assert "tool_call" in result.output


def test_audit_json_format(cli_runner, mock_state_manager) -> None:
    """Test audit with JSON output."""
    from datetime import UTC, datetime

    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            with patch("gobby.storage.workflow_audit.WorkflowAuditManager") as MockAudit:
                mock_entry = MagicMock()
                mock_entry.id = "entry-1"
                mock_entry.timestamp = datetime.now(UTC)
                mock_entry.step = "plan"
                mock_entry.event_type = "tool_call"
                mock_entry.tool_name = "Edit"
                mock_entry.rule_id = None
                mock_entry.condition = None
                mock_entry.result = "allow"
                mock_entry.reason = None
                mock_entry.context = {}

                mock_audit = MagicMock()
                mock_audit.get_entries.return_value = [mock_entry]
                MockAudit.return_value = mock_audit

                result = cli_runner.invoke(workflows, ["audit", "--session", "sess1", "--json"])

                assert result.exit_code == 0
                data = json.loads(result.output)
                assert isinstance(data, list)
                assert len(data) == 1


# ==============================================================================
# Tests for set-var command
# ==============================================================================


def test_set_variable_string(cli_runner, mock_state_manager) -> None:
    """Test setting a string variable."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.LocalDatabase") as MockDB:
            mock_db = MagicMock()
            mock_db.fetchone.return_value = {"id": "sess1"}
            MockDB.return_value = mock_db

            state = MagicMock(spec=WorkflowState)
            state.variables = {}
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["set-var", "my_var", "my_value"])

            assert result.exit_code == 0
            assert "Set my_var" in result.output


def test_set_variable_boolean(cli_runner, mock_state_manager) -> None:
    """Test setting a boolean variable."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.LocalDatabase") as MockDB:
            mock_db = MagicMock()
            mock_db.fetchone.return_value = {"id": "sess1"}
            MockDB.return_value = mock_db

            state = MagicMock(spec=WorkflowState)
            state.variables = {}
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["set-var", "debug_mode", "true"])

            assert result.exit_code == 0
            assert "Set debug_mode" in result.output
            # Check that the value was parsed as boolean
            call_args = mock_state_manager.save_state.call_args
            saved_state = call_args[0][0]
            assert saved_state.variables["debug_mode"] is True


def test_set_variable_integer(cli_runner, mock_state_manager) -> None:
    """Test setting an integer variable."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.LocalDatabase") as MockDB:
            mock_db = MagicMock()
            mock_db.fetchone.return_value = {"id": "sess1"}
            MockDB.return_value = mock_db

            state = MagicMock(spec=WorkflowState)
            state.variables = {}
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["set-var", "max_retries", "5"])

            assert result.exit_code == 0
            call_args = mock_state_manager.save_state.call_args
            saved_state = call_args[0][0]
            assert saved_state.variables["max_retries"] == 5


def test_set_variable_null(cli_runner, mock_state_manager) -> None:
    """Test setting a null variable."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.LocalDatabase") as MockDB:
            mock_db = MagicMock()
            mock_db.fetchone.return_value = {"id": "sess1"}
            MockDB.return_value = mock_db

            state = MagicMock(spec=WorkflowState)
            state.variables = {"existing": "value"}
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["set-var", "existing", "null"])

            assert result.exit_code == 0


# ==============================================================================
# Tests for get-var command
# ==============================================================================


def test_get_variable_specific(cli_runner, mock_state_manager) -> None:
    """Test getting a specific variable."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.LocalDatabase") as MockDB:
            mock_db = MagicMock()
            mock_db.fetchone.return_value = {"id": "sess1"}
            MockDB.return_value = mock_db

            state = MagicMock(spec=WorkflowState)
            state.variables = {"my_var": "my_value"}
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["get-var", "my_var"])

            assert result.exit_code == 0
            assert "my_var = 'my_value'" in result.output


def test_get_variable_not_set(cli_runner, mock_state_manager) -> None:
    """Test getting a variable that's not set."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.LocalDatabase") as MockDB:
            mock_db = MagicMock()
            mock_db.fetchone.return_value = {"id": "sess1"}
            MockDB.return_value = mock_db

            state = MagicMock(spec=WorkflowState)
            state.variables = {}
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["get-var", "nonexistent"])

            assert result.exit_code == 0
            assert "not set" in result.output


def test_get_all_variables(cli_runner, mock_state_manager) -> None:
    """Test getting all variables."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.LocalDatabase") as MockDB:
            mock_db = MagicMock()
            mock_db.fetchone.return_value = {"id": "sess1"}
            MockDB.return_value = mock_db

            state = MagicMock(spec=WorkflowState)
            state.variables = {"var1": "value1", "var2": 42}
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["get-var"])

            assert result.exit_code == 0
            assert "var1" in result.output
            assert "var2" in result.output


def test_get_all_variables_json(cli_runner, mock_state_manager) -> None:
    """Test getting all variables in JSON format."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.LocalDatabase") as MockDB:
            mock_db = MagicMock()
            mock_db.fetchone.return_value = {"id": "sess1"}
            MockDB.return_value = mock_db

            state = MagicMock(spec=WorkflowState)
            state.variables = {"var1": "value1", "var2": 42}
            mock_state_manager.get_state.return_value = state

            result = cli_runner.invoke(workflows, ["get-var", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["variables"]["var1"] == "value1"
            assert data["variables"]["var2"] == 42


# ==============================================================================
# Tests for clear command with confirmation
# ==============================================================================


def test_clear_workflow_requires_confirmation(cli_runner, mock_state_manager) -> None:
    """Test clear workflow requires confirmation without --force."""
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        with patch("gobby.cli.workflows.resolve_session_id", return_value="sess1"):
            state = MagicMock(spec=WorkflowState)
            state.workflow_name = "test_wf"
            mock_state_manager.get_state.return_value = state

            # Abort confirmation
            result = cli_runner.invoke(workflows, ["clear", "--session", "sess1"], input="n\n")

            assert result.exit_code == 1  # Aborted
            mock_state_manager.delete_state.assert_not_called()
