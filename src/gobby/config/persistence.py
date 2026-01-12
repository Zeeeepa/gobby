"""
Persistence configuration module.

Contains storage and sync-related Pydantic config models:
- MemoryConfig: Memory system settings (injection, decay, search)
- MemorySyncConfig: Memory file sync settings (stealth mode, debounce)

Extracted from app.py using Strangler Fig pattern for code decomposition.
"""

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
    injection_limit: int = Field(
        default=10,
        description="Maximum number of memories to inject per session",
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
    semantic_search_enabled: bool = Field(
        default=True,
        description="Use semantic (embedding-based) search for memory recall",
    )
    search_backend: str = Field(
        default="tfidf",
        description=(
            "Search backend for memory recall. Options: "
            "'tfidf' (default, zero-dependency local search), "
            "'openai' (embedding-based semantic search), "
            "'hybrid' (combines TF-IDF + OpenAI with RRF), "
            "'text' (simple substring matching)"
        ),
    )
    embedding_provider: str = Field(
        default="openai",
        description="Provider for embedding generation (openai, litellm)",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Model to use for memory embedding generation",
    )
    auto_embed: bool = Field(
        default=True,
        description="Automatically generate embeddings when memories are created",
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

    @field_validator("injection_limit")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        """Validate value is non-negative."""
        if v < 0:
            raise ValueError("Value must be non-negative")
        return v

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
        valid_backends = {"tfidf", "openai", "hybrid", "text"}
        if v not in valid_backends:
            raise ValueError(
                f"Invalid search_backend '{v}'. Must be one of: {sorted(valid_backends)}"
            )
        return v


class MemorySyncConfig(BaseModel):
    """Memory synchronization configuration (Git sync)."""

    enabled: bool = Field(
        default=True,
        description="Enable memory synchronization to filesystem",
    )
    export_debounce: float = Field(
        default=5.0,
        description="Seconds to wait before exporting after a change",
    )

    @field_validator("export_debounce")
    @classmethod
    def validate_positive(cls, v: float) -> float:
        """Validate value is non-negative."""
        if v < 0:
            raise ValueError("Value must be non-negative")
        return v
