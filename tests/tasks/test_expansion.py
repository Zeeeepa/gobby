import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.config.app import TaskExpansionConfig
from gobby.llm import LLMService
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.tasks.context import ExpansionContext
from gobby.tasks.expansion import SubtaskSpec, TaskExpander


@pytest.fixture
def mock_task_manager():
    """Mock task manager that returns mock tasks on create."""
    manager = MagicMock(spec=LocalTaskManager)

    # Add mock db attribute for TaskDependencyManager
    manager.db = MagicMock()

    # Track created tasks
    created_tasks = []

    def create_task_side_effect(**kwargs):
        task_id = f"gt-sub{len(created_tasks) + 1}"
        task = Task(
            id=task_id,
            project_id=kwargs.get("project_id", "p1"),
            title=kwargs["title"],
            status="open",
            priority=kwargs.get("priority", 2),
            task_type=kwargs.get("task_type", "task"),
            created_at="now",
            updated_at="now",
            description=kwargs.get("description"),
            parent_task_id=kwargs.get("parent_task_id"),
        )
        created_tasks.append(task)
        return task

    manager.create_task.side_effect = create_task_side_effect
    manager._created_tasks = created_tasks  # For test inspection
    return manager


@pytest.fixture
def mock_llm_service():
    """Mock LLM service that returns structured JSON."""
    service = MagicMock(spec=LLMService)
    mock_provider = AsyncMock()
    mock_provider.generate_text.return_value = json.dumps(
        {
            "subtasks": [
                {
                    "title": "Create database schema",
                    "description": "Define tables for users and sessions",
                    "priority": 1,
                    "test_strategy": "Run migrations and verify tables exist",
                },
                {
                    "title": "Implement data access layer",
                    "description": "Create repository classes",
                    "depends_on": [0],
                    "test_strategy": "Unit tests pass",
                },
            ]
        }
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
async def test_expand_task_creates_subtasks(
    mock_task_manager, mock_llm_service, task_expansion_config, sample_task
):
    """Test that expand_task parses JSON and creates subtasks."""
    mock_task_manager.get_task.return_value = sample_task

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

        expander = TaskExpander(
            task_expansion_config, mock_llm_service, mock_task_manager
        )

        result = await expander.expand_task("t1", "Main Task")

        # Verify context gathering was called
        mock_gatherer_instance.gather_context.assert_called_once_with(
            sample_task,
            enable_web_research=False,
            enable_code_context=True,
        )

        # Verify generate_text was called
        provider = mock_llm_service.get_provider.return_value
        provider.generate_text.assert_called_once()
        call_args = provider.generate_text.call_args
        prompt = call_args.kwargs["prompt"]
        assert "src/main.py" in prompt
        assert "pytest" in prompt

        # Verify result structure
        assert "subtask_ids" in result
        assert len(result["subtask_ids"]) == 2
        assert result["subtask_count"] == 2
        assert "raw_response" in result

        # Verify tasks were created with proper parent
        assert mock_task_manager.create_task.call_count == 2
        first_call = mock_task_manager.create_task.call_args_list[0]
        assert first_call.kwargs["parent_task_id"] == "t1"
        assert first_call.kwargs["title"] == "Create database schema"


@pytest.mark.asyncio
async def test_expand_task_wires_dependencies(
    mock_task_manager, mock_llm_service, task_expansion_config, sample_task
):
    """Test that expand_task correctly wires depends_on via dependency manager."""
    mock_task_manager.get_task.return_value = sample_task

    mock_ctx = ExpansionContext(
        task=sample_task,
        related_tasks=[],
        relevant_files=[],
        file_snippets={},
        project_patterns={},
    )

    with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
        with patch("gobby.tasks.expansion.TaskDependencyManager") as MockDepManager:
            mock_gatherer_instance = MockGatherer.return_value
            mock_gatherer_instance.gather_context = AsyncMock(return_value=mock_ctx)
            mock_dep_instance = MockDepManager.return_value

            expander = TaskExpander(
                task_expansion_config, mock_llm_service, mock_task_manager
            )

            result = await expander.expand_task("t1", "Main Task")

            # Verify add_dependency was called for the second task
            # Second task has depends_on: [0], so it should call add_dependency
            mock_dep_instance.add_dependency.assert_called_once()
            call_args = mock_dep_instance.add_dependency.call_args
            assert call_args[0][0] == "gt-sub2"  # task_id
            assert call_args[0][1] == "gt-sub1"  # blocker_id
            assert call_args[0][2] == "blocks"   # dep_type


@pytest.mark.asyncio
async def test_expand_task_handles_missing_task(
    mock_task_manager, mock_llm_service, task_expansion_config
):
    """Test that expand_task works even if task is not found in DB."""
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

        expander = TaskExpander(
            task_expansion_config, mock_llm_service, mock_task_manager
        )

        await expander.expand_task("t1", "Transient Task")

        # Should still call gatherer with a transient task object
        mock_gatherer_instance.gather_context.assert_called_once()
        args = mock_gatherer_instance.gather_context.call_args[0]
        assert args[0].id == "t1"
        assert args[0].title == "Transient Task"


@pytest.mark.asyncio
async def test_expand_task_disabled(
    mock_task_manager, mock_llm_service, sample_task
):
    """Test that expand_task returns early when disabled."""
    config = TaskExpansionConfig(enabled=False)
    expander = TaskExpander(config, mock_llm_service, mock_task_manager)

    result = await expander.expand_task("t1", "Main Task")

    assert result["subtask_ids"] == []
    assert result["subtask_count"] == 0
    mock_llm_service.get_provider.assert_not_called()


class TestParseSubtasks:
    """Tests for _parse_subtasks method."""

    def test_parses_valid_json(self, mock_task_manager, mock_llm_service, task_expansion_config):
        expander = TaskExpander(task_expansion_config, mock_llm_service, mock_task_manager)

        response = json.dumps({
            "subtasks": [
                {"title": "Task 1", "priority": 1},
                {"title": "Task 2", "depends_on": [0]},
            ]
        })

        specs = expander._parse_subtasks(response)

        assert len(specs) == 2
        assert specs[0].title == "Task 1"
        assert specs[0].priority == 1
        assert specs[1].title == "Task 2"
        assert specs[1].depends_on == [0]

    def test_parses_json_in_code_block(self, mock_task_manager, mock_llm_service, task_expansion_config):
        expander = TaskExpander(task_expansion_config, mock_llm_service, mock_task_manager)

        response = """Here's the breakdown:

```json
{
  "subtasks": [
    {"title": "Task 1"}
  ]
}
```

That should work!"""

        specs = expander._parse_subtasks(response)

        assert len(specs) == 1
        assert specs[0].title == "Task 1"

    def test_returns_empty_for_invalid_json(self, mock_task_manager, mock_llm_service, task_expansion_config):
        expander = TaskExpander(task_expansion_config, mock_llm_service, mock_task_manager)

        response = "This is not valid JSON at all"

        specs = expander._parse_subtasks(response)

        assert specs == []

    def test_skips_subtasks_without_title(self, mock_task_manager, mock_llm_service, task_expansion_config):
        expander = TaskExpander(task_expansion_config, mock_llm_service, mock_task_manager)

        response = json.dumps({
            "subtasks": [
                {"title": "Valid"},
                {"description": "Missing title"},
                {"title": "Also valid"},
            ]
        })

        specs = expander._parse_subtasks(response)

        assert len(specs) == 2
        assert specs[0].title == "Valid"
        assert specs[1].title == "Also valid"


class TestExtractJson:
    """Tests for _extract_json method."""

    def test_extracts_raw_json(self, mock_task_manager, mock_llm_service, task_expansion_config):
        expander = TaskExpander(task_expansion_config, mock_llm_service, mock_task_manager)

        text = '{"subtasks": []}'
        result = expander._extract_json(text)
        assert result == '{"subtasks": []}'

    def test_extracts_json_from_markdown(self, mock_task_manager, mock_llm_service, task_expansion_config):
        expander = TaskExpander(task_expansion_config, mock_llm_service, mock_task_manager)

        text = """Some text
```json
{"subtasks": [{"title": "Test"}]}
```
More text"""

        result = expander._extract_json(text)
        assert result == '{"subtasks": [{"title": "Test"}]}'

    def test_extracts_nested_json(self, mock_task_manager, mock_llm_service, task_expansion_config):
        expander = TaskExpander(task_expansion_config, mock_llm_service, mock_task_manager)

        text = 'Prefix {"outer": {"inner": {}}} suffix'
        result = expander._extract_json(text)
        assert result == '{"outer": {"inner": {}}}'

    def test_returns_none_for_no_json(self, mock_task_manager, mock_llm_service, task_expansion_config):
        expander = TaskExpander(task_expansion_config, mock_llm_service, mock_task_manager)

        text = "No JSON here"
        result = expander._extract_json(text)
        assert result is None


class TestSubtaskSpec:
    """Tests for SubtaskSpec dataclass."""

    def test_defaults(self):
        spec = SubtaskSpec(title="Test")
        assert spec.title == "Test"
        assert spec.description is None
        assert spec.priority == 2
        assert spec.task_type == "task"
        assert spec.test_strategy is None
        assert spec.depends_on is None

    def test_all_fields(self):
        spec = SubtaskSpec(
            title="Test",
            description="Desc",
            priority=1,
            task_type="feature",
            test_strategy="Run pytest",
            depends_on=[0, 1],
        )
        assert spec.title == "Test"
        assert spec.description == "Desc"
        assert spec.priority == 1
        assert spec.task_type == "feature"
        assert spec.test_strategy == "Run pytest"
        assert spec.depends_on == [0, 1]


class TestExpansionTimeout:
    """Tests for expansion timeout handling."""

    @pytest.mark.asyncio
    async def test_expansion_timeout_returns_error(
        self, mock_task_manager, mock_llm_service, sample_task
    ):
        """Test that expansion timeout returns a proper error."""
        import asyncio

        # Config with very short timeout
        config = TaskExpansionConfig(enabled=True, timeout=0.001)

        mock_task_manager.get_task.return_value = sample_task

        with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
            mock_gatherer_instance = MockGatherer.return_value

            # Make gather_context take longer than timeout
            async def slow_gather(*args, **kwargs):
                await asyncio.sleep(1)  # 1 second, much longer than 0.001s timeout
                return ExpansionContext(
                    task=sample_task,
                    related_tasks=[],
                    relevant_files=[],
                    file_snippets={},
                    project_patterns={},
                )

            mock_gatherer_instance.gather_context = slow_gather

            expander = TaskExpander(config, mock_llm_service, mock_task_manager)

            result = await expander.expand_task("t1", "Main Task")

            # Should return timeout error
            assert "error" in result
            assert "timed out" in result["error"]
            assert result.get("timeout") is True
            assert result["subtask_ids"] == []
            assert result["subtask_count"] == 0

    @pytest.mark.asyncio
    async def test_expansion_timeout_config_default(
        self, mock_task_manager, mock_llm_service
    ):
        """Test that timeout defaults to 300 seconds."""
        config = TaskExpansionConfig(enabled=True)

        assert config.timeout == 300.0
        assert config.research_timeout == 60.0

    @pytest.mark.asyncio
    async def test_expansion_timeout_configurable(
        self, mock_task_manager, mock_llm_service
    ):
        """Test that timeout can be configured."""
        config = TaskExpansionConfig(enabled=True, timeout=600.0, research_timeout=120.0)

        assert config.timeout == 600.0
        assert config.research_timeout == 120.0
