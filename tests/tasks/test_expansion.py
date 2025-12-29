from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.config.app import TaskExpansionConfig
from gobby.llm import LLMService
from gobby.llm.claude import ClaudeLLMProvider, MCPToolResult, ToolCall
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.tasks.context import ExpansionContext
from gobby.tasks.expansion import CREATE_TASK_TOOL, TaskExpander


@pytest.fixture
def mock_task_manager():
    return MagicMock(spec=LocalTaskManager)


@pytest.fixture
def mock_llm_service():
    """Mock LLM service with non-Claude provider (triggers fallback path)."""
    service = MagicMock(spec=LLMService)
    # Mock get_provider to return a mock provider (not ClaudeLLMProvider)
    mock_provider = AsyncMock()
    mock_provider.generate_text.return_value = "Fallback expansion response"
    service.get_provider.return_value = mock_provider
    return service


@pytest.fixture
def mock_claude_llm_service():
    """Mock LLM service with Claude provider (uses tool-based expansion)."""
    service = MagicMock(spec=LLMService)
    # Mock get_provider to return a mock ClaudeLLMProvider
    mock_provider = MagicMock(spec=ClaudeLLMProvider)
    mock_provider.generate_with_mcp_tools = AsyncMock(
        return_value=MCPToolResult(
            text="Created 2 subtasks for the task.",
            tool_calls=[
                ToolCall(
                    tool_name=CREATE_TASK_TOOL,
                    server_name="gobby-tasks",
                    arguments={"title": "Sub 1", "parent_task_id": "t1"},
                    result='{"id": "gt-sub1", "title": "Sub 1"}',
                ),
                ToolCall(
                    tool_name=CREATE_TASK_TOOL,
                    server_name="gobby-tasks",
                    arguments={"title": "Sub 2", "parent_task_id": "t1", "blocks": ["gt-sub1"]},
                    result='{"id": "gt-sub2", "title": "Sub 2"}',
                ),
            ],
        )
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
async def test_expand_task_with_claude_provider(
    mock_task_manager, mock_claude_llm_service, task_expansion_config, sample_task
):
    """Test that expand_task uses tool-based expansion with Claude provider."""
    expander = TaskExpander(task_expansion_config, mock_claude_llm_service, mock_task_manager)

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
        expander = TaskExpander(
            task_expansion_config, mock_claude_llm_service, mock_task_manager
        )

        result = await expander.expand_task("t1", "Main Task")

        mock_gatherer_instance.gather_context.assert_called_once_with(
            sample_task,
            enable_web_research=False,
            enable_code_context=True,
        )

        # Verify generate_with_mcp_tools was called
        provider = mock_claude_llm_service.get_provider.return_value
        provider.generate_with_mcp_tools.assert_called_once()
        call_args = provider.generate_with_mcp_tools.call_args
        prompt = call_args.kwargs["prompt"]

        assert "src/main.py" in prompt
        assert "pytest" in prompt

        # Verify result structure (tool-based format)
        assert "subtask_ids" in result
        assert result["subtask_ids"] == ["gt-sub1", "gt-sub2"]
        assert result["tool_calls"] == 2
        assert "Created 2 subtasks" in result["text"]


@pytest.mark.asyncio
async def test_expand_task_fallback_for_non_claude_provider(
    mock_task_manager, mock_llm_service, task_expansion_config, sample_task
):
    """Test that expand_task falls back to text generation for non-Claude providers."""
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

        result = await expander.expand_task("t1", "Main Task")

        # Verify fallback path was used
        assert result["fallback"] is True
        assert result["subtask_ids"] == []
        assert result["tool_calls"] == 0
        assert "Fallback expansion response" in result["text"]


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
