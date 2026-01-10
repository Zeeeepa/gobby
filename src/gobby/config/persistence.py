"""
Persistence configuration module.

Contains storage and sync-related Pydantic config models:
- MemoryConfig: Memory system settings (extraction, injection, decay)
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
    auto_extract: bool = Field(
        default=True,
        description="Automatically extract memories from sessions",
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
    provider: str = Field(
        default="claude",
        description="LLM provider to use for memory extraction",
    )
    model: str = Field(
        default="claude-haiku-4-5",
        description="Model to use for memory extraction",
    )
    extraction_prompt: str = Field(
        default="""Extract memories for a plan/act/reflect agent loop. Return ONLY valid JSON.

PURPOSE: These memories help the agent:
- PLAN: Recall relevant context before proposing approaches
- ACT: Remember lessons from similar past situations before tool use
- REFLECT: Build knowledge from what worked and what didn't

PRIORITY ORDER (extract in this order of importance):

1. USER-STATED PREFERENCES (importance: 0.9)
   When the user explicitly says "I want X", "always do Y", "never do Z", "I prefer..."
   These are HIGHEST priority - the user knows their codebase and workflow.

2. DISCOVERED GOTCHAS (importance: 0.85)
   Bugs, failures, or surprises: "X fails when Y", "Don't forget to Z before W"
   Things that would help avoid repeating mistakes.

3. ARCHITECTURAL DECISIONS (importance: 0.8)
   Non-obvious choices: "We use X pattern for Y", "Service A depends on B"
   Only if NOT already in CLAUDE.md.

4. REUSABLE PATTERNS (importance: 0.75)
   Approaches that worked well and could apply to similar future tasks.

DO NOT EXTRACT:
- Transient status ("completed task X", "sprint Y progress")
- Generic advice that applies to any project
- Information already in CLAUDE.md
- Implementation details (variable names, line numbers)

Session Summary:
{summary}

Return JSON array (empty [] if nothing meets criteria):
[
  {{
    "content": "Specific memory - quote user when capturing preferences",
    "memory_type": "preference|pattern|fact",
    "importance": 0.75,
    "tags": ["relevant-topic"]
  }}
]

For user preferences, use their words: "User prefers X over Y" or "User wants Z".""",
        description="Prompt template for session memory extraction (use {summary} placeholder)",
    )

    agent_md_extraction_prompt: str = Field(
        default="""You are an expert at extracting structured information from project documentation.
Respond with ONLY valid JSON - no markdown, no explanations, no code blocks.

Analyze the following agent instructions file and extract instructions, preferences, and project context that should be remembered.

Agent Instructions:
{content}

Return a JSON array of memories to extract (empty array [] if nothing significant):
[
  {{
    "content": "The specific instruction, preference, or fact to remember",
    "memory_type": "fact|preference|pattern|context",
    "importance": 0.7,
    "tags": ["optional", "tags"]
  }}
]

Guidelines:
- Extract explicit instructions and preferences (importance 0.7-0.9)
- Extract project architecture facts (importance 0.6-0.8)
- Extract coding conventions and patterns (importance 0.5-0.7)
- Skip obvious boilerplate or generic instructions
- Keep content concise but actionable""",
        description="Prompt template for agent MD extraction (use {content} placeholder)",
    )

    codebase_extraction_prompt: str = Field(
        default="""You are an expert at analyzing codebases and extracting patterns.
Respond with ONLY valid JSON - no markdown, no explanations, no code blocks.

Analyze the following codebase structure and file samples to extract patterns, conventions, and architectural decisions.

Codebase Analysis:
{content}

Return a JSON array of patterns to remember (empty array [] if nothing significant):
[
  {{
    "content": "The specific pattern, convention, or architectural decision",
    "memory_type": "fact|pattern|context",
    "importance": 0.6,
    "tags": ["architecture", "convention", "pattern"]
  }}
]

Guidelines:
- Focus on project-specific patterns, not generic language features
- Extract naming conventions, file organization patterns
- Note architectural decisions (frameworks, patterns used)
- Identify testing conventions
- Set importance based on how critical the pattern is for consistency""",
        description="Prompt template for codebase extraction (use {content} placeholder)",
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
