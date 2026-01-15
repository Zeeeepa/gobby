"""
Tests for task enrichment module.

TDD Red phase: These tests should fail until the enrich.py module is implemented.
"""

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
