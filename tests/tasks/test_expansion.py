from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.config.app import TaskExpansionConfig
from gobby.llm import LLMService
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.tasks.context import ExpansionContext
from gobby.tasks.expansion import TaskExpander


@pytest.fixture
def mock_task_manager():
    return MagicMock(spec=LocalTaskManager)


@pytest.fixture
def mock_llm_service():
    service = MagicMock(spec=LLMService)
    # Mock get_provider to return a mock provider
    mock_provider = AsyncMock()
    mock_provider.generate_text.return_value = (
        '{"subtasks": [{"title": "Sub 1", "description": "Desc 1"}]}'
    )
    service.get_provider.return_value = mock_provider
    return service


@pytest.fixture
def task_expansion_config():
    return TaskExpansionConfig(
        enabled=True,
        provider="test-provider",
        model="test-model",
    )


@pytest.fixture
def sample_task():
    return Task(
        id="t1",
        project_id="p1",
        title="Main Task",
        status="open",
        priority=2,
        task_type="feature",
        created_at="now",
        updated_at="now",
        description="Do the thing",
    )


@pytest.mark.asyncio
async def test_expand_task_calls_gatherer(
    mock_task_manager, mock_llm_service, task_expansion_config, sample_task
):
    """Test that expand_task calls context gatherer and includes it in prompt."""
    expander = TaskExpander(task_expansion_config, mock_llm_service, mock_task_manager)

    mock_task_manager.get_task.return_value = sample_task

    # Mock ExpansionContextGatherer.gather_context
    mock_ctx = ExpansionContext(
        task=sample_task,
        related_tasks=[],
        relevant_files=["src/main.py"],
        file_snippets={},
        project_patterns={"test": "pytest"},
    )

    with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
        mock_gatherer_instance = MockGatherer.return_value
        mock_gatherer_instance.gather_context = AsyncMock(return_value=mock_ctx)

        # We need to re-init because we patched the class used in init
        expander = TaskExpander(task_expansion_config, mock_llm_service, mock_task_manager)

        await expander.expand_task("t1", "Main Task")

        mock_gatherer_instance.gather_context.assert_called_once_with(sample_task)

        # Verify LLM call arguments contain context
        provider = mock_llm_service.get_provider.return_value
        call_args = provider.generate_text.call_args
        prompt = call_args.kwargs["prompt"]

        assert "src/main.py" in prompt
        assert "pytest" in prompt


@pytest.mark.asyncio
async def test_expand_task_handles_missing_task(
    mock_task_manager, mock_llm_service, task_expansion_config
):
    """Test that expand_task works even if task is not found in DB (fallback)."""
    expander = TaskExpander(task_expansion_config, mock_llm_service, mock_task_manager)
    mock_task_manager.get_task.return_value = None

    with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
        mock_gatherer_instance = MockGatherer.return_value
        mock_gatherer_instance.gather_context = AsyncMock(
            return_value=ExpansionContext(
                task=MagicMock(),
                related_tasks=[],
                relevant_files=[],
                file_snippets={},
                project_patterns={},
            )
        )

        # Re-init
        expander = TaskExpander(task_expansion_config, mock_llm_service, mock_task_manager)

        await expander.expand_task("t1", "Transient Task")

        # Should still call gatherer with a transient task object
        mock_gatherer_instance.gather_context.assert_called_once()
        args = mock_gatherer_instance.gather_context.call_args[0]
        assert args[0].id == "t1"
        assert args[0].title == "Transient Task"
