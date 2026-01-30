"""
Prompt template loader with multi-level override support.

Implements prompt loading with precedence:
1. Inline config (deprecated, for backwards compatibility)
2. Config path (explicit path in config)
3. Project file (.gobby/prompts/)
4. Global file (~/.gobby/prompts/)
5. Bundled default (src/gobby/prompts/defaults/)
6. Python constant (strangler fig fallback)
"""

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .models import PromptTemplate

logger = logging.getLogger(__name__)

# Default location for bundled prompts (in install/shared/prompts for installation)
# Falls back to src location for development if install location doesn't exist
_INSTALL_PROMPTS_DIR = Path(__file__).parent.parent / "install" / "shared" / "prompts"
_DEV_PROMPTS_DIR = Path(__file__).parent / "defaults"
DEFAULTS_DIR = _INSTALL_PROMPTS_DIR if _INSTALL_PROMPTS_DIR.exists() else _DEV_PROMPTS_DIR


class PromptLoader:
    """Loads prompt templates from multiple sources with override precedence.

    Usage:
        loader = PromptLoader(project_dir=Path("."))
        template = loader.load("expansion/system")
        rendered = loader.render("expansion/system", {"tdd_mode": True})
    """

    def __init__(
        self,
        project_dir: Path | None = None,
        global_dir: Path | None = None,
        defaults_dir: Path | None = None,
    ):
        """Initialize the prompt loader.

        Args:
            project_dir: Project root directory (for .gobby/prompts)
            global_dir: Global config directory (defaults to ~/.gobby)
            defaults_dir: Directory for bundled defaults (auto-detected)
        """
        self.project_dir = project_dir
        self.global_dir = global_dir or Path.home() / ".gobby"
        self.defaults_dir = defaults_dir or DEFAULTS_DIR

        # Build search paths in priority order
        self._search_paths: list[Path] = []
        if project_dir:
            self._search_paths.append(project_dir / ".gobby" / "prompts")
        self._search_paths.append(self.global_dir / "prompts")
        self._search_paths.append(self.defaults_dir)

        # Template cache
        self._cache: dict[str, PromptTemplate] = {}

    def clear_cache(self) -> None:
        """Clear the template cache."""
        self._cache.clear()

    def _find_template_file(self, path: str) -> Path | None:
        """Find a template file in search paths.

        Args:
            path: Template path (e.g., "expansion/system")

        Returns:
            Path to template file if found, None otherwise
        """
        # Add .md extension if not present
        if not path.endswith(".md"):
            path = f"{path}.md"

        for search_dir in self._search_paths:
            template_path = search_dir / path
            if template_path.exists():
                return template_path

        return None

    def _parse_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        """Parse YAML frontmatter from template content.

        Args:
            content: Raw file content

        Returns:
            Tuple of (frontmatter dict, body content)
        """
        # Match YAML frontmatter between --- markers
        frontmatter_pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
        match = frontmatter_pattern.match(content)

        if match:
            try:
                frontmatter = yaml.safe_load(match.group(1)) or {}
                body = content[match.end() :]
                return frontmatter, body
            except yaml.YAMLError as e:
                logger.warning(f"Failed to parse frontmatter: {e}")
                return {}, content

        return {}, content

    def load(self, path: str) -> PromptTemplate:
        """Load a prompt template by path.

        Args:
            path: Template path (e.g., "expansion/system")

        Returns:
            PromptTemplate instance

        Raises:
            FileNotFoundError: If template not found and no fallback registered
        """
        # Check cache first
        if path in self._cache:
            return self._cache[path]

        # Try to find template file
        template_file = self._find_template_file(path)

        if template_file:
            content = template_file.read_text(encoding="utf-8")
            frontmatter, body = self._parse_frontmatter(content)

            template = PromptTemplate.from_frontmatter(
                name=path,
                frontmatter=frontmatter,
                content=body.strip(),
                source_path=template_file,
            )
            self._cache[path] = template
            logger.debug(f"Loaded prompt template '{path}' from {template_file}")
            return template

        raise FileNotFoundError(f"Prompt template not found: {path}")

    def render(
        self,
        path: str,
        context: dict[str, Any] | None = None,
        strict: bool = False,
    ) -> str:
        """Load and render a template with context.

        Args:
            path: Template path
            context: Variables to inject into template
            strict: If True, raise on missing required variables

        Returns:
            Rendered template string

        Raises:
            FileNotFoundError: If template not found
            ValueError: If strict=True and required variables missing
        """
        template = self.load(path)
        ctx = template.get_default_context()

        if context:
            ctx.update(context)

        # Validate required variables
        if strict:
            errors = template.validate_context(ctx)
            if errors:
                raise ValueError(f"Template validation failed: {'; '.join(errors)}")

        # Render with Jinja2
        return self._render_jinja(template.content, ctx)

    def _render_jinja(self, template_str: str, context: dict[str, Any]) -> str:
        """Render a template string with Jinja2.

        Uses a safe subset of Jinja2 features.

        Args:
            template_str: Template content with Jinja2 syntax
            context: Context dict for rendering

        Returns:
            Rendered string
        """
        try:
            from jinja2 import Environment, StrictUndefined, UndefinedError

            # Create a restricted Jinja2 environment
            env = Environment(  # nosec B701 - generating raw text prompts, not HTML
                autoescape=False,
                undefined=StrictUndefined,
                # Disable dangerous features
                extensions=[],
            )

            # Add safe filters
            env.filters["default"] = lambda v, d="": d if v is None else v

            template = env.from_string(template_str)
            return template.render(**context)

        except UndefinedError as e:
            logger.warning(f"Template rendering error (undefined variable): {e}")
            # Fall back to simple string formatting for undefined vars
            return self._render_simple(template_str, context)
        except ImportError:
            # Jinja2 not available, use simple formatting
            logger.debug("Jinja2 not available, using simple format")
            return self._render_simple(template_str, context)
        except Exception as e:
            logger.warning(f"Template rendering error: {e}")
            return self._render_simple(template_str, context)

    def _render_simple(self, template_str: str, context: dict[str, Any]) -> str:
        """Simple string formatting fallback.

        Handles {variable} placeholders using str.format().

        Args:
            template_str: Template with {var} placeholders
            context: Context dict

        Returns:
            Rendered string
        """
        try:
            return template_str.format(**context)
        except KeyError:
            # Return as-is if formatting fails
            return template_str

    def exists(self, path: str) -> bool:
        """Check if a template exists.

        Args:
            path: Template path

        Returns:
            True if template exists (file or fallback)
        """
        return self._find_template_file(path) is not None

    def list_templates(self, category: str | None = None) -> list[str]:
        """List available template paths.

        Args:
            category: Optional category to filter (e.g., "expansion")

        Returns:
            List of template paths
        """
        templates: set[str] = set()

        for search_dir in self._search_paths:
            if not search_dir.exists():
                continue

            for md_file in search_dir.rglob("*.md"):
                rel_path = md_file.relative_to(search_dir)
                # Remove .md extension for path
                template_path = str(rel_path.with_suffix(""))

                if category is None or template_path.startswith(f"{category}/"):
                    templates.add(template_path)

        return sorted(templates)


# Module-level cached loader instance
@lru_cache(maxsize=1)
def get_default_loader() -> PromptLoader:
    """Get or create the default prompt loader.

    Returns:
        Cached PromptLoader instance
    """
    return PromptLoader()


def load_prompt(path: str) -> PromptTemplate:
    """Convenience function to load a prompt using default loader.

    Args:
        path: Template path

    Returns:
        PromptTemplate
    """
    return get_default_loader().load(path)


def render_prompt(path: str, context: dict[str, Any] | None = None) -> str:
    """Convenience function to render a prompt using default loader.

    Args:
        path: Template path
        context: Variables for rendering

    Returns:
        Rendered string
    """
    return get_default_loader().render(path, context)
