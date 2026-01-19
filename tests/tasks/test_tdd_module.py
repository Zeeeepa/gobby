"""
Tests for gobby.tasks.tdd module.

Tests the TDD sandwich pattern utilities including:
- should_skip_tdd() - pattern matching for TDD skip
- should_skip_expansion() - expansion skip logic
- apply_tdd_sandwich() - TDD sandwich pattern application
- build_expansion_context() - context building for expansion
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.tasks.tdd import (
    TDD_CRITERIA_BLUE,
    TDD_CRITERIA_RED,
    TDD_PARENT_CRITERIA,
    TDD_PREFIXES,
    TDD_SKIP_PATTERNS,
    apply_tdd_sandwich,
    build_expansion_context,
    should_skip_expansion,
    should_skip_tdd,
)


class TestShouldSkipTdd:
    """Tests for should_skip_tdd function."""

    def test_skip_tdd_prefix(self):
        """Tasks with [TDD] prefix should skip TDD transformation."""
        assert should_skip_tdd("[TDD] Write tests for auth") is True

    def test_skip_impl_prefix(self):
        """Tasks with [IMPL] prefix should skip TDD transformation."""
        assert should_skip_tdd("[IMPL] Add authentication") is True

    def test_skip_ref_prefix(self):
        """Tasks with [REF] prefix should skip TDD transformation."""
        assert should_skip_tdd("[REF] Clean up auth code") is True

    def test_skip_legacy_write_tests(self):
        """Legacy 'Write tests for:' prefix should skip."""
        assert should_skip_tdd("Write tests for: login feature") is True

    def test_skip_legacy_implement(self):
        """Legacy 'Implement:' prefix should skip."""
        assert should_skip_tdd("Implement: user authentication") is True

    def test_skip_legacy_refactor(self):
        """Legacy 'Refactor:' prefix should skip."""
        assert should_skip_tdd("Refactor: auth module") is True

    def test_skip_delete_task(self):
        """Delete tasks should skip TDD."""
        assert should_skip_tdd("Delete unused files") is True
        assert should_skip_tdd("Delete the deprecated module") is True

    def test_skip_remove_task(self):
        """Remove tasks should skip TDD."""
        assert should_skip_tdd("Remove legacy code") is True
        assert should_skip_tdd("Remove the old API endpoint") is True

    def test_skip_update_readme(self):
        """README updates should skip TDD."""
        assert should_skip_tdd("Update README with new instructions") is True
        assert should_skip_tdd("Update the README.md file") is True

    def test_skip_update_documentation(self):
        """Documentation updates should skip TDD."""
        assert should_skip_tdd("Update documentation for API") is True
        assert should_skip_tdd("Update docs for the new feature") is True

    def test_skip_update_config_toml(self):
        """TOML config updates should skip TDD."""
        assert should_skip_tdd("Update pyproject.toml with new dependency") is True

    def test_skip_update_config_yaml(self):
        """YAML config updates should skip TDD."""
        assert should_skip_tdd("Update config.yaml with new setting") is True
        assert should_skip_tdd("Update settings.yml") is True

    def test_skip_update_config_json(self):
        """JSON config updates should skip TDD."""
        assert should_skip_tdd("Update package.json scripts") is True

    def test_skip_update_env(self):
        """Env file updates should skip TDD."""
        assert should_skip_tdd("Update .env with new variables") is True

    def test_skip_update_config_general(self):
        """General config updates should skip TDD."""
        assert should_skip_tdd("Update config for production") is True

    def test_no_skip_regular_task(self):
        """Regular tasks should NOT skip TDD."""
        assert should_skip_tdd("Add user authentication") is False
        assert should_skip_tdd("Fix the login bug") is False
        assert should_skip_tdd("Implement feature XYZ") is False  # No colon

    def test_case_insensitive(self):
        """Skip patterns should be case insensitive."""
        assert should_skip_tdd("delete unused files") is True
        assert should_skip_tdd("DELETE unused files") is True
        assert should_skip_tdd("Delete Unused Files") is True


class TestShouldSkipExpansion:
    """Tests for should_skip_expansion function."""

    def test_skip_tdd_prefix(self):
        """[TDD] tasks should never be expanded."""
        should_skip, reason = should_skip_expansion("[TDD] Write tests", is_expanded=False)
        assert should_skip is True
        assert "[TDD]" in reason

    def test_skip_impl_prefix(self):
        """[IMPL] tasks should never be expanded."""
        should_skip, reason = should_skip_expansion("[IMPL] Implement feature", is_expanded=False)
        assert should_skip is True
        assert "[IMPL]" in reason

    def test_skip_ref_prefix(self):
        """[REF] tasks should never be expanded."""
        should_skip, reason = should_skip_expansion("[REF] Refactor code", is_expanded=False)
        assert should_skip is True
        assert "[REF]" in reason

    def test_skip_already_expanded(self):
        """Already expanded tasks should be skipped without force."""
        should_skip, reason = should_skip_expansion("Some task", is_expanded=True)
        assert should_skip is True
        assert "already expanded" in reason

    def test_no_skip_with_force(self):
        """Already expanded tasks can be re-expanded with force=True."""
        should_skip, reason = should_skip_expansion("Some task", is_expanded=True, force=True)
        assert should_skip is False
        assert reason == ""

    def test_no_skip_regular_task(self):
        """Regular tasks should not be skipped."""
        should_skip, reason = should_skip_expansion("Add feature", is_expanded=False)
        assert should_skip is False
        assert reason == ""


class TestApplyTddSandwich:
    """Tests for apply_tdd_sandwich function."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock task manager."""
        manager = MagicMock()
        return manager

    @pytest.fixture
    def mock_dep_manager(self):
        """Create a mock dependency manager."""
        manager = MagicMock()
        return manager

    @pytest.fixture
    def mock_parent_task(self):
        """Create a mock parent task."""
        task = MagicMock()
        task.id = "parent-123"
        task.title = "Implement authentication"
        task.project_id = "project-456"
        task.priority = 1
        task.is_tdd_applied = False
        return task

    @pytest.fixture
    def mock_impl_tasks(self):
        """Create mock implementation tasks."""
        tasks = []
        for i in range(3):
            task = MagicMock()
            task.id = f"impl-{i}"
            task.title = f"Implementation task {i}"
            tasks.append(task)
        return tasks

    @pytest.mark.asyncio
    async def test_parent_not_found(self, mock_task_manager, mock_dep_manager):
        """Return error when parent task not found."""
        mock_task_manager.get_task.return_value = None

        result = await apply_tdd_sandwich(
            mock_task_manager,
            mock_dep_manager,
            "nonexistent-id",
            ["impl-1", "impl-2"],
        )

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_no_impl_tasks(self, mock_task_manager, mock_dep_manager, mock_parent_task):
        """Return error when no implementation tasks provided."""
        mock_task_manager.get_task.return_value = mock_parent_task

        result = await apply_tdd_sandwich(
            mock_task_manager,
            mock_dep_manager,
            "parent-123",
            [],
        )

        assert result["success"] is False
        assert "No implementation tasks" in result["error"]

    @pytest.mark.asyncio
    async def test_already_tdd_applied(self, mock_task_manager, mock_dep_manager, mock_parent_task):
        """Skip if TDD already applied to parent task."""
        mock_parent_task.is_tdd_applied = True
        mock_task_manager.get_task.return_value = mock_parent_task

        result = await apply_tdd_sandwich(
            mock_task_manager,
            mock_dep_manager,
            "parent-123",
            ["impl-1"],
        )

        assert result["success"] is False
        assert result.get("skipped") is True
        assert result.get("reason") == "already_applied"

    @pytest.mark.asyncio
    async def test_successful_sandwich_application(
        self, mock_task_manager, mock_dep_manager, mock_parent_task, mock_impl_tasks
    ):
        """Test successful TDD sandwich application."""
        # Setup mock returns
        mock_task_manager.get_task.side_effect = lambda task_id: (
            mock_parent_task
            if task_id == "parent-123"
            else next((t for t in mock_impl_tasks if t.id == task_id), None)
        )

        # Create mock test and refactor tasks
        mock_test_task = MagicMock()
        mock_test_task.id = "test-task-id"
        mock_refactor_task = MagicMock()
        mock_refactor_task.id = "refactor-task-id"

        create_call_count = [0]

        def create_task_side_effect(**kwargs):
            create_call_count[0] += 1
            if create_call_count[0] == 1:
                return mock_test_task
            return mock_refactor_task

        mock_task_manager.create_task.side_effect = create_task_side_effect

        result = await apply_tdd_sandwich(
            mock_task_manager,
            mock_dep_manager,
            "parent-123",
            [t.id for t in mock_impl_tasks],
        )

        assert result["success"] is True
        assert result["tasks_created"] == 2
        assert result["test_task_id"] == "test-task-id"
        assert result["refactor_task_id"] == "refactor-task-id"
        assert result["impl_task_count"] == 3

        # Verify create_task was called twice (TDD + REF)
        assert mock_task_manager.create_task.call_count == 2

        # Verify parent was marked as TDD-applied
        mock_task_manager.update_task.assert_any_call(
            "parent-123",
            is_tdd_applied=True,
            validation_criteria=TDD_PARENT_CRITERIA,
        )

    @pytest.mark.asyncio
    async def test_impl_tasks_get_prefix(
        self, mock_task_manager, mock_dep_manager, mock_parent_task, mock_impl_tasks
    ):
        """Test that implementation tasks get [IMPL] prefix."""
        mock_task_manager.get_task.side_effect = lambda task_id: (
            mock_parent_task
            if task_id == "parent-123"
            else next((t for t in mock_impl_tasks if t.id == task_id), None)
        )

        mock_test_task = MagicMock(id="test-id")
        mock_refactor_task = MagicMock(id="ref-id")
        mock_task_manager.create_task.side_effect = [mock_test_task, mock_refactor_task]

        result = await apply_tdd_sandwich(
            mock_task_manager,
            mock_dep_manager,
            "parent-123",
            [t.id for t in mock_impl_tasks],
        )

        assert result["success"] is True

        # Verify impl tasks were updated with [IMPL] prefix
        for task in mock_impl_tasks:
            mock_task_manager.update_task.assert_any_call(
                task.id, title=f"[IMPL] {task.title}"
            )

    @pytest.mark.asyncio
    async def test_dependencies_wired_correctly(
        self, mock_task_manager, mock_dep_manager, mock_parent_task, mock_impl_tasks
    ):
        """Test that dependencies are wired correctly."""
        mock_task_manager.get_task.side_effect = lambda task_id: (
            mock_parent_task
            if task_id == "parent-123"
            else next((t for t in mock_impl_tasks if t.id == task_id), None)
        )

        mock_test_task = MagicMock(id="test-id")
        mock_refactor_task = MagicMock(id="ref-id")
        mock_task_manager.create_task.side_effect = [mock_test_task, mock_refactor_task]

        result = await apply_tdd_sandwich(
            mock_task_manager,
            mock_dep_manager,
            "parent-123",
            [t.id for t in mock_impl_tasks],
        )

        assert result["success"] is True

        # Verify all impl tasks depend on test task
        for task in mock_impl_tasks:
            mock_dep_manager.add_dependency.assert_any_call(task.id, "test-id", "blocks")

        # Verify refactor depends on test task
        mock_dep_manager.add_dependency.assert_any_call("ref-id", "test-id", "blocks")

        # Verify refactor depends on all impl tasks
        for task in mock_impl_tasks:
            mock_dep_manager.add_dependency.assert_any_call("ref-id", task.id, "blocks")

    @pytest.mark.asyncio
    async def test_handles_existing_dependencies(
        self, mock_task_manager, mock_dep_manager, mock_parent_task, mock_impl_tasks
    ):
        """Test that existing dependencies don't cause errors."""
        mock_task_manager.get_task.side_effect = lambda task_id: (
            mock_parent_task
            if task_id == "parent-123"
            else next((t for t in mock_impl_tasks if t.id == task_id), None)
        )

        mock_test_task = MagicMock(id="test-id")
        mock_refactor_task = MagicMock(id="ref-id")
        mock_task_manager.create_task.side_effect = [mock_test_task, mock_refactor_task]

        # Simulate existing dependency error
        mock_dep_manager.add_dependency.side_effect = ValueError("Dependency exists")

        result = await apply_tdd_sandwich(
            mock_task_manager,
            mock_dep_manager,
            "parent-123",
            [t.id for t in mock_impl_tasks],
        )

        # Should still succeed despite ValueError from add_dependency
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_handles_exception(self, mock_task_manager, mock_dep_manager, mock_parent_task):
        """Test that exceptions are caught and returned as errors."""
        mock_task_manager.get_task.return_value = mock_parent_task
        mock_task_manager.create_task.side_effect = Exception("Database error")

        result = await apply_tdd_sandwich(
            mock_task_manager,
            mock_dep_manager,
            "parent-123",
            ["impl-1"],
        )

        assert result["success"] is False
        assert "Database error" in result["error"]

    @pytest.mark.asyncio
    async def test_impl_task_already_has_prefix(
        self, mock_task_manager, mock_dep_manager, mock_parent_task
    ):
        """Test that impl tasks with existing [IMPL] prefix are not double-prefixed."""
        mock_impl_task = MagicMock()
        mock_impl_task.id = "impl-1"
        mock_impl_task.title = "[IMPL] Already prefixed task"

        mock_task_manager.get_task.side_effect = lambda task_id: (
            mock_parent_task if task_id == "parent-123" else mock_impl_task
        )

        mock_test_task = MagicMock(id="test-id")
        mock_refactor_task = MagicMock(id="ref-id")
        mock_task_manager.create_task.side_effect = [mock_test_task, mock_refactor_task]

        result = await apply_tdd_sandwich(
            mock_task_manager,
            mock_dep_manager,
            "parent-123",
            ["impl-1"],
        )

        assert result["success"] is True

        # Should NOT call update_task for the already-prefixed task (title update)
        # But should still call it for the parent
        title_update_calls = [
            call
            for call in mock_task_manager.update_task.call_args_list
            if call[0] == ("impl-1",) and "title" in call[1]
        ]
        assert len(title_update_calls) == 0

    @pytest.mark.asyncio
    async def test_impl_task_not_found(
        self, mock_task_manager, mock_dep_manager, mock_parent_task
    ):
        """Test handling when an impl task is not found."""
        mock_task_manager.get_task.side_effect = lambda task_id: (
            mock_parent_task if task_id == "parent-123" else None
        )

        mock_test_task = MagicMock(id="test-id")
        mock_refactor_task = MagicMock(id="ref-id")
        mock_task_manager.create_task.side_effect = [mock_test_task, mock_refactor_task]

        result = await apply_tdd_sandwich(
            mock_task_manager,
            mock_dep_manager,
            "parent-123",
            ["nonexistent-impl"],
        )

        # Should still succeed, just with no impl titles in the TDD task description
        assert result["success"] is True


class TestBuildExpansionContext:
    """Tests for build_expansion_context function."""

    def test_no_context(self):
        """Returns None when no context provided."""
        result = build_expansion_context(None, None)
        assert result is None

    def test_only_user_context(self):
        """Returns user context with header."""
        result = build_expansion_context(None, "User provided context")
        assert "## Additional Context" in result
        assert "User provided context" in result

    def test_only_expansion_context_valid_json(self):
        """Parses JSON expansion context correctly."""
        context_json = json.dumps({
            "research_findings": "Some research findings",
            "validation_criteria": "Must pass tests",
            "complexity_level": "medium",
            "suggested_subtask_count": 3,
        })

        result = build_expansion_context(context_json, None)

        assert "## Research Findings" in result
        assert "Some research findings" in result
        assert "## Validation Criteria" in result
        assert "Must pass tests" in result
        assert "## Complexity Analysis" in result
        assert "Complexity level: medium" in result
        assert "Suggested subtask count: 3" in result

    def test_expansion_context_partial_fields(self):
        """Handles JSON with only some fields."""
        context_json = json.dumps({
            "research_findings": "Only research",
        })

        result = build_expansion_context(context_json, None)

        assert "## Research Findings" in result
        assert "Only research" in result
        assert "## Validation Criteria" not in result
        assert "## Complexity Analysis" not in result

    def test_expansion_context_only_complexity_level(self):
        """Handles JSON with only complexity_level."""
        context_json = json.dumps({
            "complexity_level": "high",
        })

        result = build_expansion_context(context_json, None)

        assert "## Complexity Analysis" in result
        assert "Complexity level: high" in result

    def test_expansion_context_only_subtask_count(self):
        """Handles JSON with only suggested_subtask_count."""
        context_json = json.dumps({
            "suggested_subtask_count": 5,
        })

        result = build_expansion_context(context_json, None)

        assert "## Complexity Analysis" in result
        assert "Suggested subtask count: 5" in result

    def test_expansion_context_invalid_json(self):
        """Falls back to legacy format for invalid JSON."""
        result = build_expansion_context("Not valid JSON", None)

        assert "## Legacy Expansion Context" in result
        assert "Not valid JSON" in result

    def test_combined_contexts(self):
        """Combines expansion context with user context."""
        context_json = json.dumps({
            "research_findings": "Research data",
        })

        result = build_expansion_context(context_json, "Additional user info")

        assert "## Research Findings" in result
        assert "Research data" in result
        assert "## Additional Context" in result
        assert "Additional user info" in result

    def test_empty_expansion_context_json(self):
        """Handles empty JSON object."""
        context_json = json.dumps({})

        result = build_expansion_context(context_json, None)

        # Empty JSON should return None (no meaningful context)
        assert result is None

    def test_expansion_context_empty_string(self):
        """Handles empty string expansion context."""
        # Empty string should be treated as no context
        result = build_expansion_context("", None)

        # Empty string is truthy but contains no meaningful data
        # It will fail JSON parsing and fall back to legacy
        assert result is None or "## Legacy Expansion Context" in result


class TestTddConstants:
    """Tests for TDD module constants."""

    def test_tdd_prefixes(self):
        """TDD_PREFIXES contains expected prefixes."""
        assert "[TDD]" in TDD_PREFIXES
        assert "[IMPL]" in TDD_PREFIXES
        assert "[REF]" in TDD_PREFIXES

    def test_tdd_skip_patterns_cover_prefixes(self):
        """TDD_SKIP_PATTERNS covers TDD prefixes."""
        # The patterns should match the TDD_PREFIXES
        patterns_text = " ".join(TDD_SKIP_PATTERNS)
        assert "TDD" in patterns_text
        assert "IMPL" in patterns_text
        assert "REF" in patterns_text

    def test_tdd_criteria_red_has_checkbox_format(self):
        """TDD_CRITERIA_RED uses checkbox format."""
        assert "- [ ]" in TDD_CRITERIA_RED
        assert "tests" in TDD_CRITERIA_RED.lower() or "test" in TDD_CRITERIA_RED.lower()

    def test_tdd_criteria_blue_has_checkbox_format(self):
        """TDD_CRITERIA_BLUE uses checkbox format."""
        assert "- [ ]" in TDD_CRITERIA_BLUE
        assert "refactor" in TDD_CRITERIA_BLUE.lower()

    def test_tdd_parent_criteria_has_checkbox_format(self):
        """TDD_PARENT_CRITERIA uses checkbox format."""
        assert "- [ ]" in TDD_PARENT_CRITERIA
        assert "child tasks" in TDD_PARENT_CRITERIA.lower()
