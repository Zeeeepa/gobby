"""
Type definitions and data classes for Codex adapter.

Target types to migrate from codex.py:
- Dataclasses for API request/response models
- TypedDicts for structured data
- Enums for status codes and modes

Dependencies to analyze:
- pydantic (if used for validation)
- typing (TypedDict, Protocol, etc.)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Placeholder - types will be migrated from codex.py
__all__: list[str] = []
