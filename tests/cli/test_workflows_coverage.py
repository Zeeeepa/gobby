from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from gobby.cli.workflows import workflows
from gobby.workflows.definitions import WorkflowState

pytestmark = pytest.mark.unit


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_loader():
    with patch("gobby.cli.workflows.get_workflow_loader") as m:
        loader = Mock()
        m.return_value = loader
        yield loader


@pytest.fixture
def mock_state_manager():
    with patch("gobby.cli.workflows.get_state_manager") as m:
        manager = Mock()
        m.return_value = manager
        yield manager


@pytest.fixture
def mock_resolve_session():
    with patch("gobby.cli.workflows.resolve_session_id") as m:
        m.return_value = "sess-123"
        yield m


def test_list_workflows_empty(runner, mock_loader) -> None:
    mock_loader.global_dirs = []
    # patch get_project_path
    with patch("gobby.cli.workflows.get_project_path", return_value=None):
        result = runner.invoke(workflows, ["list"])
        assert result.exit_code == 0
        assert "No workflows found" in result.output


def test_show_workflow_not_found(runner, mock_loader) -> None:
    mock_loader.load_workflow_sync.return_value = None
    with patch("gobby.cli.workflows.get_project_path", return_value=None):
        result = runner.invoke(workflows, ["show", "unknown"])
        assert result.exit_code == 1
        assert "Workflow 'unknown' not found" in result.output


def test_status_no_workflow(runner, mock_state_manager, mock_resolve_session) -> None:
    mock_state_manager.get_state.return_value = None
    result = runner.invoke(workflows, ["status"])
    assert result.exit_code == 0
    assert "No workflow active" in result.output


def test_clear_workflow_success(runner, mock_state_manager, mock_resolve_session) -> None:
    state = Mock(spec=WorkflowState)
    state.workflow_name = "test-wf"
    mock_state_manager.get_state.return_value = state

    result = runner.invoke(workflows, ["clear", "--force"])
    assert result.exit_code == 0
    assert "Cleared workflow" in result.output
    mock_state_manager.delete_state.assert_called_with("sess-123")


def test_set_workflow_lifecycle_error(
    runner, mock_loader, mock_state_manager, mock_resolve_session
) -> None:
    # Mock that no workflow is currently active
    mock_state_manager.get_state.return_value = None

    # Pipeline definitions (not WorkflowDefinition) are rejected
    from gobby.workflows.definitions import PipelineDefinition, PipelineStep

    definition = PipelineDefinition(
        name="life-wf",
        steps=[PipelineStep(id="s1", exec="echo test")],
    )
    mock_loader.load_workflow_sync.return_value = definition

    with patch("gobby.cli.workflows.get_project_path", return_value=None):
        result = runner.invoke(workflows, ["set", "life-wf"])
        assert result.exit_code == 1
        assert "is a pipeline" in result.output


def test_reload_workflows_success(runner) -> None:
    # Mock load_config - imported inside function from gobby.config.app
    with patch("gobby.config.app.load_config") as mock_conf:
        mock_conf.return_value.daemon_port = 60887

        # Mock psutil - imported inside function
        with patch("psutil.process_iter") as mock_iter:
            proc = Mock()
            proc.cmdline.return_value = ["python", "-m", "gobby", "start"]
            mock_iter.return_value = [proc]

            # Mock httpx - imported inside function
            with patch("httpx.post") as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {"status": "success"}

                result = runner.invoke(workflows, ["reload"])
                assert result.exit_code == 0
                assert "Triggered daemon workflow reload" in result.output


def test_reload_workflows_fallback(runner) -> None:
    # Mock load_config failure or process not found - imported inside function
    with patch("gobby.config.app.load_config") as mock_conf:
        mock_conf.side_effect = Exception("Config error")

        # Mock loader for fallback
        with patch("gobby.cli.workflows.get_workflow_loader") as m_loader:
            result = runner.invoke(workflows, ["reload"])
            assert result.exit_code == 0
            assert "Cleared local workflow cache" in result.output
            m_loader.return_value.clear_cache.assert_called_once()
