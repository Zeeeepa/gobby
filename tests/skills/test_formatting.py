"""Tests for skill formatting helpers (recommend_skills_for_task).

Relocated from tests/workflows/test_context_actions.py as part of dead-code cleanup.
"""

import pytest

from gobby.skills.formatting import recommend_skills_for_task

pytestmark = pytest.mark.unit


class TestRecommendSkillsForTask:
    """Tests for the recommend_skills_for_task function."""

    def test_returns_list(self) -> None:
        """Should return a list of skill names."""
        result = recommend_skills_for_task({"title": "Test task"})
        assert isinstance(result, list)

    def test_with_code_category(self) -> None:
        """Should return code-related skills for code category."""
        task = {"title": "Test task", "category": "code"}
        result = recommend_skills_for_task(task)

        assert "gobby-tasks" in result

    def test_with_docs_category(self) -> None:
        """Should return docs-related skills for docs category."""
        task = {"title": "Test task", "category": "docs"}
        result = recommend_skills_for_task(task)

        assert "gobby-tasks" in result
        assert "gobby-plan" in result

    def test_with_test_category(self) -> None:
        """Should return test-related skills for test category."""
        task = {"title": "Test task", "category": "test"}
        result = recommend_skills_for_task(task)

        assert "gobby-tasks" in result

    def test_with_no_category(self) -> None:
        """Should return always-apply skills when no category."""
        task = {"title": "Test task"}
        result = recommend_skills_for_task(task)

        assert isinstance(result, list)

    def test_with_none_task(self) -> None:
        """Should return empty list for None task."""
        result = recommend_skills_for_task(None)
        assert result == []

    def test_with_empty_dict(self) -> None:
        """Should return always-apply skills for empty dict."""
        result = recommend_skills_for_task({})
        assert isinstance(result, list)
