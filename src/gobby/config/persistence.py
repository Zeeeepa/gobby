"""
Persistence configuration module.

Contains storage and sync-related Pydantic config models:
- MemoryConfig: Memory system settings (extraction, injection, decay)
- MemorySyncConfig: Memory file sync settings (stealth mode, debounce)
- SkillSyncConfig: Skill file sync settings
- SkillConfig: Skill learning settings

Extracted from app.py using Strangler Fig pattern for code decomposition.
"""

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "MemoryConfig",
    "MemorySyncConfig",
    "SkillSyncConfig",
    "SkillConfig",
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
        default=0.3,
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
        default="""You are an expert at extracting long-term knowledge from development session transcripts.
Respond with ONLY valid JSON - no markdown, no explanations, no code blocks.

Analyze the following session summary and extract any NEW facts, preferences, or patterns worth remembering for future sessions.

CRITICAL QUALITY FILTER:
- DO NOT extract information already in CLAUDE.md or generic knowledge.
- DO NOT extract transient session logs ("User ran X command", "Test failed").
- DO NOT extract internal implementation details like variable names unless critical.
- DO NOT create duplicate memories. If something is fundamental (e.g., project architecture), assume it's already known.
- ONLY extract high-value insights:
    *   Specific bugs/gotchas found ("Feature X fails when Y")
    *   Explicit User Preferences ("Always use library Z")
    *   New architectural decisions ("We serve frontend from /api")

Session Summary:
{summary}

Return a JSON array directly (empty array [] if nothing passes the filter):
[
  {{
    "content": "The specific fact, preference, or pattern to remember",
    "memory_type": "fact|preference|pattern|context",
    "importance": 0.5,
    "tags": ["optional", "tags"]
  }}
]

Guidelines:
- "fact": Permanent truths about the codebase (not temporary states)
- "pattern": Reusable solutions
- "preference": Explicit user directives
- Importance > 0.8 is reserved for CRITICAL information that prevents bugs.""",
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

    @field_validator("importance_threshold", "decay_rate", "decay_floor")
    @classmethod
    def validate_probability(cls, v: float) -> float:
        """Validate value is between 0.0 and 1.0."""
        if not (0.0 <= v <= 1.0):
            raise ValueError("Value must be between 0.0 and 1.0")
        return v


class MemorySyncConfig(BaseModel):
    """Memory synchronization configuration (Git sync)."""

    enabled: bool = Field(
        default=True,
        description="Enable memory synchronization to filesystem",
    )
    stealth: bool = Field(
        default=False,
        description="If True, store in ~/.gobby/ (local only). If False, store in .gobby/ (git committed).",
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


class SkillSyncConfig(BaseModel):
    """Skill synchronization configuration (Git sync)."""

    enabled: bool = Field(
        default=True,
        description="Enable skill synchronization to filesystem",
    )
    stealth: bool = Field(
        default=False,
        description="If True, store in ~/.gobby/ (local only). If False, store in .gobby/ (git committed).",
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


class SkillConfig(BaseModel):
    """Skill learning configuration.

    Skills are exported to .claude/skills/<name>/ in Claude Code native format,
    making them automatically available to Claude Code sessions.
    """

    enabled: bool = Field(
        default=True,
        description="Enable skill learning system",
    )
    provider: str = Field(
        default="claude",
        description="LLM provider to use for skill extraction",
    )
    model: str = Field(
        default="claude-haiku-4-5",
        description="Model to use for skill extraction",
    )
    prompt: str = Field(
        default="""You are an expert at extracting reusable developer skills from transcripts.
Respond with ONLY valid JSON - no markdown, no explanations, no code blocks.

Analyze the following session transcript and extract any reusable skills.
A "skill" is a repeatable process or pattern that can be used in future sessions.

Transcript:
{transcript}

Return a JSON array directly:
[
  {{
    "name": "short-kebab-case-name",
    "description": "Brief description of what the skill does",
    "trigger_pattern": "regex|pattern|to|match",
    "instructions": "Markdown instructions on how to perform the skill",
    "tags": ["tag1", "tag2"]
  }}
]""",
        description="Prompt template for skill extraction (use {transcript} placeholder)",
    )
