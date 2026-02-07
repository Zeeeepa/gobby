"""Tests for inject_context with source='skills'.

Covers the happy path (skills found and formatted) and the
skill_manager-is-None early-return path.
"""

from unittest.mock import MagicMock

import pytest

from gobby.workflows.context_actions import inject_context

pytestmark = pytest.mark.unit


def _make_skill(
    name: str,
    description: str = "",
    always_apply: bool = False,
    injection_format: str = "summary",
    content: str = "",
) -> MagicMock:
    """Helper to build a mock ParsedSkill."""
    skill = MagicMock()
    skill.name = name
    skill.description = description
    skill.is_always_apply.return_value = always_apply
    skill.injection_format = injection_format
    skill.content = content
    return skill


@pytest.fixture
def mock_skill_manager():
    """Create a mock skill manager with discover_core_skills."""
    manager = MagicMock()
    skill1 = _make_skill("commit", "Create git commits")
    skill2 = _make_skill("review-pr", "Review pull requests", always_apply=True)
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


def test_format_skills_full_injection_format(base_args):
    """Skills with injection_format='full' include their full content body."""
    manager = MagicMock()
    skill = _make_skill(
        "proactive-memory",
        "Guidelines for saving memories",
        always_apply=True,
        injection_format="full",
        content="# Proactive Memory\n\nSave insights immediately.",
    )
    manager.discover_core_skills.return_value = [skill]

    result = inject_context(
        **base_args,
        source="skills",
        skill_manager=manager,
    )

    assert result is not None
    content = result["inject_context"]
    assert "### proactive-memory" in content
    assert "Guidelines for saving memories" in content
    assert "# Proactive Memory" in content
    assert "Save insights immediately." in content
    # Full-format skills should NOT appear under Available Skills heading
    assert "## Available Skills" not in content


def test_format_skills_content_injection_format(base_args):
    """Skills with injection_format='content' inject raw content only."""
    manager = MagicMock()
    skill = _make_skill(
        "raw-skill",
        "Some description",
        injection_format="content",
        content="Raw content block here.",
    )
    manager.discover_core_skills.return_value = [skill]

    result = inject_context(
        **base_args,
        source="skills",
        skill_manager=manager,
    )

    assert result is not None
    content = result["inject_context"]
    assert "Raw content block here." in content
    # Content-format skills should NOT have name/description wrappers
    assert "### raw-skill" not in content
    assert "Some description" not in content
    assert "## Available Skills" not in content


def test_format_skills_mixed_formats(base_args):
    """Mixed injection formats: summary skills grouped, full/content separate."""
    manager = MagicMock()
    summary_skill = _make_skill("commit", "Create git commits")
    full_skill = _make_skill(
        "proactive-memory",
        "Guidelines for saving memories",
        injection_format="full",
        content="Save insights when discovered.",
    )
    content_skill = _make_skill(
        "raw-inject",
        "Ignored description",
        injection_format="content",
        content="Injected raw block.",
    )
    manager.discover_core_skills.return_value = [
        summary_skill,
        full_skill,
        content_skill,
    ]

    result = inject_context(
        **base_args,
        source="skills",
        skill_manager=manager,
    )

    assert result is not None
    content = result["inject_context"]
    # Summary skill under Available Skills
    assert "## Available Skills" in content
    assert "- **commit**: Create git commits" in content
    # Full skill has heading + content
    assert "### proactive-memory" in content
    assert "Save insights when discovered." in content
    # Content skill is raw
    assert "Injected raw block." in content
    assert "### raw-inject" not in content
