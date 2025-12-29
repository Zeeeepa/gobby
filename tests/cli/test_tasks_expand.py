import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from click.testing import CliRunner
from gobby.cli.tasks import tasks
from gobby.storage.tasks import LocalTaskManager, Task


@pytest.fixture
def mock_task_manager():
    manager = MagicMock(spec=LocalTaskManager)
    manager.db = MagicMock()
    return manager


@pytest.fixture
def mock_expander():
    expander = MagicMock()
    expander.expand_task = AsyncMock()
    return expander


def test_expand_command_with_flags(mock_task_manager, mock_expander):
    """Test expand command passes flags correctly."""
    runner = CliRunner()

    with (
        patch("gobby.cli.tasks.get_task_manager", return_value=mock_task_manager),
        patch(
            "gobby.cli.tasks.resolve_task_id",
            return_value=MagicMock(id="t1", project_id="p1", title="Task 1"),
        ),
        patch("gobby.cli.tasks.load_config") as mock_config,
        patch("gobby.llm.LLMService"),
        patch("gobby.tasks.expansion.TaskExpander", return_value=mock_expander),
    ):
        # Enable expansion in config
        mock_config.return_value.task_expansion.enabled = True

        # Mock successful expansion
        mock_expander.expand_task.return_value = {
            "complexity_analysis": {"score": 5},
            "phases": [{"subtasks": [{"title": "Sub 1"}]}],
        }

        # Test with explicit flags
        result = runner.invoke(tasks, ["expand", "t1", "--web-research", "--no-code-context"])

        assert result.exit_code == 0

        # Verify call arguments
        # context argument is None by default
        mock_expander.expand_task.assert_called_with(
            task_id="t1",
            title="Task 1",
            description=None,  # Description comes from resolved task mocks
            context=None,
            enable_web_research=True,
            enable_code_context=False,
        )
