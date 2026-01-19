"""
Persistence configuration module.

Contains storage and sync-related Pydantic config models:
- MemoryConfig: Memory system settings (injection, decay, search)
- MemorySyncConfig: Memory file sync settings (debounce, export path)

Extracted from app.py using Strangler Fig pattern for code decomposition.
"""

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "MemoryConfig",
    "MemorySyncConfig",
]


class MemoryConfig(BaseModel):
    """Memory system configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable persistent memory system",
    )
    backend: str = Field(
        default="sqlite",
        description=(
            "Storage backend for memories. Options: "
            "'sqlite' (default, local SQLite database), "
            "'null' (no persistence, for testing)"
        ),
    )
    importance_threshold: float = Field(
        default=0.7,
        description="Minimum importance score for memory injection",
    )
    decay_enabled: bool = Field(
        default=True,
        description="Enable memory importance decay over time",
    )
    decay_rate: float = Field(
        default=0.05,
        description="Importance decay rate per month",
    )
    decay_floor: float = Field(
        default=0.1,
        description="Minimum importance score after decay",
    )
    search_backend: str = Field(
        default="tfidf",
        description=(
            "Search backend for memory recall. Options: "
            "'tfidf' (default, zero-dependency local search), "
            "'text' (simple substring matching)"
        ),
    )
    auto_crossref: bool = Field(
        default=False,
        description="Automatically create cross-references between similar memories",
    )
    crossref_threshold: float = Field(
        default=0.3,
        description="Minimum similarity score to create a cross-reference (0.0-1.0)",
    )
    crossref_max_links: int = Field(
        default=5,
        description="Maximum number of cross-references to create per memory",
    )
    access_debounce_seconds: int = Field(
        default=60,
        description="Minimum seconds between access stat updates for the same memory",
    )

    @field_validator("importance_threshold", "decay_rate", "decay_floor", "crossref_threshold")
    @classmethod
    def validate_probability(cls, v: float) -> float:
        """Validate value is between 0.0 and 1.0."""
        if not (0.0 <= v <= 1.0):
            raise ValueError("Value must be between 0.0 and 1.0")
        return v

    @field_validator("crossref_max_links")
    @classmethod
    def validate_positive_links(cls, v: int) -> int:
        """Validate crossref_max_links is positive."""
        if v < 1:
            raise ValueError("crossref_max_links must be at least 1")
        return v

    @field_validator("search_backend")
    @classmethod
    def validate_search_backend(cls, v: str) -> str:
        """Validate search_backend is a supported option."""
        valid_backends = {"tfidf", "text"}
        if v not in valid_backends:
            raise ValueError(
                f"Invalid search_backend '{v}'. Must be one of: {sorted(valid_backends)}"
            )
        return v

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        """Validate backend is a supported storage option."""
        valid_backends = {"sqlite", "null"}
        if v not in valid_backends:
            raise ValueError(
                f"Invalid backend '{v}'. Must be one of: {sorted(valid_backends)}"
            )
        return v


class MemorySyncConfig(BaseModel):
    """Memory backup configuration (filesystem export).

    Note: This was previously named for "sync" but is actually a backup mechanism.
    Memories are stored in the database via MemoryBackendProtocol; this config
    controls the JSONL backup file export (for disaster recovery/migration).

    TODO: Consider renaming to MemoryBackupConfig in a future breaking change.
    """

    enabled: bool = Field(
        default=True,
        description="Enable memory synchronization to filesystem",
    )
    export_debounce: float = Field(
        default=5.0,
        description="Seconds to wait before exporting after a change",
    )
    export_path: Path = Field(
        default=Path(".gobby/memories.jsonl"),
        description="Path to the memories export file (relative to project root or absolute)",
    )

    @field_validator("export_debounce")
    @classmethod
    def validate_positive(cls, v: float) -> float:
        """Validate value is non-negative."""
        if v < 0:
            raise ValueError("Value must be non-negative")
        return v
