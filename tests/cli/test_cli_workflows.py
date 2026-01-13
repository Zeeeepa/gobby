import json
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner
from gobby.cli.workflows import workflows
from gobby.workflows.definitions import WorkflowDefinition, WorkflowState, WorkflowStep


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


def test_list_workflows_empty(cli_runner, mock_loader):
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_project_path", return_value=None):
            result = cli_runner.invoke(workflows, ["list"])
            assert result.exit_code == 0
            assert "No workflows found" in result.output


def test_list_workflows_found(cli_runner, mock_loader, tmp_path):
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


def test_show_workflow(cli_runner, mock_loader):
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


def test_status_no_session(cli_runner, mock_state_manager):
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        # Mock DB fetchone
        with patch("gobby.cli.workflows.LocalDatabase") as MockDB:
            MockDB.return_value.fetchone.return_value = None

            result = cli_runner.invoke(workflows, ["status"])
            assert result.exit_code == 1
            assert "No active session found" in result.output


def test_status_active(cli_runner, mock_state_manager):
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
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


def test_set_workflow(cli_runner, mock_loader, mock_state_manager):
    with patch("gobby.cli.workflows.get_workflow_loader", return_value=mock_loader):
        with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
            with patch("gobby.cli.workflows.get_project_path", return_value=None):
                # Mock definition
                defi = WorkflowDefinition(name="new_wf", steps=[WorkflowStep(name="start")])
                mock_loader.load_workflow.return_value = defi

                # Mock no existing state
                mock_state_manager.get_state.return_value = None

                result = cli_runner.invoke(workflows, ["set", "new_wf", "--session", "sess1"])

                assert result.exit_code == 0
                assert "Activated workflow 'new_wf'" in result.output
                mock_state_manager.save_state.assert_called_once()


def test_clear_workflow(cli_runner, mock_state_manager):
    with patch("gobby.cli.workflows.get_state_manager", return_value=mock_state_manager):
        state = MagicMock(spec=WorkflowState)
        state.workflow_name = "w1"
        mock_state_manager.get_state.return_value = state

        result = cli_runner.invoke(workflows, ["clear", "--session", "sess1", "--force"])

        assert result.exit_code == 0
        assert "Cleared workflow" in result.output
        mock_state_manager.delete_state.assert_called_with("sess1")
