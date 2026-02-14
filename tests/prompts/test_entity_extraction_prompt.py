"""Tests for entity extraction prompt template."""

from pathlib import Path

import pytest

from gobby.prompts.loader import PromptLoader

pytestmark = pytest.mark.unit

PROMPTS_DIR = Path(__file__).parent.parent.parent / "src" / "gobby" / "install" / "shared" / "prompts"


class TestEntityExtractionPrompt:
    """Tests for memory/extract_entities prompt template."""

    @pytest.fixture
    def loader(self) -> PromptLoader:
        """Create a PromptLoader pointing at bundled prompts."""
        return PromptLoader(defaults_dir=PROMPTS_DIR)

    def test_prompt_file_exists(self) -> None:
        """extract_entities.md exists in the prompts directory."""
        prompt_path = PROMPTS_DIR / "memory" / "extract_entities.md"
        assert prompt_path.exists(), f"Expected {prompt_path} to exist"

    def test_prompt_loads_successfully(self, loader: PromptLoader) -> None:
        """PromptLoader can load memory/extract_entities."""
        template = loader.load("memory/extract_entities")
        assert template is not None
        assert template.content

    def test_prompt_has_apache2_attribution(self) -> None:
        """Prompt frontmatter contains Apache 2.0 attribution."""
        prompt_path = PROMPTS_DIR / "memory" / "extract_entities.md"
        content = prompt_path.read_text()
        assert "Apache-2.0" in content
        assert "mem0" in content

    def test_prompt_has_content_variable(self, loader: PromptLoader) -> None:
        """Prompt uses {{ content }} Jinja2 variable."""
        template = loader.load("memory/extract_entities")
        assert "content" in template.variables or "{{ content }}" in template.content

    def test_prompt_renders_with_content(self, loader: PromptLoader) -> None:
        """PromptLoader.render works with content variable."""
        rendered = loader.render(
            "memory/extract_entities",
            {"content": "Josh uses Python 3.13 for the Gobby project."},
        )
        assert "Josh uses Python 3.13" in rendered

    def test_prompt_specifies_entities_output(self, loader: PromptLoader) -> None:
        """Prompt instructs output as {"entities": [...]} JSON with entity_type."""
        template = loader.load("memory/extract_entities")
        assert '"entities"' in template.content
        assert "entity_type" in template.content

    def test_prompt_mentions_entity_types(self, loader: PromptLoader) -> None:
        """Prompt mentions common entity types like person, organization, tool."""
        template = loader.load("memory/extract_entities")
        assert "person" in template.content.lower()
        assert "organization" in template.content.lower()
        assert "tool" in template.content.lower()
