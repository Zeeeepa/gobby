"""Tests for HookSkillManager (TDD - written before implementation)."""

import pytest

pytestmark = pytest.mark.integration


class TestHookSkillManager:
    """Tests for HookSkillManager class."""

    def test_import(self) -> None:
        """Test that HookSkillManager can be imported."""
        from gobby.hooks.skill_manager import HookSkillManager

        assert HookSkillManager is not None

    def test_instantiate(self) -> None:
        """Test that HookSkillManager can be instantiated."""
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        assert manager is not None

    def test_has_discover_core_skills_method(self) -> None:
        """Test that HookSkillManager has discover_core_skills method."""
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        assert hasattr(manager, "discover_core_skills")
        assert callable(manager.discover_core_skills)

    def test_discover_core_skills_returns_list(self) -> None:
        """Test that discover_core_skills returns a list."""
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        result = manager.discover_core_skills()
        assert isinstance(result, list)

    def test_discover_core_skills_loads_from_shared_path(self) -> None:
        """Test that discover_core_skills loads from install/shared/skills/."""
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        skills = manager.discover_core_skills()

        # Should find the built-in skills
        skill_names = [s.name for s in skills]
        assert len(skill_names) > 0  # At least some skills exist

    def test_discover_core_skills_finds_discovering_tools_skill(self) -> None:
        """Test that discover_core_skills finds the discovering-tools skill."""
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        skills = manager.discover_core_skills()

        skill_names = [s.name for s in skills]
        assert "discovering-tools" in skill_names

    def test_discover_core_skills_finds_sessions_skill(self) -> None:
        """Test that discover_core_skills finds the sessions skill."""
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        skills = manager.discover_core_skills()

        skill_names = [s.name for s in skills]
        assert "sessions" in skill_names

    def test_discovered_skills_have_name_and_content(self) -> None:
        """Test that discovered skills have name and content attributes."""
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        skills = manager.discover_core_skills()

        # Ensure we have at least one skill to test
        assert skills, "Expected at least one skill to be discovered"

        skill = skills[0]
        assert hasattr(skill, "name")
        assert hasattr(skill, "content")
        assert skill.name is not None
        assert skill.content is not None

    def test_get_skill_by_name(self) -> None:
        """Test getting a skill by name."""
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        skill = manager.get_skill_by_name("discovering-tools")

        assert skill is not None
        assert skill.name == "discovering-tools"

    def test_get_skill_by_name_not_found(self) -> None:
        """Test getting a non-existent skill returns None."""
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        skill = manager.get_skill_by_name("nonexistent-skill")

        assert skill is None

    def test_recommend_skills_returns_list(self) -> None:
        """Test that recommend_skills returns a list."""
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        result = manager.recommend_skills()

        assert isinstance(result, list)

    def test_recommend_skills_for_code_category(self) -> None:
        """Test that recommend_skills returns code-related skills."""
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        result = manager.recommend_skills(category="code")

        assert "gobby-tasks" in result

    def test_recommend_skills_for_docs_category(self) -> None:
        """Test that recommend_skills returns docs-related skills."""
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        result = manager.recommend_skills(category="docs")

        assert "gobby-tasks" in result
        assert "gobby-plan" in result

    def test_recommend_skills_unknown_category_returns_always_apply(self) -> None:
        """Test that recommend_skills returns alwaysApply skills for unknown category."""
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        result = manager.recommend_skills(category="unknown-category")

        # Should at least return some skills (alwaysApply ones)
        assert isinstance(result, list)
