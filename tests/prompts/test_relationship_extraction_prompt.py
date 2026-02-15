"""Tests for relationship extraction prompt template."""

from pathlib import Path

import pytest

from gobby.prompts.loader import PromptLoader

pytestmark = pytest.mark.unit

PROMPTS_DIR = (
    Path(__file__).parent.parent.parent / "src" / "gobby" / "install" / "shared" / "prompts"
)


class TestRelationshipExtractionPrompt:
    """Tests for memory/extract_relations prompt template."""

    @pytest.fixture
    def loader(self) -> PromptLoader:
        """Create a PromptLoader pointing at bundled prompts."""
        return PromptLoader(defaults_dir=PROMPTS_DIR)

    def test_prompt_file_exists(self) -> None:
        """extract_relations.md exists in the prompts directory."""
        prompt_path = PROMPTS_DIR / "memory" / "extract_relations.md"
        assert prompt_path.exists(), f"Expected {prompt_path} to exist"

    def test_prompt_loads_successfully(self, loader: PromptLoader) -> None:
        """PromptLoader can load memory/extract_relations."""
        template = loader.load("memory/extract_relations")
        assert template is not None
        assert template.content

    def test_prompt_has_apache2_attribution(self) -> None:
        """Prompt frontmatter contains Apache 2.0 attribution."""
        prompt_path = PROMPTS_DIR / "memory" / "extract_relations.md"
        content = prompt_path.read_text()
        assert "Apache-2.0" in content
        assert "mem0" in content

    def test_prompt_has_required_variables(self, loader: PromptLoader) -> None:
        """Prompt uses {{ content }} and {{ entities }} Jinja2 variables."""
        template = loader.load("memory/extract_relations")
        assert "{{ content }}" in template.content
        assert "{{ entities }}" in template.content

    def test_prompt_renders_with_variables(self, loader: PromptLoader) -> None:
        """PromptLoader.render works with content and entities variables."""
        rendered = loader.render(
            "memory/extract_relations",
            {
                "content": "Josh works on the Gobby project at Anthropic.",
                "entities": '[{"entity": "Josh", "entity_type": "person"}]',
            },
        )
        assert "Josh works on the Gobby project" in rendered

    def test_prompt_specifies_relations_output(self, loader: PromptLoader) -> None:
        """Prompt instructs output as {"relations": [...]} JSON."""
        template = loader.load("memory/extract_relations")
        assert '"relations"' in template.content
        assert "source" in template.content
        assert "relationship" in template.content
        assert "destination" in template.content
