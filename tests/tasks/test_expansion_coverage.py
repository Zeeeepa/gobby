"""
Comprehensive unit tests for gobby.tasks.expansion module.

This module provides additional test coverage focusing on:
1. Task expansion methods with various edge cases
2. LLM integration mocking
3. Error handling paths
4. Pattern criteria injection
5. Precise criteria generation
6. Context saving and subtask creation
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.config.app import (
    ProjectVerificationConfig,
    TaskExpansionConfig,
)
from gobby.llm import LLMService
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.tasks.context import ExpansionContext
from gobby.tasks.expansion import SubtaskSpec, TaskExpander

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_task_manager():
    """Mock task manager that returns mock tasks on create."""
    manager = MagicMock(spec=LocalTaskManager)
    manager.db = MagicMock()
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
    manager._created_tasks = created_tasks
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
                    "title": "First task",
                    "description": "Do the first thing",
                    "priority": 1,
                    "test_strategy": "Run {unit_tests} to verify",
                },
                {
                    "title": "Second task",
                    "description": "Do the second thing",
                    "depends_on": [0],
                },
            ]
        }
    )
    service.get_provider.return_value = mock_provider
    return service


@pytest.fixture
def task_expansion_config():
    """Standard task expansion config."""
    return TaskExpansionConfig(
        enabled=True,
        provider="test-provider",
        model="test-model",
    )


@pytest.fixture
def sample_task():
    """Sample task for testing."""
    return Task(
        id="t1",
        project_id="p1",
        title="Main Task",
        status="open",
        priority=2,
        task_type="feature",
        created_at="now",
        updated_at="now",
        description="Implement using strangler-fig pattern",
        labels=["strangler-fig"],
    )


@pytest.fixture
def verification_config():
    """Mock verification config."""
    return ProjectVerificationConfig(
        unit_tests="pytest",
        type_check="mypy src/",
        lint="ruff check .",
    )


# =============================================================================
# TaskExpander Initialization Tests
# =============================================================================


class TestTaskExpanderInit:
    """Tests for TaskExpander initialization."""

    def test_init_with_verification_config(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test initialization with explicit verification config."""
        config = TaskExpansionConfig(enabled=True)

        expander = TaskExpander(
            config=config,
            llm_service=mock_llm_service,
            task_manager=mock_task_manager,
            verification_config=verification_config,
        )

        assert expander.criteria_injector is not None
        assert expander.criteria_injector.verification_config == verification_config

    def test_init_without_verification_config(self, mock_task_manager, mock_llm_service):
        """Test initialization without verification config (gets from project)."""
        config = TaskExpansionConfig(enabled=True)

        with patch("gobby.tasks.expansion.get_verification_config", return_value=None):
            expander = TaskExpander(
                config=config,
                llm_service=mock_llm_service,
                task_manager=mock_task_manager,
            )

        assert expander.criteria_injector is not None

    def test_init_with_mcp_manager(self, mock_task_manager, mock_llm_service):
        """Test initialization with MCP manager."""
        config = TaskExpansionConfig(enabled=True)
        mock_mcp = MagicMock()

        expander = TaskExpander(
            config=config,
            llm_service=mock_llm_service,
            task_manager=mock_task_manager,
            mcp_manager=mock_mcp,
        )

        assert expander.mcp_manager == mock_mcp


# =============================================================================
# Pattern Criteria Injection Tests
# =============================================================================


class TestPatternCriteriaInjection:
    """Tests for pattern criteria injection during expansion."""

    @pytest.mark.asyncio
    async def test_pattern_criteria_injected_from_labels(
        self, mock_task_manager, mock_llm_service, sample_task, verification_config
    ):
        """Test that pattern criteria are injected based on task labels."""
        config = TaskExpansionConfig(enabled=True)
        mock_task_manager.get_task.return_value = sample_task

        mock_ctx = ExpansionContext(
            task=sample_task,
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
            verification_commands={"unit_tests": "pytest"},
        )

        with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
            mock_gatherer = MockGatherer.return_value
            mock_gatherer.gather_context = AsyncMock(return_value=mock_ctx)

            expander = TaskExpander(
                config=config,
                llm_service=mock_llm_service,
                task_manager=mock_task_manager,
                verification_config=verification_config,
            )

            await expander.expand_task("t1", "Main Task")

            # Verify LLM was called (pattern criteria would be in the prompt)
            provider = mock_llm_service.get_provider.return_value
            provider.generate_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_pattern_criteria_from_description_keywords(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test pattern detection from description keywords."""
        config = TaskExpansionConfig(enabled=True)

        # Task with pattern keyword in description but no labels
        task = Task(
            id="t1",
            project_id="p1",
            title="Refactor code",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            description="Refactor this module using TDD approach",
            labels=[],
        )
        mock_task_manager.get_task.return_value = task

        mock_ctx = ExpansionContext(
            task=task,
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
        )

        with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
            mock_gatherer = MockGatherer.return_value
            mock_gatherer.gather_context = AsyncMock(return_value=mock_ctx)

            expander = TaskExpander(
                config=config,
                llm_service=mock_llm_service,
                task_manager=mock_task_manager,
                verification_config=verification_config,
            )

            result = await expander.expand_task("t1", "Refactor code")

            assert "subtask_ids" in result

    @pytest.mark.asyncio
    async def test_combined_context_with_user_instructions(
        self, mock_task_manager, mock_llm_service, sample_task, verification_config
    ):
        """Test that user context and pattern criteria are combined."""
        config = TaskExpansionConfig(enabled=True)
        mock_task_manager.get_task.return_value = sample_task

        mock_ctx = ExpansionContext(
            task=sample_task,
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
        )

        with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
            mock_gatherer = MockGatherer.return_value
            mock_gatherer.gather_context = AsyncMock(return_value=mock_ctx)

            expander = TaskExpander(
                config=config,
                llm_service=mock_llm_service,
                task_manager=mock_task_manager,
                verification_config=verification_config,
            )

            # Pass additional context
            result = await expander.expand_task(
                "t1",
                "Main Task",
                context="Focus on performance optimization",
            )

            # Verify generate_text was called with combined context
            provider = mock_llm_service.get_provider.return_value
            call_args = provider.generate_text.call_args
            prompt = call_args.kwargs["prompt"]
            assert "performance optimization" in prompt.lower()
            assert isinstance(result, dict)


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in task expansion."""

    @pytest.mark.asyncio
    async def test_llm_exception_handled(self, mock_task_manager, mock_llm_service, sample_task):
        """Test that LLM exceptions are handled gracefully."""
        config = TaskExpansionConfig(enabled=True)
        mock_task_manager.get_task.return_value = sample_task

        # Make LLM raise an exception
        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.side_effect = RuntimeError("LLM API error")

        mock_ctx = ExpansionContext(
            task=sample_task,
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
        )

        with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
            mock_gatherer = MockGatherer.return_value
            mock_gatherer.gather_context = AsyncMock(return_value=mock_ctx)

            expander = TaskExpander(
                config=config,
                llm_service=mock_llm_service,
                task_manager=mock_task_manager,
            )

            result = await expander.expand_task("t1", "Main Task")

            assert "error" in result
            assert "LLM API error" in result["error"]
            assert result["subtask_ids"] == []
            assert result["subtask_count"] == 0

    @pytest.mark.asyncio
    async def test_llm_exception_without_message(
        self, mock_task_manager, mock_llm_service, sample_task
    ):
        """Test exception handling when exception has no message."""
        config = TaskExpansionConfig(enabled=True)
        mock_task_manager.get_task.return_value = sample_task

        # Exception with empty message
        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.side_effect = ValueError()

        mock_ctx = ExpansionContext(
            task=sample_task,
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
        )

        with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
            mock_gatherer = MockGatherer.return_value
            mock_gatherer.gather_context = AsyncMock(return_value=mock_ctx)

            expander = TaskExpander(
                config=config,
                llm_service=mock_llm_service,
                task_manager=mock_task_manager,
            )

            result = await expander.expand_task("t1", "Main Task")

            assert "error" in result
            assert "ValueError" in result["error"]

    @pytest.mark.asyncio
    async def test_no_subtasks_returns_warning(
        self, mock_task_manager, mock_llm_service, sample_task
    ):
        """Test that empty subtask response returns appropriate warning."""
        config = TaskExpansionConfig(enabled=True)
        mock_task_manager.get_task.return_value = sample_task

        # LLM returns empty subtasks
        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.return_value = json.dumps({"subtasks": []})

        mock_ctx = ExpansionContext(
            task=sample_task,
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
        )

        with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
            mock_gatherer = MockGatherer.return_value
            mock_gatherer.gather_context = AsyncMock(return_value=mock_ctx)

            expander = TaskExpander(
                config=config,
                llm_service=mock_llm_service,
                task_manager=mock_task_manager,
            )

            result = await expander.expand_task("t1", "Main Task")

            assert result["subtask_ids"] == []
            assert result["subtask_count"] == 0
            assert "No subtasks found" in result.get("error", "")


# =============================================================================
# Parse Subtasks Edge Cases
# =============================================================================


class TestParseSubtasksEdgeCases:
    """Edge case tests for _parse_subtasks method."""

    def test_subtasks_not_a_list(self, mock_task_manager, mock_llm_service):
        """Test handling when subtasks is not a list."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(config, mock_llm_service, mock_task_manager)

        response = json.dumps({"subtasks": "not a list"})
        specs = expander._parse_subtasks(response)

        assert specs == []

    def test_subtask_item_not_dict(self, mock_task_manager, mock_llm_service):
        """Test handling when subtask item is not a dict."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(config, mock_llm_service, mock_task_manager)

        response = json.dumps({"subtasks": [{"title": "Valid"}, "not a dict", 123]})
        specs = expander._parse_subtasks(response)

        assert len(specs) == 1
        assert specs[0].title == "Valid"

    def test_parse_all_subtask_fields(self, mock_task_manager, mock_llm_service):
        """Test that all subtask fields are parsed correctly."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(config, mock_llm_service, mock_task_manager)

        response = json.dumps(
            {
                "subtasks": [
                    {
                        "title": "Full Subtask",
                        "description": "Complete description",
                        "priority": 1,
                        "task_type": "feature",
                        "test_strategy": "Run tests",
                        "depends_on": [0, 1],
                    }
                ]
            }
        )
        specs = expander._parse_subtasks(response)

        assert len(specs) == 1
        assert specs[0].title == "Full Subtask"
        assert specs[0].description == "Complete description"
        assert specs[0].priority == 1
        assert specs[0].task_type == "feature"
        assert specs[0].test_strategy == "Run tests"
        assert specs[0].depends_on == [0, 1]

    def test_parse_malformed_json_response(self, mock_task_manager, mock_llm_service):
        """Test handling of malformed JSON in response."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(config, mock_llm_service, mock_task_manager)

        response = '{"subtasks": [{"title": "Test"'  # Incomplete JSON
        specs = expander._parse_subtasks(response)

        assert specs == []

    def test_parse_json_decode_error(self, mock_task_manager, mock_llm_service):
        """Test JSONDecodeError is properly handled (lines 254-256)."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(config, mock_llm_service, mock_task_manager)

        # Valid looking JSON block but actually invalid
        response = """```json
{"subtasks": [{"title": "Test", invalid_syntax}]}
```"""
        specs = expander._parse_subtasks(response)

        assert specs == []


# =============================================================================
# Create Subtasks Tests
# =============================================================================


class TestCreateSubtasks:
    """Tests for _create_subtasks method."""

    @pytest.mark.asyncio
    async def test_create_subtasks_with_test_strategy(self, mock_task_manager, mock_llm_service):
        """Test that test strategy is added to description."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(config, mock_llm_service, mock_task_manager)

        specs = [
            SubtaskSpec(
                title="Task with strategy",
                description="Original description",
                test_strategy="Run pytest",
            )
        ]

        subtask_ids = await expander._create_subtasks(
            parent_task_id="parent-1",
            project_id="p1",
            subtask_specs=specs,
        )

        assert len(subtask_ids) == 1
        call_kwargs = mock_task_manager.create_task.call_args.kwargs
        assert "**Test Strategy:**" in call_kwargs["description"]

    @pytest.mark.asyncio
    async def test_create_subtasks_strategy_without_description(
        self, mock_task_manager, mock_llm_service
    ):
        """Test test strategy when there's no description."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(config, mock_llm_service, mock_task_manager)

        specs = [
            SubtaskSpec(
                title="Strategy only",
                description=None,
                test_strategy="Verify output",
            )
        ]

        subtask_ids = await expander._create_subtasks(
            parent_task_id="parent-1",
            project_id="p1",
            subtask_specs=specs,
        )

        assert len(subtask_ids) == 1
        call_kwargs = mock_task_manager.create_task.call_args.kwargs
        assert "**Test Strategy:**" in call_kwargs["description"]

    @pytest.mark.asyncio
    async def test_create_subtasks_criteria_only_no_description(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test that description is set from precise criteria when no original description (line 338)."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(
            config,
            mock_llm_service,
            mock_task_manager,
            verification_config=verification_config,
        )

        # Subtask with no description and no test strategy
        specs = [
            SubtaskSpec(
                title="Task without description",
                description=None,
                test_strategy=None,
            )
        ]

        # Context with verification commands to generate criteria
        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
            verification_commands={"unit_tests": "pytest", "type_check": "mypy src/"},
        )

        subtask_ids = await expander._create_subtasks(
            parent_task_id="parent-1",
            project_id="p1",
            subtask_specs=specs,
            expansion_context=context,
        )

        assert len(subtask_ids) == 1
        call_kwargs = mock_task_manager.create_task.call_args.kwargs
        # Description should come from criteria only
        assert "## Verification" in call_kwargs["description"]

    @pytest.mark.asyncio
    async def test_create_subtasks_with_precise_criteria(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test that precise criteria are generated from context."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(
            config,
            mock_llm_service,
            mock_task_manager,
            verification_config=verification_config,
        )

        specs = [
            SubtaskSpec(
                title="Task with file",
                description="Modify src/main.py",
            )
        ]

        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=["src/main.py"],
            file_snippets={},
            project_patterns={},
            verification_commands={"unit_tests": "pytest", "lint": "ruff check ."},
        )

        subtask_ids = await expander._create_subtasks(
            parent_task_id="parent-1",
            project_id="p1",
            subtask_specs=specs,
            expansion_context=context,
        )

        assert len(subtask_ids) == 1

    @pytest.mark.asyncio
    async def test_create_subtasks_with_invalid_dependency_index(
        self, mock_task_manager, mock_llm_service
    ):
        """Test handling of invalid dependency indices."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(config, mock_llm_service, mock_task_manager)

        specs = [
            SubtaskSpec(title="First"),
            SubtaskSpec(title="Second", depends_on=[5]),  # Invalid index
        ]

        with patch("gobby.tasks.expansion.TaskDependencyManager") as MockDepMgr:
            mock_dep = MockDepMgr.return_value

            await expander._create_subtasks(
                parent_task_id="parent-1",
                project_id="p1",
                subtask_specs=specs,
            )

            # Dependency should not be added for invalid index
            mock_dep.add_dependency.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_subtasks_dependency_manager_failure(
        self, mock_task_manager, mock_llm_service
    ):
        """Test handling when dependency manager fails."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(config, mock_llm_service, mock_task_manager)

        specs = [
            SubtaskSpec(title="First"),
            SubtaskSpec(title="Second", depends_on=[0]),
        ]

        with patch("gobby.tasks.expansion.TaskDependencyManager") as MockDepMgr:
            mock_dep = MockDepMgr.return_value
            mock_dep.add_dependency.side_effect = Exception("DB error")

            # Should not raise, just log warning
            subtask_ids = await expander._create_subtasks(
                parent_task_id="parent-1",
                project_id="p1",
                subtask_specs=specs,
            )

            assert len(subtask_ids) == 2


# =============================================================================
# Save Expansion Context Tests
# =============================================================================


class TestSaveExpansionContext:
    """Tests for _save_expansion_context method."""

    def test_save_context_with_web_research(self, mock_task_manager, mock_llm_service):
        """Test saving context with web research data."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(config, mock_llm_service, mock_task_manager)

        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=["file.py"],
            file_snippets={},
            project_patterns={},
            web_research=[{"query": "test", "results": ["result1"]}],
            agent_findings="Found interesting patterns",
        )

        expander._save_expansion_context("task-1", context)

        mock_task_manager.update_task.assert_called_once()
        call_kwargs = mock_task_manager.update_task.call_args.kwargs
        context_json = json.loads(call_kwargs["expansion_context"])
        assert "web_research" in context_json
        assert "agent_findings" in context_json

    def test_save_context_empty_context(self, mock_task_manager, mock_llm_service):
        """Test that empty context doesn't trigger update."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(config, mock_llm_service, mock_task_manager)

        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
        )

        expander._save_expansion_context("task-1", context)

        mock_task_manager.update_task.assert_not_called()

    def test_save_context_exception_handled(self, mock_task_manager, mock_llm_service):
        """Test that exceptions during save are handled."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(config, mock_llm_service, mock_task_manager)

        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=["file.py"],
            file_snippets={},
            project_patterns={},
        )

        mock_task_manager.update_task.side_effect = Exception("DB error")

        # Should not raise
        expander._save_expansion_context("task-1", context)


# =============================================================================
# Generate Precise Criteria Tests
# =============================================================================


class TestGeneratePreciseCriteria:
    """Tests for _generate_precise_criteria method."""

    @pytest.mark.asyncio
    async def test_generate_criteria_with_pattern_labels(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test criteria generation with pattern labels."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(
            config,
            mock_llm_service,
            mock_task_manager,
            verification_config=verification_config,
        )

        spec = SubtaskSpec(title="Refactor module")
        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
            verification_commands={"unit_tests": "pytest"},
        )

        criteria = await expander._generate_precise_criteria(
            spec=spec,
            context=context,
            parent_labels=["refactoring"],
        )

        # Criteria should be a string (can be empty if no pattern matched)
        assert isinstance(criteria, str)

    @pytest.mark.asyncio
    async def test_generate_criteria_with_test_strategy_substitution(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test that verification commands are substituted in test strategy."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(
            config,
            mock_llm_service,
            mock_task_manager,
            verification_config=verification_config,
        )

        spec = SubtaskSpec(
            title="Task",
            test_strategy="Run {unit_tests} to verify",
        )
        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
            verification_commands={"unit_tests": "pytest"},
        )

        criteria = await expander._generate_precise_criteria(
            spec=spec,
            context=context,
            parent_labels=[],
        )

        assert "## Test Strategy" in criteria
        assert "`pytest`" in criteria

    @pytest.mark.asyncio
    async def test_generate_criteria_with_relevant_files(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test file requirements criteria when files match description."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(
            config,
            mock_llm_service,
            mock_task_manager,
            verification_config=verification_config,
        )

        spec = SubtaskSpec(
            title="Update main.py",
            description="Modify src/main.py to add feature",
        )
        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=["src/main.py", "src/utils.py"],
            file_snippets={},
            project_patterns={},
        )

        criteria = await expander._generate_precise_criteria(
            spec=spec,
            context=context,
            parent_labels=[],
        )

        assert "## File Requirements" in criteria
        assert "`src/main.py`" in criteria

    @pytest.mark.asyncio
    async def test_generate_criteria_with_function_signatures(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test function integrity criteria when signatures match."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(
            config,
            mock_llm_service,
            mock_task_manager,
            verification_config=verification_config,
        )

        spec = SubtaskSpec(
            title="Update expand_task",
            description="Modify the expand_task function",
        )
        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
            function_signatures={
                "src/expansion.py": [
                    "async def expand_task(self, task_id: str) -> dict",
                    "def _parse_subtasks(self, response: str) -> list",
                ]
            },
        )

        criteria = await expander._generate_precise_criteria(
            spec=spec,
            context=context,
            parent_labels=[],
        )

        assert "## Function Integrity" in criteria
        assert "`expand_task`" in criteria

    @pytest.mark.asyncio
    async def test_generate_criteria_with_verification_commands(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test verification criteria from project commands."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(
            config,
            mock_llm_service,
            mock_task_manager,
            verification_config=verification_config,
        )

        spec = SubtaskSpec(title="Add feature")
        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
            verification_commands={
                "unit_tests": "pytest",
                "type_check": "mypy src/",
                "lint": "ruff check .",
            },
        )

        criteria = await expander._generate_precise_criteria(
            spec=spec,
            context=context,
            parent_labels=[],
        )

        assert "## Verification" in criteria
        assert "`pytest` passes" in criteria
        assert "`mypy src/` passes" in criteria
        assert "`ruff check .` passes" in criteria

    @pytest.mark.asyncio
    async def test_generate_criteria_with_async_function_signature(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test function signature parsing for async functions."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(
            config,
            mock_llm_service,
            mock_task_manager,
            verification_config=verification_config,
        )

        spec = SubtaskSpec(
            title="Update gather_context",
            description="Modify gather_context method",
        )
        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
            function_signatures={
                "src/context.py": ["async def gather_context(self, task: Task) -> Context"]
            },
        )

        criteria = await expander._generate_precise_criteria(
            spec=spec,
            context=context,
            parent_labels=[],
        )

        assert "gather_context" in criteria

    @pytest.mark.asyncio
    async def test_generate_criteria_empty_signature(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test handling of empty signature strings."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(
            config,
            mock_llm_service,
            mock_task_manager,
            verification_config=verification_config,
        )

        spec = SubtaskSpec(
            title="Update something",
            description="Some description",
        )
        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
            function_signatures={"src/file.py": ["", None, "def valid_func()"]},
        )

        # Should not raise
        criteria = await expander._generate_precise_criteria(
            spec=spec,
            context=context,
            parent_labels=[],
        )

        assert isinstance(criteria, str)

    @pytest.mark.asyncio
    async def test_generate_criteria_fallback_function_name_extraction(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test function name extraction fallback for unusual signatures."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(
            config,
            mock_llm_service,
            mock_task_manager,
            verification_config=verification_config,
        )

        spec = SubtaskSpec(
            title="Update myfunction",
            description="Change myfunction behavior",
        )
        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
            function_signatures={"src/file.py": ["myfunction(arg1, arg2)"]},  # No def keyword
        )

        criteria = await expander._generate_precise_criteria(
            spec=spec,
            context=context,
            parent_labels=[],
        )

        # Should still extract function name using fallback
        assert "myfunction" in criteria

    @pytest.mark.asyncio
    async def test_generate_criteria_split_fallback_with_paren(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test function name extraction using split logic for sig with paren (lines 483-486)."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(
            config,
            mock_llm_service,
            mock_task_manager,
            verification_config=verification_config,
        )

        spec = SubtaskSpec(
            title="Update @decorated process",
            description="Modify process function",
        )
        # Signature that doesn't match regex but has parens - triggers split fallback
        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
            function_signatures={
                # This pattern won't match the regex patterns but has parentheses
                "src/file.py": ["@decorator process(x)"]
            },
        )

        criteria = await expander._generate_precise_criteria(
            spec=spec,
            context=context,
            parent_labels=[],
        )

        assert "process" in criteria

    @pytest.mark.asyncio
    async def test_generate_criteria_split_fallback_no_paren(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test function name extraction for sig without paren (lines 485-486 else branch)."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(
            config,
            mock_llm_service,
            mock_task_manager,
            verification_config=verification_config,
        )

        spec = SubtaskSpec(
            title="Update handler",
            description="Modify handler logic",
        )
        # Signature without parentheses - uses split()[-1]
        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
            function_signatures={"src/file.py": ["property handler"]},  # No parens
        )

        criteria = await expander._generate_precise_criteria(
            spec=spec,
            context=context,
            parent_labels=[],
        )

        assert "handler" in criteria

    @pytest.mark.asyncio
    async def test_generate_criteria_split_fallback_index_error(
        self, mock_task_manager, mock_llm_service, verification_config
    ):
        """Test that IndexError in split fallback is caught (lines 487-488)."""
        config = TaskExpansionConfig(enabled=True)
        expander = TaskExpander(
            config,
            mock_llm_service,
            mock_task_manager,
            verification_config=verification_config,
        )

        spec = SubtaskSpec(
            title="Update thing",
            description="Modify thing",
        )
        # Edge case: signature that could cause IndexError in split
        context = ExpansionContext(
            task=MagicMock(),
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
            function_signatures={"src/file.py": ["()"]},  # Edge case - empty before paren
        )

        # Should not raise
        criteria = await expander._generate_precise_criteria(
            spec=spec,
            context=context,
            parent_labels=[],
        )

        assert isinstance(criteria, str)


# =============================================================================
# Full Expansion Flow Tests
# =============================================================================


class TestFullExpansionFlow:
    """Integration-style tests for the full expansion flow."""

    @pytest.mark.asyncio
    async def test_expansion_with_web_research_enabled(
        self, mock_task_manager, mock_llm_service, sample_task
    ):
        """Test expansion with web research enabled."""
        config = TaskExpansionConfig(enabled=True)
        mock_task_manager.get_task.return_value = sample_task

        mock_ctx = ExpansionContext(
            task=sample_task,
            related_tasks=[],
            relevant_files=["src/file.py"],
            file_snippets={"src/file.py": "content"},
            project_patterns={"tests": "tests/"},
        )

        with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
            mock_gatherer = MockGatherer.return_value
            mock_gatherer.gather_context = AsyncMock(return_value=mock_ctx)

            expander = TaskExpander(config, mock_llm_service, mock_task_manager)

            await expander.expand_task(
                "t1",
                "Main Task",
                enable_web_research=True,
            )

            # Verify context gathering was called with web research enabled
            mock_gatherer.gather_context.assert_called_once_with(
                sample_task,
                enable_web_research=True,
                enable_code_context=True,
            )

    @pytest.mark.asyncio
    async def test_expansion_with_code_context_disabled(
        self, mock_task_manager, mock_llm_service, sample_task
    ):
        """Test expansion with code context disabled."""
        config = TaskExpansionConfig(enabled=True)
        mock_task_manager.get_task.return_value = sample_task

        mock_ctx = ExpansionContext(
            task=sample_task,
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
        )

        with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
            mock_gatherer = MockGatherer.return_value
            mock_gatherer.gather_context = AsyncMock(return_value=mock_ctx)

            expander = TaskExpander(config, mock_llm_service, mock_task_manager)

            await expander.expand_task(
                "t1",
                "Main Task",
                enable_code_context=False,
            )

            mock_gatherer.gather_context.assert_called_once_with(
                sample_task,
                enable_web_research=False,
                enable_code_context=False,
            )

    @pytest.mark.asyncio
    async def test_expansion_with_description(
        self, mock_task_manager, mock_llm_service, sample_task
    ):
        """Test expansion with explicit description parameter."""
        config = TaskExpansionConfig(enabled=True)
        mock_task_manager.get_task.return_value = sample_task

        mock_ctx = ExpansionContext(
            task=sample_task,
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
        )

        with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
            mock_gatherer = MockGatherer.return_value
            mock_gatherer.gather_context = AsyncMock(return_value=mock_ctx)

            expander = TaskExpander(config, mock_llm_service, mock_task_manager)

            result = await expander.expand_task(
                "t1",
                "Main Task",
                description="Custom description for expansion",
            )

            # Should successfully complete
            assert "subtask_ids" in result


# =============================================================================
# TDD Mode Tests
# =============================================================================


class TestTddModeHandling:
    """Additional tests for TDD mode handling."""

    @pytest.mark.asyncio
    async def test_tdd_mode_disabled_in_config(
        self, mock_task_manager, mock_llm_service, sample_task
    ):
        """Test that TDD mode can be disabled via config."""
        config = TaskExpansionConfig(enabled=True, tdd_mode=False)
        mock_task_manager.get_task.return_value = sample_task

        mock_ctx = ExpansionContext(
            task=sample_task,
            related_tasks=[],
            relevant_files=[],
            file_snippets={},
            project_patterns={},
        )

        with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
            mock_gatherer = MockGatherer.return_value
            mock_gatherer.gather_context = AsyncMock(return_value=mock_ctx)

            expander = TaskExpander(config, mock_llm_service, mock_task_manager)

            await expander.expand_task("t1", "Main Task")

            provider = mock_llm_service.get_provider.return_value
            call_args = provider.generate_text.call_args
            system_prompt = call_args.kwargs["system_prompt"]

            # TDD mode instructions should not be present
            assert "TDD Mode Enabled" not in system_prompt
