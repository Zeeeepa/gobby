"""Tests for skill search functionality."""

import pytest

from gobby.skills.search import SkillSearch, SkillSearchResult
from gobby.storage.skills import Skill


@pytest.fixture
def sample_skills():
    """Create sample skills for testing."""
    return [
        Skill(
            id="skl-commit",
            name="commit-message",
            description="Generate conventional commit messages",
            content="# Commit Messages\n\nInstructions...",
            metadata={
                "skillport": {
                    "category": "git",
                    "tags": ["git", "commits", "workflow"],
                }
            },
        ),
        Skill(
            id="skl-review",
            name="code-review",
            description="Perform thorough code reviews",
            content="# Code Review\n\nGuidelines...",
            metadata={
                "skillport": {
                    "category": "quality",
                    "tags": ["review", "quality", "best-practices"],
                }
            },
        ),
        Skill(
            id="skl-test",
            name="test-writing",
            description="Write comprehensive unit tests",
            content="# Testing\n\nTest patterns...",
            metadata={
                "skillport": {
                    "category": "testing",
                    "tags": ["testing", "unit-tests", "quality"],
                }
            },
        ),
        Skill(
            id="skl-git",
            name="git-workflow",
            description="Best practices for git branching and merging",
            content="# Git Workflow\n\nStrategies...",
            metadata={
                "skillport": {
                    "category": "git",
                    "tags": ["git", "branching", "workflow"],
                }
            },
        ),
    ]


class TestSkillSearchResult:
    """Tests for SkillSearchResult dataclass."""

    def test_creation(self):
        """Test creating a search result."""
        result = SkillSearchResult(
            skill_id="skl-test",
            skill_name="test-skill",
            similarity=0.85,
        )

        assert result.skill_id == "skl-test"
        assert result.skill_name == "test-skill"
        assert result.similarity == 0.85

    def test_to_dict(self):
        """Test converting to dictionary."""
        result = SkillSearchResult(
            skill_id="skl-test",
            skill_name="test-skill",
            similarity=0.75,
        )

        d = result.to_dict()
        assert d["skill_id"] == "skl-test"
        assert d["skill_name"] == "test-skill"
        assert d["similarity"] == 0.75


class TestSkillSearch:
    """Tests for SkillSearch class."""

    def test_index_empty_skills(self):
        """Test indexing empty skill list."""
        search = SkillSearch()
        search.index_skills([])

        assert not search._indexed
        assert search.search("query") == []

    def test_index_skills(self, sample_skills):
        """Test indexing skills."""
        search = SkillSearch()
        search.index_skills(sample_skills)

        assert search._indexed
        assert len(search._skill_names) == 4

    def test_search_by_name(self, sample_skills):
        """Test searching by skill name."""
        search = SkillSearch()
        search.index_skills(sample_skills)

        results = search.search("commit", top_k=5)

        assert len(results) > 0
        assert results[0].skill_name == "commit-message"
        assert results[0].similarity > 0

    def test_search_by_description(self, sample_skills):
        """Test searching by description content."""
        search = SkillSearch()
        search.index_skills(sample_skills)

        results = search.search("unit tests", top_k=5)

        assert len(results) > 0
        # test-writing skill mentions "unit tests"
        skill_names = [r.skill_name for r in results]
        assert "test-writing" in skill_names

    def test_search_by_tags(self, sample_skills):
        """Test searching by tag content."""
        search = SkillSearch()
        search.index_skills(sample_skills)

        results = search.search("workflow", top_k=5)

        assert len(results) > 0
        # Both commit-message and git-workflow have "workflow" tag
        skill_names = [r.skill_name for r in results]
        assert any("workflow" in name or "commit" in name for name in skill_names)

    def test_search_by_category(self, sample_skills):
        """Test searching by category."""
        search = SkillSearch()
        search.index_skills(sample_skills)

        results = search.search("git", top_k=5)

        assert len(results) > 0
        # Both commit-message and git-workflow have "git" category
        skill_names = [r.skill_name for r in results]
        assert "git-workflow" in skill_names or "commit-message" in skill_names

    def test_search_returns_top_k(self, sample_skills):
        """Test that search respects top_k limit."""
        search = SkillSearch()
        search.index_skills(sample_skills)

        results = search.search("quality", top_k=2)

        assert len(results) <= 2

    def test_search_results_ranked_by_similarity(self, sample_skills):
        """Test that results are sorted by similarity descending."""
        search = SkillSearch()
        search.index_skills(sample_skills)

        results = search.search("code review quality", top_k=5)

        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].similarity >= results[i + 1].similarity

    def test_search_no_results(self, sample_skills):
        """Test search with no matching results."""
        search = SkillSearch()
        search.index_skills(sample_skills)

        results = search.search("xyznonexistent123", top_k=5)

        # May return empty or low-similarity results
        assert isinstance(results, list)

    def test_search_before_index(self):
        """Test searching before indexing returns empty."""
        search = SkillSearch()
        results = search.search("test")

        assert results == []

    def test_add_skill_marks_update(self, sample_skills):
        """Test that add_skill increments pending updates."""
        search = SkillSearch()
        search.index_skills(sample_skills)
        assert search._pending_updates == 0

        new_skill = Skill(
            id="skl-new",
            name="new-skill",
            description="A new skill",
            content="Content",
        )
        search.add_skill(new_skill)

        assert search._pending_updates == 1
        assert search._skill_names["skl-new"] == "new-skill"

    def test_update_skill_marks_update(self, sample_skills):
        """Test that update_skill increments pending updates."""
        search = SkillSearch()
        search.index_skills(sample_skills)

        updated_skill = sample_skills[0]
        updated_skill.name = "updated-name"
        search.update_skill(updated_skill)

        assert search._pending_updates == 1

    def test_remove_skill_marks_update(self, sample_skills):
        """Test that remove_skill increments pending updates."""
        search = SkillSearch()
        search.index_skills(sample_skills)

        search.remove_skill("skl-commit")

        assert search._pending_updates == 1
        assert "skl-commit" not in search._skill_names

    def test_needs_reindex_after_threshold(self, sample_skills):
        """Test that needs_reindex returns True after threshold updates."""
        search = SkillSearch(refit_threshold=3)
        search.index_skills(sample_skills)

        assert not search.needs_reindex()

        new_skill = Skill(
            id="skl-1", name="skill-1", description="Desc", content="C"
        )
        search.add_skill(new_skill)
        assert not search.needs_reindex()

        search.add_skill(new_skill)
        assert not search.needs_reindex()

        search.add_skill(new_skill)
        assert search.needs_reindex()

    def test_needs_reindex_before_indexing(self):
        """Test that needs_reindex returns True before any indexing."""
        search = SkillSearch()
        assert search.needs_reindex()

    def test_get_stats(self, sample_skills):
        """Test getting search statistics."""
        search = SkillSearch()
        search.index_skills(sample_skills)

        stats = search.get_stats()

        assert stats["indexed"] is True
        assert stats["skill_count"] == 4
        assert stats["pending_updates"] == 0
        assert "refit_threshold" in stats

    def test_clear(self, sample_skills):
        """Test clearing the search index."""
        search = SkillSearch()
        search.index_skills(sample_skills)
        assert search._indexed

        search.clear()

        assert not search._indexed
        assert len(search._skill_names) == 0
        assert search._pending_updates == 0

    def test_custom_parameters(self, sample_skills):
        """Test creating search with custom parameters."""
        search = SkillSearch(
            ngram_range=(1, 3),
            max_features=1000,
            min_df=1,
            refit_threshold=5,
        )
        search.index_skills(sample_skills)

        stats = search.get_stats()
        assert stats["ngram_range"] == (1, 3)
        assert stats["max_features"] == 1000
        assert stats["refit_threshold"] == 5


class TestSkillSearchIntegration:
    """Integration tests for skill search with realistic scenarios."""

    def test_search_multiple_fields_combined(self, sample_skills):
        """Test that search considers all indexed fields."""
        search = SkillSearch()
        search.index_skills(sample_skills)

        # Query that matches different fields in same skill
        results = search.search("git commit message workflow", top_k=5)

        assert len(results) > 0
        # commit-message skill matches name, tag, and category
        assert results[0].skill_id == "skl-commit"

    def test_reindex_after_updates(self, sample_skills):
        """Test reindexing after multiple updates."""
        search = SkillSearch(refit_threshold=2)
        search.index_skills(sample_skills)

        # Add skills to trigger reindex threshold
        for i in range(3):
            skill = Skill(
                id=f"skl-new-{i}",
                name=f"new-skill-{i}",
                description="New description",
                content="Content",
            )
            search.add_skill(skill)

        assert search.needs_reindex()

        # Re-index with updated list
        updated_skills = sample_skills + [
            Skill(
                id="skl-new-0",
                name="new-skill-0",
                description="Findable description about databases",
                content="Content",
            )
        ]
        search.index_skills(updated_skills)

        # Should find the new skill
        results = search.search("databases", top_k=5)
        skill_names = [r.skill_name for r in results]
        assert "new-skill-0" in skill_names
