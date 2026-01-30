"""Unit tests for PromptLoader."""

import tempfile
from pathlib import Path

import pytest

from gobby.prompts import PromptLoader, PromptTemplate

pytestmark = pytest.mark.unit

class TestPromptLoader:
    """Tests for PromptLoader class."""

    def test_load_from_bundled_defaults(self) -> None:
        """Test loading prompt from bundled defaults directory."""
        loader = PromptLoader()

        # Should find the bundled expansion/system template
        template = loader.load("expansion/system")

        assert template is not None
        assert template.name == "expansion/system"
        assert "senior technical project manager" in template.content
        assert template.source_path is not None

    def test_load_from_fallback(self) -> None:
        """Test loading prompt from registered fallback."""
        loader = PromptLoader()
        fallback_content = "This is the fallback content"

        # Register a fallback for a non-existent template
        loader.register_fallback("test/nonexistent", lambda: fallback_content)

        template = loader.load("test/nonexistent")

        assert template is not None
        assert template.content == fallback_content
        assert template.source_path is None

    def test_load_file_not_found(self) -> None:
        """Test that FileNotFoundError is raised for non-existent templates."""
        loader = PromptLoader()

        with pytest.raises(FileNotFoundError, match="Prompt template not found"):
            loader.load("completely/nonexistent/path")

    def test_render_with_jinja2_variables(self) -> None:
        """Test rendering template with Jinja2 variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test template
            prompts_dir = Path(tmpdir) / ".gobby" / "prompts"
            prompts_dir.mkdir(parents=True)

            template_content = """---
name: test-template
description: Test template
variables:
  name:
    type: str
    default: "World"
---
Hello, {{ name }}!"""

            (prompts_dir / "test.md").write_text(template_content)

            loader = PromptLoader(project_dir=Path(tmpdir))
            result = loader.render("test", {"name": "Claude"})

            assert result == "Hello, Claude!"

    def test_render_with_defaults(self) -> None:
        """Test rendering uses default values from frontmatter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts_dir = Path(tmpdir) / ".gobby" / "prompts"
            prompts_dir.mkdir(parents=True)

            template_content = """---
name: test-template
variables:
  greeting:
    type: str
    default: "Hello"
  name:
    type: str
    default: "World"
---
{{ greeting }}, {{ name }}!"""

            (prompts_dir / "greet.md").write_text(template_content)

            loader = PromptLoader(project_dir=Path(tmpdir))
            result = loader.render("greet", {})

            assert result == "Hello, World!"

    def test_render_with_conditionals(self) -> None:
        """Test rendering with Jinja2 conditionals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts_dir = Path(tmpdir) / ".gobby" / "prompts"
            prompts_dir.mkdir(parents=True)

            template_content = """---
name: conditional-test
variables:
  show_extra:
    type: bool
    default: false
---
Base content.
{% if show_extra %}
Extra content here.
{% endif %}"""

            (prompts_dir / "conditional.md").write_text(template_content)

            loader = PromptLoader(project_dir=Path(tmpdir))

            # Test with show_extra=False (default)
            result_false = loader.render("conditional", {"show_extra": False})
            assert "Base content." in result_false
            assert "Extra content here." not in result_false

            # Test with show_extra=True
            result_true = loader.render("conditional", {"show_extra": True})
            assert "Base content." in result_true
            assert "Extra content here." in result_true

    def test_precedence_project_over_global(self) -> None:
        """Test that project templates take precedence over global."""
        with tempfile.TemporaryDirectory() as project_dir:
            with tempfile.TemporaryDirectory() as global_dir:
                # Create global template
                global_prompts = Path(global_dir) / "prompts"
                global_prompts.mkdir(parents=True)
                (global_prompts / "test.md").write_text("Global version")

                # Create project template
                project_prompts = Path(project_dir) / ".gobby" / "prompts"
                project_prompts.mkdir(parents=True)
                (project_prompts / "test.md").write_text("Project version")

                loader = PromptLoader(project_dir=Path(project_dir), global_dir=Path(global_dir))
                template = loader.load("test")

                assert template.content == "Project version"

    def test_cache_behavior(self) -> None:
        """Test that templates are cached after first load."""
        loader = PromptLoader()

        # First load
        template1 = loader.load("expansion/system")
        # Second load should return cached version
        template2 = loader.load("expansion/system")

        assert template1 is template2

        # Clear cache
        loader.clear_cache()
        template3 = loader.load("expansion/system")

        # After clear, should be different object
        assert template1 is not template3

    def test_list_templates(self) -> None:
        """Test listing available templates."""
        loader = PromptLoader()

        # List all templates
        all_templates = loader.list_templates()

        assert len(all_templates) > 0
        assert "expansion/system" in all_templates
        assert "expansion/user" in all_templates

        # List filtered by category
        expansion_templates = loader.list_templates(category="expansion")

        assert all(t.startswith("expansion/") for t in expansion_templates)

    def test_exists(self) -> None:
        """Test checking if template exists."""
        loader = PromptLoader()

        assert loader.exists("expansion/system") is True
        assert loader.exists("nonexistent/path") is False

        # Register fallback
        loader.register_fallback("test/fallback", lambda: "content")
        assert loader.exists("test/fallback") is True

    def test_frontmatter_parsing(self) -> None:
        """Test YAML frontmatter parsing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts_dir = Path(tmpdir) / ".gobby" / "prompts"
            prompts_dir.mkdir(parents=True)

            template_content = """---
name: test-template
description: A test template
version: "2.0"
variables:
  required_var:
    type: str
    required: true
    description: A required variable
  optional_var:
    type: int
    default: 42
---
Template content: {{ required_var }}"""

            (prompts_dir / "test.md").write_text(template_content)

            loader = PromptLoader(project_dir=Path(tmpdir))
            template = loader.load("test")

            assert template.name == "test"
            assert template.description == "A test template"
            assert template.version == "2.0"
            assert "required_var" in template.variables
            assert template.variables["required_var"].required is True
            assert "optional_var" in template.variables
            assert template.variables["optional_var"].default == 42


class TestPromptTemplate:
    """Tests for PromptTemplate dataclass."""

    def test_get_default_context(self) -> None:
        """Test getting default context from template."""
        from gobby.prompts.models import VariableSpec

        template = PromptTemplate(
            name="test",
            content="content",
            variables={
                "var1": VariableSpec(default="default1"),
                "var2": VariableSpec(default=42),
            },
        )

        defaults = template.get_default_context()

        assert defaults == {"var1": "default1", "var2": 42}

    def test_validate_context_required(self) -> None:
        """Test validation of required variables."""
        from gobby.prompts.models import VariableSpec

        template = PromptTemplate(
            name="test",
            content="content",
            variables={
                "required_var": VariableSpec(required=True),
                "optional_var": VariableSpec(required=False),
            },
        )

        # Missing required var
        errors = template.validate_context({})
        assert len(errors) == 1
        assert "required_var" in errors[0]

        # All required vars present
        errors = template.validate_context({"required_var": "value"})
        assert len(errors) == 0

    def test_from_frontmatter(self) -> None:
        """Test creating PromptTemplate from frontmatter."""
        frontmatter = {
            "name": "test-template",
            "description": "Test description",
            "version": "1.5",
            "variables": {
                "simple_var": "default_value",
                "complex_var": {
                    "type": "int",
                    "default": 10,
                    "description": "A complex variable",
                    "required": True,
                },
            },
        }

        template = PromptTemplate.from_frontmatter(
            name="test",
            frontmatter=frontmatter,
            content="The content",
        )

        assert template.description == "Test description"
        assert template.version == "1.5"
        assert "simple_var" in template.variables
        assert template.variables["simple_var"].default == "default_value"
        assert "complex_var" in template.variables
        assert template.variables["complex_var"].type == "int"
        assert template.variables["complex_var"].default == 10
        assert template.variables["complex_var"].required is True


class TestBundledTemplates:
    """Tests to verify all bundled default templates load correctly."""

    @pytest.mark.parametrize(
        "template_path",
        [
            "expansion/system",
            "expansion/user",
            "validation/validate",
            "validation/criteria",
            "external_validation/system",
            "external_validation/spawn",
            "external_validation/agent",
            "external_validation/external",
            "research/step",
            "features/tool_summary",
            "features/tool_summary_system",
            "features/server_description",
            "features/server_description_system",
            "features/task_description",
            "features/task_description_system",
            "features/recommend_tools",
            "features/recommend_tools_hybrid",
            "features/recommend_tools_llm",
            "features/import_mcp",
            "features/import_mcp_github",
            "features/import_mcp_search",
        ],
    )
    def test_bundled_template_loads(self, template_path: str) -> None:
        """Test that each bundled template loads without error."""
        loader = PromptLoader()
        template = loader.load(template_path)

        assert template is not None
        assert template.content != ""
        assert template.source_path is not None

    def test_expansion_system_no_tdd_mode_in_prompt(self) -> None:
        """Test that expansion/system template does not include TDD mode.

        TDD mode is now applied post-expansion via the sandwich pattern,
        not in the prompt itself.
        """
        loader = PromptLoader()

        # TDD mode is no longer in the template - it's applied post-expansion
        result = loader.render("expansion/system", {"tdd_mode": False})
        assert "TDD Mode Enabled" not in result

        # tdd_mode variable is ignored - template is the same regardless
        result_with_flag = loader.render("expansion/system", {"tdd_mode": True})
        assert "TDD Mode Enabled" not in result_with_flag
        assert result == result_with_flag
