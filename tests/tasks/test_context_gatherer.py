import pytest
from unittest.mock import MagicMock, patch
from gobby.tasks.context import ExpansionContextGatherer
from gobby.storage.tasks import Task


@pytest.fixture
def mock_task_manager():
    return MagicMock()


@pytest.fixture
def sample_task():
    return Task(
        id="t1",
        project_id="p1",
        title="Implement login",
        status="open",
        priority=2,
        task_type="feature",
        created_at="now",
        updated_at="now",
        description="Implement login using auth.py",
    )


@pytest.mark.asyncio
async def test_gather_context_basic(mock_task_manager, sample_task):
    gatherer = ExpansionContextGatherer(mock_task_manager)

    # Mock finding related tasks
    mock_task_manager.list_tasks.return_value = [sample_task]

    # Mock filesystem operations
    with patch("gobby.tasks.context.find_project_root") as mock_root:
        mock_root.return_value = None  # Simulate no project root for simplicity first

        context = await gatherer.gather_context(sample_task)

        assert context.task.id == "t1"
        assert context.related_tasks == []  # Should be empty as we filter out same task
        assert context.relevant_files == []
        assert context.project_patterns == {}


@pytest.mark.asyncio
async def test_find_relevant_files_in_description(mock_task_manager, sample_task):
    gatherer = ExpansionContextGatherer(mock_task_manager)

    with patch("gobby.tasks.context.find_project_root") as mock_root:
        # Mock root path behavior
        mock_path = MagicMock()
        mock_root.return_value = mock_path

        # When checking relevant files, we look for "auth.py"
        # The code checks path / fname exists() and is_file()
        # "auth.py" in description

        # We need to mock the / operator and exists()
        # This is tricky with pathlib mocks, so we rely on MagicMock behavior
        # mock_path / "auth.py" -> another mock
        file_mock = MagicMock()
        file_mock.exists.return_value = True
        file_mock.is_file.return_value = True
        file_mock.relative_to.return_value = "auth.py"

        mock_path.__truediv__.side_effect = (
            lambda x: file_mock if x == "auth.py" else MagicMock(exists=lambda: False)
        )

        files = await gatherer._find_relevant_files(sample_task)
        assert "auth.py" in files
