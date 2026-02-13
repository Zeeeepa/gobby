"""
Prompt template loading and rendering system.

Provides externalized prompt management with:
- YAML frontmatter for metadata
- Jinja2 templating for dynamic content
- Multi-level override precedence (project → global → bundled → fallback)
"""

from .loader import PromptLoader, configure_default_loader, parse_frontmatter
from .models import PromptTemplate, VariableSpec

__all__ = [
    "PromptLoader",
    "PromptTemplate",
    "VariableSpec",
    "configure_default_loader",
    "parse_frontmatter",
]
