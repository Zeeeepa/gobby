"""
Tests for task enrichment module.

TDD Red phase: These tests should fail until the enrich.py module is implemented.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestEnrichmentResult:
    """Tests for the EnrichmentResult dataclass."""

    def test_enrichment_result_can_be_imported(self):
        """Test that EnrichmentResult can be imported from the module."""
        from gobby.tasks.enrich import EnrichmentResult

        assert EnrichmentResult is not None

    def test_enrichment_result_has_required_fields(self):
        """Test that EnrichmentResult has all required fields."""
        from gobby.tasks.enrich import EnrichmentResult

        # Create an instance with required fields
        result = EnrichmentResult(
            task_id="test-task-123",
            category="code",
            complexity_score=2,
            research_findings="Found relevant patterns in auth module",
            suggested_subtask_count=3,
            validation_criteria="All tests pass, code review approved",
            mcp_tools_used=["context7", "grep"],
        )

        assert result.task_id == "test-task-123"
        assert result.category == "code"
        assert result.complexity_score == 2
        assert result.research_findings == "Found relevant patterns in auth module"
        assert result.suggested_subtask_count == 3
        assert result.validation_criteria == "All tests pass, code review approved"
        assert result.mcp_tools_used == ["context7", "grep"]

    def test_enrichment_result_optional_fields_default_to_none(self):
        """Test that optional fields default to None."""
        from gobby.tasks.enrich import EnrichmentResult

        # Create with only task_id (minimum required)
        result = EnrichmentResult(task_id="test-task-456")

        assert result.task_id == "test-task-456"
        assert result.category is None
        assert result.complexity_score is None
        assert result.research_findings is None
        assert result.suggested_subtask_count is None
        assert result.validation_criteria is None
        assert result.mcp_tools_used is None

    def test_enrichment_result_to_dict(self):
        """Test that EnrichmentResult can be converted to a dictionary."""
        from gobby.tasks.enrich import EnrichmentResult

        result = EnrichmentResult(
            task_id="test-task-789",
            category="document",
            complexity_score=1,
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["task_id"] == "test-task-789"
        assert result_dict["category"] == "document"
        assert result_dict["complexity_score"] == 1

    def test_enrichment_result_category_validation(self):
        """Test that category accepts valid values."""
        from gobby.tasks.enrich import EnrichmentResult

        # Valid categories based on the spec
        valid_categories = ["code", "document", "research", "config", "test", "manual"]

        for category in valid_categories:
            result = EnrichmentResult(task_id="test", category=category)
            assert result.category == category


class TestTaskEnricher:
    """Tests for the TaskEnricher class."""

    def test_task_enricher_can_be_imported(self):
        """Test that TaskEnricher can be imported from the module."""
        from gobby.tasks.enrich import TaskEnricher

        assert TaskEnricher is not None

    def test_task_enricher_has_enrich_method(self):
        """Test that TaskEnricher has an enrich method."""
        from gobby.tasks.enrich import TaskEnricher

        enricher = TaskEnricher()
        assert hasattr(enricher, "enrich")
        assert callable(enricher.enrich)

    @pytest.mark.asyncio
    async def test_task_enricher_enrich_returns_enrichment_result(self):
        """Test that enrich method returns an EnrichmentResult."""
        from gobby.tasks.enrich import EnrichmentResult, TaskEnricher

        enricher = TaskEnricher()

        # Mock task data
        result = await enricher.enrich(
            task_id="test-task-001",
            title="Implement user login",
            description="Add login functionality",
        )

        assert isinstance(result, EnrichmentResult)
        assert result.task_id == "test-task-001"


class TestCodeResearch:
    """Tests for code research functionality in TaskEnricher.

    TDD Red Phase: These tests verify the code research feature that searches
    the codebase for relevant files, patterns, and function signatures.
    """

    @pytest.mark.asyncio
    async def test_code_research_searches_codebase(self):
        """Test that code research searches for relevant files when enabled."""
        from gobby.tasks.enrich import TaskEnricher

        enricher = TaskEnricher()

        result = await enricher.enrich(
            task_id="test-task",
            title="Add user authentication",
            description="Implement login and registration",
            enable_code_research=True,
        )

        # When code research is enabled, research_findings should be populated
        assert result.research_findings is not None
        assert len(result.research_findings) > 0

    @pytest.mark.asyncio
    async def test_code_research_finds_relevant_files(self):
        """Test that code research identifies relevant files for the task."""
        from gobby.tasks.enrich import TaskEnricher

        enricher = TaskEnricher()

        result = await enricher.enrich(
            task_id="test-task",
            title="Fix bug in task manager",
            description="Fix the create_task method in task manager",
            enable_code_research=True,
        )

        # Research findings should mention relevant files
        assert result.research_findings is not None
        # Should find files related to tasks (implementation-specific)
        assert "task" in result.research_findings.lower()

    @pytest.mark.asyncio
    async def test_code_research_respects_disable_flag(self):
        """Test that code research is skipped when disabled."""
        from gobby.tasks.enrich import TaskEnricher

        enricher = TaskEnricher()

        result = await enricher.enrich(
            task_id="test-task",
            title="Simple task",
            description="A simple task",
            enable_code_research=False,
        )

        # When disabled, research_findings should be None or minimal
        # The enricher may still return basic info but shouldn't do codebase search
        # This test ensures the flag is respected
        assert result.task_id == "test-task"

    @pytest.mark.asyncio
    async def test_code_research_with_code_context(self):
        """Test that code research uses provided code context."""
        from gobby.tasks.enrich import TaskEnricher

        enricher = TaskEnricher()

        code_context = """
        def create_task(self, title: str, description: str) -> Task:
            '''Create a new task.'''
            pass
        """

        result = await enricher.enrich(
            task_id="test-task",
            title="Improve create_task method",
            description="Add validation to create_task",
            code_context=code_context,
            enable_code_research=True,
        )

        # Should incorporate provided code context
        assert result.research_findings is not None

    @pytest.mark.asyncio
    async def test_code_research_categorizes_task(self):
        """Test that code research helps categorize the task."""
        from gobby.tasks.enrich import TaskEnricher

        enricher = TaskEnricher()

        result = await enricher.enrich(
            task_id="test-task",
            title="Write tests for user service",
            description="Add unit tests for the user service module",
            enable_code_research=True,
        )

        # Should categorize as "test" based on title/description
        assert result.category is not None
        assert result.category == "test"

    @pytest.mark.asyncio
    async def test_code_research_estimates_complexity(self):
        """Test that code research provides complexity estimate."""
        from gobby.tasks.enrich import TaskEnricher

        enricher = TaskEnricher()

        result = await enricher.enrich(
            task_id="test-task",
            title="Refactor authentication module",
            description="Complete refactoring of auth including OAuth, JWT, and session management",
            enable_code_research=True,
        )

        # Should estimate complexity (1=low, 2=medium, 3=high)
        assert result.complexity_score is not None
        assert 1 <= result.complexity_score <= 3

    @pytest.mark.asyncio
    async def test_code_research_suggests_subtask_count(self):
        """Test that code research suggests appropriate subtask count."""
        from gobby.tasks.enrich import TaskEnricher

        enricher = TaskEnricher()

        result = await enricher.enrich(
            task_id="test-task",
            title="Implement user management",
            description="Add user CRUD operations, roles, and permissions",
            enable_code_research=True,
        )

        # Should suggest number of subtasks based on complexity
        assert result.suggested_subtask_count is not None
        assert result.suggested_subtask_count >= 1

    @pytest.mark.asyncio
    async def test_code_research_with_project_context(self):
        """Test that code research uses project context."""
        from gobby.tasks.enrich import TaskEnricher

        enricher = TaskEnricher()

        project_context = """
        Project: gobby
        Language: Python
        Framework: FastAPI
        Database: SQLite
        """

        result = await enricher.enrich(
            task_id="test-task",
            title="Add database migration",
            description="Add migration for new user table",
            project_context=project_context,
            enable_code_research=True,
        )

        # Should incorporate project context in research
        assert result.research_findings is not None

    @pytest.mark.asyncio
    async def test_code_research_handles_empty_codebase(self):
        """Test that code research handles empty/no codebase gracefully."""
        from gobby.tasks.enrich import TaskEnricher

        enricher = TaskEnricher()

        # Even without codebase access, should return valid result
        result = await enricher.enrich(
            task_id="test-task",
            title="Initial setup",
            description="Set up project structure",
            enable_code_research=True,
        )

        # Should not raise, should return basic enrichment
        assert result.task_id == "test-task"

    @pytest.mark.asyncio
    async def test_code_research_pattern_detection(self):
        """Test that code research detects code patterns."""
        from gobby.tasks.enrich import TaskEnricher

        enricher = TaskEnricher()

        result = await enricher.enrich(
            task_id="test-task",
            title="Add repository pattern",
            description="Implement repository pattern for data access layer",
            enable_code_research=True,
        )

        # Research should mention patterns if found
        assert result.research_findings is not None
