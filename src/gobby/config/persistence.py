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
    "Mem0Config",
    "MemUConfig",
    "OpenMemoryConfig",
]


class Mem0Config(BaseModel):
    """Mem0 backend configuration.

    Configure this section when using backend: 'mem0' for cloud-based
    semantic memory storage via the Mem0 AI service (mem0ai package).

    Requires: pip install mem0ai
    """

    api_key: str | None = Field(
        default=None,
        description="Mem0 API key for authentication (required when backend='mem0')",
    )
    user_id: str | None = Field(
        default=None,
        description="Default user ID for memories (optional, defaults to 'default')",
    )
    org_id: str | None = Field(
        default=None,
        description="Organization ID for multi-tenant use (optional)",
    )


class MemUConfig(BaseModel):
    """MemU backend configuration.

    Configure this section when using backend: 'memu' for structured
    memory storage via the MemU SDK (NevaMind-AI/memU via memu-py).

    Requires: pip install memu-py
    """

    database_type: str = Field(
        default="inmemory",
        description="Database type: 'inmemory', 'sqlite', or 'postgres'",
    )
    database_url: str | None = Field(
        default=None,
        description="Database connection URL (for sqlite/postgres)",
    )
    llm_api_key: str | None = Field(
        default=None,
        description="LLM API key for embeddings (optional, uses OpenAI by default)",
    )
    llm_base_url: str | None = Field(
        default=None,
        description="LLM API base URL (optional)",
    )
    user_id: str | None = Field(
        default=None,
        description="Default user ID for memories (optional)",
    )


class OpenMemoryConfig(BaseModel):
    """OpenMemory backend configuration.

    Configure this section when using backend: 'openmemory' for self-hosted
    embedding-based memory storage via the OpenMemory REST API.

    OpenMemory provides semantic search over memories using local embeddings.
    """

    base_url: str = Field(
        default="http://localhost:8080",
        description="OpenMemory server base URL (required when backend='openmemory')",
    )
    api_key: str | None = Field(
        default=None,
        description="Optional API key for authentication",
    )
    user_id: str | None = Field(
        default=None,
        description="Default user ID for memories (optional, defaults to 'default')",
    )

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate base_url is a valid URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        # Remove trailing slash for consistency
        return v.rstrip("/")


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
            "'mem0' (Mem0 cloud-based semantic memory via mem0ai), "
            "'memu' (MemU structured memory via memu-py), "
            "'openmemory' (self-hosted OpenMemory REST API), "
            "'null' (no persistence, for testing)"
        ),
    )
    mem0: Mem0Config = Field(
        default_factory=Mem0Config,
        description="Mem0 backend configuration (only used when backend='mem0')",
    )
    memu: MemUConfig = Field(
        default_factory=MemUConfig,
        description="MemU backend configuration (only used when backend='memu')",
    )
    openmemory: OpenMemoryConfig = Field(
        default_factory=OpenMemoryConfig,
        description="OpenMemory backend configuration (only used when backend='openmemory')",
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
        valid_backends = {"sqlite", "mem0", "memu", "openmemory", "null"}
        if v not in valid_backends:
            raise ValueError(f"Invalid backend '{v}'. Must be one of: {sorted(valid_backends)}")
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
