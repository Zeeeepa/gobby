"""
Prompt template loading and rendering system.

Provides externalized prompt management with:
- YAML frontmatter for metadata
- Jinja2 templating for dynamic content
- Multi-level override precedence (project → global → bundled → fallback)
"""

from .loader import PromptLoader
from .models import PromptTemplate, VariableSpec

__all__ = ["PromptLoader", "PromptTemplate", "VariableSpec"]
