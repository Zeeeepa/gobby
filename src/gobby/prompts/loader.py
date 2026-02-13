"""
Prompt template loader with multi-level override support.

Implements prompt loading with precedence:
1. Database (tier precedence: project > user > bundled)
2. Project file (.gobby/prompts/)
3. Global file (~/.gobby/prompts/)
4. Bundled default (install/shared/prompts/)

When a database is configured via configure_default_loader(), DB resolution
is used first. All 13+ callers using get_default_loader() / load_prompt() /
render_prompt() automatically get DB-backed resolution without code changes.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from .models import PromptTemplate

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)

# Default location for bundled prompts (shipped in install/shared/prompts)
DEFAULTS_DIR = Path(__file__).parent.parent / "install" / "shared" / "prompts"

# Module-level default loader (configured by configure_default_loader)
_default_loader: PromptLoader | None = None


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from template content.

    Standalone function (extracted from PromptLoader method) so that
    sync.py and other modules can reuse it.

    Args:
        content: Raw file content

    Returns:
        Tuple of (frontmatter dict, body content)
    """
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


class PromptLoader:
    """Loads prompt templates from multiple sources with override precedence.

    Usage:
        loader = PromptLoader(project_dir=Path("."))
        template = loader.load("expansion/system")
        rendered = loader.render("expansion/system", {"tdd_mode": True})

    With DB:
        loader = PromptLoader(db=database, project_id="...")
        template = loader.load("expansion/system")  # checks DB first
    """

    def __init__(
        self,
        project_dir: Path | None = None,
        global_dir: Path | None = None,
        defaults_dir: Path | None = None,
        db: DatabaseProtocol | None = None,
        project_id: str | None = None,
    ):
        """Initialize the prompt loader.

        Args:
            project_dir: Project root directory (for .gobby/prompts)
            global_dir: Global config directory (defaults to ~/.gobby)
            defaults_dir: Directory for bundled defaults (auto-detected)
            db: Optional database for DB-first resolution
            project_id: Optional project ID for tier precedence
        """
        self.project_dir = project_dir
        self.global_dir = global_dir or Path.home() / ".gobby"
        self.defaults_dir = defaults_dir or DEFAULTS_DIR
        self._db = db
        self._project_id = project_id
        self._prompt_manager = None

        if db is not None:
            from gobby.storage.prompts import LocalPromptManager

            self._prompt_manager = LocalPromptManager(db)

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

        Delegates to the module-level parse_frontmatter function.

        Args:
            content: Raw file content

        Returns:
            Tuple of (frontmatter dict, body content)
        """
        return parse_frontmatter(content)

    def _load_from_db(self, path: str) -> PromptTemplate | None:
        """Try to load a template from the database.

        Args:
            path: Template path

        Returns:
            PromptTemplate if found in DB, None otherwise
        """
        if self._prompt_manager is None:
            return None

        record = self._prompt_manager.get_prompt(path, project_id=self._project_id)
        if record is not None:
            return record.to_template()

        return None

    def load(self, path: str) -> PromptTemplate:
        """Load a prompt template by path.

        Resolution order: cache → DB (tier precedence) → file search → raise.

        Args:
            path: Template path (e.g., "expansion/system")

        Returns:
            PromptTemplate instance

        Raises:
            FileNotFoundError: If template not found
        """
        # Check cache first
        if path in self._cache:
            return self._cache[path]

        # Try DB resolution first
        template = self._load_from_db(path)
        if template is not None:
            self._cache[path] = template
            logger.debug(f"Loaded prompt template '{path}' from database")
            return template

        # Fall back to file search
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
            True if template exists (DB, file, or fallback)
        """
        if self._prompt_manager is not None:
            record = self._prompt_manager.get_prompt(path, project_id=self._project_id)
            if record is not None:
                return True
        return self._find_template_file(path) is not None

    def list_templates(self, category: str | None = None) -> list[str]:
        """List available template paths.

        Returns union of DB paths and file paths.

        Args:
            category: Optional category to filter (e.g., "expansion")

        Returns:
            List of template paths
        """
        templates: set[str] = set()

        # DB templates
        if self._prompt_manager is not None:
            records = self._prompt_manager.list_prompts(
                category=category,
                project_id=self._project_id,
            )
            for record in records:
                templates.add(record.path)

        # File templates
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


def configure_default_loader(
    db: DatabaseProtocol,
    project_id: str | None = None,
) -> PromptLoader:
    """Configure the module-level default loader with DB backing.

    Clears any cached loader and creates a new one with DB resolution.
    All callers of get_default_loader() / load_prompt() / render_prompt()
    automatically get DB-backed resolution after this call.

    Args:
        db: Database connection for prompt storage.
        project_id: Optional project ID for tier precedence.

    Returns:
        The newly configured PromptLoader.
    """
    global _default_loader
    _default_loader = PromptLoader(db=db, project_id=project_id)
    return _default_loader


def get_default_loader() -> PromptLoader:
    """Get or create the default prompt loader.

    Returns:
        Cached PromptLoader instance (DB-backed if configured)
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptLoader()
    return _default_loader


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
