"""Tests for inject_context with source='skills'.

Covers the happy path (skills found and formatted) and the
skill_manager-is-None early-return path.
"""

from unittest.mock import MagicMock

import pytest

from gobby.workflows.context_actions import inject_context

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_skill_manager():
    """Create a mock skill manager with discover_core_skills."""
    manager = MagicMock()
    skill1 = MagicMock()
    skill1.name = "commit"
    skill1.description = "Create git commits"
    skill1.is_always_apply.return_value = False

    skill2 = MagicMock()
    skill2.name = "review-pr"
    skill2.description = "Review pull requests"
    skill2.is_always_apply.return_value = True

    manager.discover_core_skills.return_value = [skill1, skill2]
    return manager


@pytest.fixture
def base_args():
    """Common arguments for inject_context calls."""
    return {
        "session_manager": MagicMock(),
        "session_id": "test-session",
        "state": MagicMock(),
        "template_engine": MagicMock(),
    }


def test_inject_context_skills_happy_path(base_args, mock_skill_manager):
    """inject_context with source='skills' returns formatted skills."""
    result = inject_context(
        **base_args,
        source="skills",
        skill_manager=mock_skill_manager,
    )

    assert result is not None
    content = result["inject_context"]
    assert "## Available Skills" in content
    assert "commit" in content
    assert "Create git commits" in content
    assert "review-pr" in content
    mock_skill_manager.discover_core_skills.assert_called_once()


def test_inject_context_skills_none_skill_manager(base_args):
    """inject_context with source='skills' returns None when skill_manager is None."""
    result = inject_context(
        **base_args,
        source="skills",
        skill_manager=None,
    )

    assert result is None


def test_inject_context_skills_filter_always_apply(base_args, mock_skill_manager):
    """inject_context with filter='always_apply' only includes always-apply skills."""
    result = inject_context(
        **base_args,
        source="skills",
        skill_manager=mock_skill_manager,
        filter="always_apply",
    )

    assert result is not None
    content = result["inject_context"]
    assert "review-pr" in content
    # commit has is_always_apply=False, so it should be filtered out
    assert "commit" not in content


def test_inject_context_skills_empty_list(base_args):
    """inject_context returns None when skill_manager returns no skills."""
    manager = MagicMock()
    manager.discover_core_skills.return_value = []

    result = inject_context(
        **base_args,
        source="skills",
        skill_manager=manager,
    )

    assert result is None
