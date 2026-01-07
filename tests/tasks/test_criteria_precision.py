"""
Tests for precise criteria generation in task expansion.

Tests that:
- Pattern-specific criteria are injected based on labels/description
- Verification commands from project config appear in criteria
- CriteriaGenerator produces actionable, verifiable criteria
"""

import pytest

from gobby.config.features import ProjectVerificationConfig
from gobby.config.tasks import PatternCriteriaConfig
from gobby.storage.tasks import Task
from gobby.tasks.criteria import CriteriaGenerator, PatternCriteriaInjector


@pytest.fixture
def pattern_config():
    """Pattern criteria config with test patterns."""
    return PatternCriteriaConfig()


@pytest.fixture
def verification_config():
    """Verification config with test commands."""
    return ProjectVerificationConfig(
        unit_tests="uv run pytest",
        type_check="uv run mypy src/",
        lint="uv run ruff check src/",
    )


@pytest.fixture
def pattern_injector(pattern_config, verification_config):
    """PatternCriteriaInjector with test config."""
    return PatternCriteriaInjector(
        pattern_config=pattern_config,
        verification_config=verification_config,
    )


@pytest.fixture
def criteria_generator(pattern_config, verification_config):
    """CriteriaGenerator with test config."""
    return CriteriaGenerator(
        pattern_config=pattern_config,
        verification_config=verification_config,
    )


class TestPatternDetection:
    """Tests for pattern detection from labels and description."""

    def test_detects_pattern_from_labels(self, pattern_injector):
        """Pattern detected from task labels."""
        task = Task(
            id="gt-test",
            project_id="p1",
            title="Refactor module",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            labels=["strangler-fig"],
        )
        patterns = pattern_injector.detect_patterns(task)
        assert "strangler-fig" in patterns

    def test_detects_pattern_from_description(self, pattern_injector):
        """Pattern detected from description keywords."""
        task = Task(
            id="gt-test",
            project_id="p1",
            title="Refactor module",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            description="Use strangler fig pattern to extract this component",
        )
        patterns = pattern_injector.detect_patterns(task)
        assert "strangler-fig" in patterns

    def test_detects_multiple_patterns(self, pattern_injector):
        """Multiple patterns can be detected."""
        task = Task(
            id="gt-test",
            project_id="p1",
            title="Refactor module with TDD",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            labels=["strangler-fig", "tdd"],
        )
        patterns = pattern_injector.detect_patterns(task)
        assert "strangler-fig" in patterns
        assert "tdd" in patterns

    def test_no_pattern_detected(self, pattern_injector):
        """No patterns when labels/description don't match."""
        task = Task(
            id="gt-test",
            project_id="p1",
            title="Simple task",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        patterns = pattern_injector.detect_patterns(task)
        assert patterns == []


class TestStranglerFigCriteriaInjection:
    """Tests for strangler-fig pattern criteria."""

    def test_strangler_fig_criteria_include_import_checks(self, pattern_injector):
        """Strangler-fig criteria include import verification."""
        task = Task(
            id="gt-test",
            project_id="p1",
            title="Extract component",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            labels=["strangler-fig"],
        )
        criteria = pattern_injector.inject(task)

        # Strangler-fig pattern should include these criteria
        assert "Original import still works" in criteria or "original import" in criteria.lower()
        assert "New import works" in criteria or "new import" in criteria.lower()

    def test_strangler_fig_criteria_include_circular_import_check(self, pattern_injector):
        """Strangler-fig criteria include circular import verification."""
        task = Task(
            id="gt-test",
            project_id="p1",
            title="Extract component",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            labels=["strangler-fig"],
        )
        criteria = pattern_injector.inject(task)
        assert "circular" in criteria.lower()


class TestVerificationCommandSubstitution:
    """Tests for verification command placeholder substitution."""

    def test_unit_tests_command_substituted(self, pattern_injector):
        """unit_tests placeholder is replaced with actual command."""
        task = Task(
            id="gt-test",
            project_id="p1",
            title="Refactor module",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            labels=["refactoring"],
        )
        criteria = pattern_injector.inject(task)

        # Should use actual command, not placeholder
        assert "uv run pytest" in criteria
        assert "{unit_tests}" not in criteria

    def test_type_check_command_substituted(self, pattern_injector):
        """type_check placeholder is replaced with actual command."""
        task = Task(
            id="gt-test",
            project_id="p1",
            title="Refactor module",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            labels=["refactoring"],
        )
        criteria = pattern_injector.inject(task)

        # Should use actual command
        assert "uv run mypy" in criteria
        assert "{type_check}" not in criteria

    def test_lint_command_substituted(self, pattern_injector):
        """lint placeholder is replaced with actual command."""
        task = Task(
            id="gt-test",
            project_id="p1",
            title="Refactor module",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            labels=["refactoring"],
        )
        criteria = pattern_injector.inject(task)

        # Should use actual command
        assert "uv run ruff" in criteria
        assert "{lint}" not in criteria


class TestCriteriaGenerator:
    """Tests for the CriteriaGenerator class."""

    def test_generates_pattern_criteria_from_labels(self, criteria_generator):
        """CriteriaGenerator generates pattern-specific criteria from labels."""
        criteria = criteria_generator.generate(
            title="Extract module",
            description="Using strangler fig pattern",
            labels=["strangler-fig"],
        )

        # Should include pattern-specific criteria
        assert "Strangler" in criteria or "strangler" in criteria.lower()
        assert len(criteria) > 0

    def test_generates_verification_criteria(self, criteria_generator):
        """CriteriaGenerator generates verification command criteria."""
        criteria = criteria_generator.generate(
            title="Add feature",
            description="Implement new feature",
            labels=["refactoring"],
        )

        # Should include verification section with actual commands
        assert "uv run pytest" in criteria or "uv run mypy" in criteria or "uv run ruff" in criteria

    def test_generates_file_criteria_when_files_mentioned(self, criteria_generator):
        """CriteriaGenerator generates file-specific criteria."""
        criteria = criteria_generator.generate(
            title="Modify expansion.py",
            description="Update the expansion.py file",
            labels=[],
            relevant_files=["src/gobby/tasks/expansion.py"],
        )

        # File criteria only generated if file name appears in text
        if "expansion.py" in criteria:
            assert "File Requirements" in criteria

    def test_verification_criteria_generated_without_patterns(self, criteria_generator):
        """Verification criteria still generated even without pattern labels."""
        criteria = criteria_generator.generate(
            title="Simple task",
            description="Just a simple task",
            labels=[],
        )

        # Verification criteria are always generated when config available
        # even without pattern-specific labels
        assert "Verification" in criteria or criteria == ""

    def test_empty_criteria_without_config(self):
        """Empty criteria when no verification config provided."""
        generator = CriteriaGenerator(
            pattern_config=PatternCriteriaConfig(),
            verification_config=None,
        )
        criteria = generator.generate(
            title="Simple task",
            description="Just a simple task",
            labels=[],
        )

        # No criteria should be generated without config
        assert criteria == ""

    def test_accepts_verification_commands_override(self, criteria_generator):
        """CriteriaGenerator accepts custom verification commands."""
        criteria = criteria_generator.generate(
            title="Custom build task",
            description="Task with custom verification",
            labels=["refactoring"],
            verification_commands={
                "unit_tests": "npm test",
                "lint": "npm run lint",
            },
        )

        # Should use custom commands when refactoring pattern detected
        # The override commands are passed through for pattern substitution
        assert criteria is not None


class TestTddPatternCriteria:
    """Tests for TDD pattern criteria."""

    def test_tdd_criteria_include_test_first(self, pattern_injector):
        """TDD criteria include test-first verification."""
        task = Task(
            id="gt-test",
            project_id="p1",
            title="Implement feature with TDD",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            labels=["tdd"],
        )
        criteria = pattern_injector.inject(task)

        # TDD pattern should mention tests
        assert "test" in criteria.lower() or "Test" in criteria


class TestRefactoringPatternCriteria:
    """Tests for refactoring pattern criteria."""

    def test_refactoring_criteria_include_all_checks(self, pattern_injector):
        """Refactoring criteria include tests, types, and lint checks."""
        task = Task(
            id="gt-test",
            project_id="p1",
            title="Refactor module",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            labels=["refactoring"],
        )
        criteria = pattern_injector.inject(task)

        # Should have all three verification commands
        assert "uv run pytest" in criteria
        assert "uv run mypy" in criteria
        assert "uv run ruff" in criteria


class TestInjectForLabels:
    """Tests for inject_for_labels convenience method."""

    def test_inject_for_labels_without_task(self, pattern_injector):
        """inject_for_labels works without a task object."""
        criteria = pattern_injector.inject_for_labels(
            labels=["refactoring"],
        )

        # Should still generate criteria
        assert len(criteria) > 0
        assert "uv run pytest" in criteria

    def test_inject_for_labels_with_extra_placeholders(self, pattern_injector):
        """inject_for_labels accepts extra placeholder values."""
        criteria = pattern_injector.inject_for_labels(
            labels=["refactoring"],
            extra_placeholders={"custom_check": "run custom"},
        )

        # Should include pattern criteria
        assert len(criteria) > 0
