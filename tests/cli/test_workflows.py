from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli.workflows import workflows
from gobby.workflows.definitions import WorkflowDefinition, WorkflowStep

pytestmark = pytest.mark.unit

# Mock workflow definition
MOCK_WORKFLOW = WorkflowDefinition(
    name="test-workflow",
    description="A test workflow",
    type="step",
    version="1.0",
    steps=[
        WorkflowStep(name="step1", description="First step"),
        WorkflowStep(name="step2", description="Second step"),
    ],
)


@pytest.fixture
def mock_loader():
    with patch("gobby.cli.workflows.get_workflow_loader") as mock:
        yield mock.return_value


@pytest.fixture
def mock_state_manager():
    with patch("gobby.cli.workflows.get_state_manager") as mock:
        yield mock.return_value


def test_list_workflows_empty(mock_loader) -> None:
    """Test 'workflows list' with no workflows."""
    # Mock global_dirs to be empty or contain directories with no yaml
    mock_loader.global_dirs = []

    # We also need to patch pathlib.Path.cwd to return a path without .gobby
    with patch("gobby.cli.workflows.Path.cwd") as mock_cwd:
        mock_cwd.return_value = MagicMock()
        mock_cwd.return_value.__truediv__.return_value.exists.return_value = False

        runner = CliRunner()
        result = runner.invoke(workflows, ["list"])

    assert result.exit_code == 0
    assert "No workflows found" in result.output


@patch("gobby.cli.workflows.get_project_path", return_value=None)
@patch("gobby.cli.workflows.yaml.safe_load")
@patch("gobby.cli.workflows.open", new_callable=MagicMock)
def test_list_workflows_found(mock_open, mock_yaml, mock_project_path, mock_loader):
    """Test 'workflows list' finding files."""
    mock_dir = MagicMock()
    mock_dir.exists.return_value = True

    mock_file = MagicMock()
    mock_file.stem = "test-workflow"
    mock_dir.glob.return_value = [mock_file]

    mock_loader.global_dirs = [mock_dir]

    mock_open.return_value.__enter__.return_value.read.return_value = (
        "name: test-workflow\ntype: step\n"
    )
    mock_yaml.return_value = {
        "name": "test-workflow",
        "type": "step",
        "description": "desc",
    }

    runner = CliRunner()
    result = runner.invoke(workflows, ["list"])

    assert result.exit_code == 0
    assert "test-workflow" in result.output
    assert "(step)" in result.output
    # [global] tag is not shown for global workflows
    assert "desc" in result.output


def test_show_workflow(mock_loader) -> None:
    """Test 'workflows show' with valid name."""
    mock_loader.load_workflow_sync.return_value = MOCK_WORKFLOW

    runner = CliRunner()
    result = runner.invoke(workflows, ["show", "test-workflow"])

    assert result.exit_code == 0
    assert "Workflow: test-workflow" in result.output
    assert "Steps (2):" in result.output
    assert "- step1" in result.output


def test_show_workflow_not_found(mock_loader) -> None:
    """Test 'workflows show' with invalid name."""
    mock_loader.load_workflow_sync.return_value = None

    runner = CliRunner()
    result = runner.invoke(workflows, ["show", "invalid"])

    assert result.exit_code == 1
    assert "not found" in result.output


def test_status_no_active(mock_state_manager) -> None:
    """Test 'workflows status' with no active workflow."""
    mock_state_manager.get_state.return_value = None

    runner = CliRunner()
    with patch("gobby.cli.workflows.resolve_session_id", return_value="sess-123"):
        result = runner.invoke(workflows, ["status"])

    assert result.exit_code == 0
    assert "No workflow active" in result.output


def test_set_workflow_success(mock_loader, mock_state_manager) -> None:
    """Test 'workflows set' successfully."""
    mock_loader.load_workflow_sync.return_value = MOCK_WORKFLOW
    mock_state_manager.get_state.return_value = None  # No existing workflow

    runner = CliRunner()
    with patch("gobby.cli.workflows.resolve_session_id", return_value="sess-123"):
        result = runner.invoke(workflows, ["set", "test-workflow"])

    assert result.exit_code == 0
    assert "Activated workflow 'test-workflow'" in result.output
    mock_state_manager.save_state.assert_called_once()


def test_clear_workflow(mock_state_manager) -> None:
    """Test 'workflows clear'."""
    mock_state = MagicMock()
    mock_state.workflow_name = "test-workflow"
    mock_state_manager.get_state.return_value = mock_state

    runner = CliRunner()
    with patch("gobby.cli.workflows.resolve_session_id", return_value="sess-123"):
        result = runner.invoke(workflows, ["clear"], input="y\n")

    assert result.exit_code == 0
    assert "Cleared workflow" in result.output
    mock_state_manager.delete_state.assert_called_once()
