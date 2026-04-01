"""Code index configuration."""

from pydantic import BaseModel, Field


class CodeIndexConfig(BaseModel):
    """Configuration for native AST-based code indexing."""

    enabled: bool = Field(
        default=True,
        description="Enable code indexing via tree-sitter AST parsing",
    )
    auto_index_on_commit: bool = Field(
        default=True,
        description="Auto-reindex changed files on git commit",
    )
    maintenance_interval_seconds: int = Field(
        default=300,
        description="Background reindex interval in seconds",
    )
    max_file_size_bytes: int = Field(
        default=1_000_000,
        description="Skip files larger than this",
    )
    exclude_patterns: list[str] = Field(
        default=[
            "node_modules",
            ".vite",
            ".git",
            "__pycache__",
            ".mypy_cache",
            ".ruff_cache",
            ".pytest_cache",
            ".tox",
            ".eggs",
            "vendor",
            "build",
            "dist",
            ".venv",
        ],
        description="Glob patterns to exclude from indexing",
    )
    embedding_enabled: bool = Field(
        default=True,
        description="Enable Qdrant vector embeddings for semantic search",
    )
    graph_enabled: bool = Field(
        default=True,
        description="Enable Neo4j call/import graph",
    )
    qdrant_collection_prefix: str = Field(
        default="code_symbols_",
        description="Qdrant collection name prefix",
    )
    languages: list[str] = Field(
        default=[
            "python",
            "javascript",
            "typescript",
            "go",
            "rust",
            "java",
            "php",
            "dart",
            "csharp",
            "c",
            "cpp",
            "elixir",
            "ruby",
            "markdown",
            "yaml",
            "json",
        ],
        description="Languages to index",
    )
    content_extensions: list[str] = Field(
        default=[
            ".html",
            ".css",
            ".scss",
            ".less",
            ".toml",
            ".cfg",
            ".ini",
            ".sh",
            ".bash",
            ".zsh",
            ".fish",
            ".sql",
            ".graphql",
            ".proto",
            ".txt",
            ".rst",
            ".csv",
            ".gitignore",
            ".editorconfig",
        ],
        description="Additional file extensions to index for content search only (no AST parsing)",
    )
