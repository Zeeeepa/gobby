"""
Persistence configuration module.

Contains storage and sync-related Pydantic config models:
- MemoryConfig: Memory system settings (injection, decay, search)
- MemorySyncConfig: Memory file sync settings (debounce, export path)

Extracted from app.py using Strangler Fig pattern for code decomposition.
"""

import logging
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

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
        default="local",
        description=(
            "Storage backend for memories. Options: "
            "'local' (default, direct SQLite via LocalMemoryManager), "
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
        default="auto",
        description=(
            "Search backend for memory recall. Options: "
            "'auto' (default, tries embeddings then falls back to TF-IDF), "
            "'tfidf' (zero-dependency local search), "
            "'text' (simple substring matching), "
            "'embedding' (semantic search via embeddings), "
            "'hybrid' (combined TF-IDF + embedding scores)"
        ),
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model for semantic search (used in auto/embedding/hybrid modes)",
    )
    embedding_weight: float = Field(
        default=0.6,
        description="Weight for embedding score in hybrid search (0.0-1.0)",
    )
    tfidf_weight: float = Field(
        default=0.4,
        description="Weight for TF-IDF score in hybrid search (0.0-1.0)",
    )
    mem0_url: str | None = Field(
        default=None,
        description=(
            "Mem0 REST API URL for cloud-based memory sync. "
            "None means standalone mode (local-only). "
            "Example: 'https://api.mem0.ai' or 'http://localhost:8888'"
        ),
    )
    mem0_api_key: str | None = Field(
        default=None,
        description=(
            "Mem0 API key for authentication. "
            "Supports ${ENV_VAR} pattern for env var expansion at load time."
        ),
    )
    mem0_timeout: float = Field(
        default=90.0,
        description="Timeout in seconds for mem0 API requests (includes embedding generation).",
    )
    neo4j_url: str | None = Field(
        default=None,
        description=(
            "Neo4j HTTP API URL for knowledge graph visualization. "
            "Example: 'http://localhost:7474' or 'http://localhost:8474'"
        ),
    )
    neo4j_auth: str | None = Field(
        default=None,
        description=(
            "Neo4j authentication in 'user:password' format. "
            "Supports ${ENV_VAR} pattern for env var expansion at load time."
        ),
    )
    neo4j_database: str = Field(
        default="neo4j",
        description="Neo4j database name",
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
    mem0_sync_interval: float = Field(
        default=10.0,
        description="Seconds between Mem0 background sync attempts",
    )
    mem0_sync_max_backoff: float = Field(
        default=300.0,
        description="Maximum backoff seconds on Mem0 connection failure",
    )

    @field_validator("mem0_sync_interval")
    @classmethod
    def validate_sync_interval(cls, v: float) -> float:
        """Validate mem0_sync_interval is positive."""
        if v <= 0:
            raise ValueError("mem0_sync_interval must be greater than 0")
        return v

    @field_validator(
        "importance_threshold",
        "decay_rate",
        "decay_floor",
        "crossref_threshold",
        "embedding_weight",
        "tfidf_weight",
    )
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

    @field_validator("mem0_timeout")
    @classmethod
    def validate_mem0_timeout(cls, v: float) -> float:
        """Validate mem0_timeout is positive."""
        if v <= 0:
            raise ValueError("mem0_timeout must be greater than 0")
        return v

    @field_validator("search_backend")
    @classmethod
    def validate_search_backend(cls, v: str) -> str:
        """Validate search_backend is a supported option."""
        valid_backends = {"tfidf", "text", "embedding", "auto", "hybrid"}
        if v not in valid_backends:
            raise ValueError(
                f"Invalid search_backend '{v}'. Must be one of: {sorted(valid_backends)}"
            )
        return v

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        """Validate backend is a supported storage option."""
        # Accept "sqlite" as backwards-compat alias for "local"
        if v == "sqlite":
            return "local"
        valid_backends = {"local", "null"}
        if v not in valid_backends:
            raise ValueError(f"Invalid backend '{v}'. Must be one of: {sorted(valid_backends)}")
        return v

    @model_validator(mode="after")
    def validate_hybrid_weights(self) -> "MemoryConfig":
        """Warn if embedding_weight + tfidf_weight don't sum to ~1.0."""
        total = self.embedding_weight + self.tfidf_weight
        if abs(total - 1.0) > 0.01:
            logger.warning(
                f"embedding_weight ({self.embedding_weight}) + tfidf_weight ({self.tfidf_weight}) "
                f"= {total}, expected ~1.0"
            )
        return self

    @model_validator(mode="after")
    def validate_sync_backoff(self) -> "MemoryConfig":
        """Validate mem0_sync_max_backoff >= mem0_sync_interval."""
        if self.mem0_sync_max_backoff < self.mem0_sync_interval:
            raise ValueError(
                f"mem0_sync_max_backoff ({self.mem0_sync_max_backoff}) must be >= "
                f"mem0_sync_interval ({self.mem0_sync_interval})"
            )
        return self


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
