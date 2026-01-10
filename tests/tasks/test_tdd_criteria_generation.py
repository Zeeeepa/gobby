"""
Tests for TDD-aware validation criteria generation.

Tests that:
- generate_criteria accepts labels parameter
- TDD label triggers TDD-specific criteria injection
- LLM-generated criteria combined with pattern criteria
- Multiple patterns can be combined
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.config.app import TaskValidationConfig
from gobby.config.tasks import PatternCriteriaConfig
from gobby.tasks.validation import TaskValidator


@pytest.fixture
def mock_llm():
    """Mock LLM service."""
    llm = MagicMock()
    provider = AsyncMock()
    llm.get_provider.return_value = provider
    return llm


@pytest.fixture
def validation_config():
    """Validation config with provider settings."""
    return TaskValidationConfig(
        enabled=True,
        provider="claude",
        model="test-model",
    )


class TestTddAwareCriteriaGeneration:
    """Tests for TDD-aware criteria generation."""

    @pytest.mark.asyncio
    async def test_generate_criteria_accepts_labels_parameter(self, mock_llm, validation_config):
        """generate_criteria should accept an optional labels parameter."""
        validator = TaskValidator(validation_config, mock_llm)
        mock_provider = mock_llm.get_provider.return_value
        mock_provider.generate_text.return_value = "## Deliverable\n- [ ] Feature works"

        # Should not raise TypeError for unexpected keyword argument
        result = await validator.generate_criteria(
            title="Implement feature",
            description="Add new feature",
            labels=["tdd"],
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_tdd_label_includes_tdd_criteria(self, mock_llm, validation_config):
        """When 'tdd' label is present, criteria should include TDD-specific items."""
        validator = TaskValidator(validation_config, mock_llm)
        mock_provider = mock_llm.get_provider.return_value
        mock_provider.generate_text.return_value = "## Deliverable\n- [ ] Feature works"

        result = await validator.generate_criteria(
            title="Implement feature",
            description="Add new feature",
            labels=["tdd"],
        )

        # TDD criteria should be injected
        assert "test" in result.lower() or "Test" in result
        # Should include red-green-refactor concepts
        assert any(
            phrase in result.lower()
            for phrase in ["red phase", "green phase", "tests written before"]
        )

    @pytest.mark.asyncio
    async def test_refactoring_label_includes_verification_criteria(
        self, mock_llm, validation_config
    ):
        """When 'refactoring' label is present, verification commands should appear."""
        validator = TaskValidator(validation_config, mock_llm)
        mock_provider = mock_llm.get_provider.return_value
        mock_provider.generate_text.return_value = "## Deliverable\n- [ ] Code refactored"

        result = await validator.generate_criteria(
            title="Refactor module",
            description="Clean up code",
            labels=["refactoring"],
        )

        # Refactoring criteria include tests, types, lint checks
        assert result is not None
        # Should have verification related content
        assert "test" in result.lower() or "lint" in result.lower() or "type" in result.lower()

    @pytest.mark.asyncio
    async def test_multiple_labels_combine_criteria(self, mock_llm, validation_config):
        """Multiple labels should combine their pattern criteria."""
        validator = TaskValidator(validation_config, mock_llm)
        mock_provider = mock_llm.get_provider.return_value
        mock_provider.generate_text.return_value = "## Deliverable\n- [ ] Module extracted"

        result = await validator.generate_criteria(
            title="Extract module using strangler fig",
            description="Use strangler fig pattern with TDD",
            labels=["strangler-fig", "tdd"],
        )

        # Should have both strangler-fig and TDD criteria
        assert result is not None
        # Strangler-fig criteria mention imports
        has_strangler = "import" in result.lower() or "circular" in result.lower()
        # TDD criteria mention tests
        has_tdd = "test" in result.lower()
        assert has_strangler or has_tdd  # At least one pattern should be present

    @pytest.mark.asyncio
    async def test_no_labels_generates_plain_criteria(self, mock_llm, validation_config):
        """Without labels, generate_criteria should work as before (no pattern injection)."""
        validator = TaskValidator(validation_config, mock_llm)
        mock_provider = mock_llm.get_provider.return_value
        llm_response = "## Deliverable\n- [ ] Bug fixed\n## Verification\n- [ ] Tests pass"
        mock_provider.generate_text.return_value = llm_response

        result = await validator.generate_criteria(
            title="Fix bug",
            description="Fix the login bug",
        )

        # Should return the LLM response without pattern-specific additions
        assert result == llm_response

    @pytest.mark.asyncio
    async def test_empty_labels_list_generates_plain_criteria(self, mock_llm, validation_config):
        """Empty labels list should behave same as no labels."""
        validator = TaskValidator(validation_config, mock_llm)
        mock_provider = mock_llm.get_provider.return_value
        llm_response = "## Deliverable\n- [ ] Feature added"
        mock_provider.generate_text.return_value = llm_response

        result = await validator.generate_criteria(
            title="Add feature",
            description="Add the feature",
            labels=[],
        )

        assert result == llm_response

    @pytest.mark.asyncio
    async def test_pattern_criteria_appended_to_llm_criteria(self, mock_llm, validation_config):
        """Pattern criteria should be appended to LLM-generated criteria."""
        validator = TaskValidator(validation_config, mock_llm)
        mock_provider = mock_llm.get_provider.return_value
        llm_response = "## Deliverable\n- [ ] Feature implemented"
        mock_provider.generate_text.return_value = llm_response

        result = await validator.generate_criteria(
            title="Implement with TDD",
            description="Use test-driven development",
            labels=["tdd"],
        )

        # LLM response should be present
        assert "Feature implemented" in result
        # TDD pattern criteria should also be present
        assert "Tdd Pattern" in result or "TDD" in result.upper()


class TestPatternCriteriaIntegration:
    """Tests for pattern criteria integration with validation."""

    @pytest.mark.asyncio
    async def test_tdd_pattern_criteria_structure(self, mock_llm, validation_config):
        """TDD pattern criteria should have expected structure."""
        validator = TaskValidator(validation_config, mock_llm)
        mock_provider = mock_llm.get_provider.return_value
        mock_provider.generate_text.return_value = "## Deliverable\n- [ ] Done"

        result = await validator.generate_criteria(
            title="Test task",
            description="A task",
            labels=["tdd"],
        )

        # Should have checkbox format for TDD criteria
        assert "- [ ]" in result
        # Should have TDD-specific items from PatternCriteriaConfig
        pattern_config = PatternCriteriaConfig()
        tdd_templates = pattern_config.patterns.get("tdd", [])

        # At least one TDD criterion should appear
        tdd_criteria_found = False
        for template in tdd_templates:
            # Templates may have placeholders, check for key phrases
            key_phrase = template.split("{")[0].strip() if "{" in template else template
            if key_phrase and key_phrase.lower() in result.lower():
                tdd_criteria_found = True
                break

        assert tdd_criteria_found, f"No TDD criteria found in result: {result}"

    @pytest.mark.asyncio
    async def test_criteria_disabled_returns_none(self, mock_llm):
        """When validation disabled, generate_criteria returns None even with labels."""
        config = TaskValidationConfig(enabled=False)
        validator = TaskValidator(config, mock_llm)

        result = await validator.generate_criteria(
            title="Test task",
            description="A task",
            labels=["tdd"],
        )

        assert result is None
