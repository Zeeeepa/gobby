"""
Configuration management for Gobby daemon.

Provides YAML-based configuration with CLI overrides,
configuration hierarchy (CLI > YAML > Defaults), and validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class WebSocketSettings(BaseModel):
    """WebSocket server configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable WebSocket server for real-time communication",
    )
    port: int = Field(
        default=8766,
        description="Port for WebSocket server to listen on",
    )
    ping_interval: int = Field(
        default=30,
        description="Ping interval in seconds for keepalive",
    )
    ping_timeout: int = Field(
        default=10,
        description="Pong timeout in seconds before considering connection dead",
    )

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port number is in valid range."""
        if not (1024 <= v <= 65535):
            raise ValueError("Port must be between 1024 and 65535")
        return v

    @field_validator("ping_interval", "ping_timeout")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        """Validate value is positive."""
        if v <= 0:
            raise ValueError("Value must be positive")
        return v


class LoggingSettings(BaseModel):
    """Logging configuration."""

    level: Literal["debug", "info", "warning", "error"] = Field(
        default="info",
        description="Log level",
    )
    format: Literal["text", "json"] = Field(
        default="text",
        description="Log format (text or json)",
    )

    # Log file paths
    client: str = Field(
        default="~/.gobby/logs/gobby.log",
        description="Daemon main log file path",
    )
    client_error: str = Field(
        default="~/.gobby/logs/gobby-error.log",
        description="Daemon error log file path",
    )
    hook_manager: str = Field(
        default="~/.gobby/logs/hook-manager.log",
        description="Claude Code hook manager log file path",
    )
    mcp_server: str = Field(
        default="~/.gobby/logs/mcp-server.log",
        description="MCP server log file path",
    )
    mcp_client: str = Field(
        default="~/.gobby/logs/mcp-client.log",
        description="MCP client connection log file path",
    )

    max_size_mb: int = Field(
        default=10,
        description="Maximum log file size in MB",
    )
    backup_count: int = Field(
        default=5,
        description="Number of backup log files to keep",
    )

    @field_validator("max_size_mb", "backup_count")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        """Validate value is positive."""
        if v <= 0:
            raise ValueError("Value must be positive")
        return v


class CompactHandoffConfig(BaseModel):
    """Compact handoff context configuration for /compact command."""

    enabled: bool = Field(
        default=True,
        description="Enable compact handoff context extraction and injection",
    )
    prompt: str = Field(
        default="""## Continuation Context

{active_task_section}
{todo_state_section}
{git_commits_section}
{git_status_section}
{files_modified_section}
{initial_goal_section}
{recent_activity_section}
""",
        description="Template for formatting handoff context. Available placeholders: "
        "{active_task_section}, {todo_state_section}, {git_commits_section}, "
        "{git_status_section}, {files_modified_section}, {initial_goal_section}, "
        "{recent_activity_section}",
    )


class SessionSummaryConfig(BaseModel):
    """Session summary generation configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable LLM-based session summary generation",
    )
    provider: str = Field(
        default="claude",
        description="LLM provider to use for session summary",
    )
    model: str = Field(
        default="claude-haiku-4-5",
        description="Model to use for session summary generation",
    )
    prompt: str | None = Field(
        default=None,
        description="Custom prompt template for session summary",
    )
    summary_file_path: str = Field(
        default="~/.gobby/session_summaries",
        description="Directory path for session summary markdown files",
    )


class CodeExecutionConfig(BaseModel):
    """Code execution configuration for MCP tools."""

    enabled: bool = Field(
        default=True,
        description="Enable code execution MCP tools (execute_code, process_large_dataset)",
    )
    provider: str = Field(
        default="claude",
        description="LLM provider to use for code execution",
    )
    model: str = Field(
        default="claude-sonnet-4-5",
        description="Model to use for code execution (must support code_execution tool)",
    )
    prompt: str | None = Field(
        default=None,
        description="Custom prompt template for code execution",
    )
    max_turns: int = Field(
        default=5,
        description="Maximum turns for code execution conversations",
    )
    default_timeout: int = Field(
        default=30,
        description="Default timeout in seconds for code execution",
    )
    learning_threshold: float = Field(
        default=0.7,
        description="Threshold for skill learning (0-1)",
    )
    max_context_skills: int = Field(
        default=5,
        description="Maximum number of skills to include in context window",
    )
    max_dataset_preview: int = Field(
        default=3,
        description="Maximum number of dataset items to show in preview",
    )

    @field_validator("max_turns")
    @classmethod
    def validate_max_turns(cls, v: int) -> int:
        """Validate max_turns is positive."""
        if v <= 0:
            raise ValueError("max_turns must be positive")
        return v

    @field_validator("default_timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """Validate timeout is positive."""
        if v <= 0:
            raise ValueError("default_timeout must be positive")
        return v

    @field_validator("learning_threshold")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        """Validate threshold is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError("learning_threshold must be between 0 and 1")
        return v

    @field_validator("max_context_skills")
    @classmethod
    def validate_max_skills(cls, v: int) -> int:
        """Validate max_context_skills is positive."""
        if v <= 0:
            raise ValueError("max_context_skills must be positive")
        return v

    @field_validator("max_dataset_preview")
    @classmethod
    def validate_preview(cls, v: int) -> int:
        """Validate preview size is positive."""
        if v <= 0:
            raise ValueError("max_dataset_preview must be positive")
        return v


class RecommendToolsConfig(BaseModel):
    """Tool recommendation configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable tool recommendation MCP tool",
    )
    provider: str = Field(
        default="claude",
        description="LLM provider to use for tool recommendations",
    )
    model: str = Field(
        default="claude-sonnet-4-5",
        description="Model to use for tool recommendations",
    )
    prompt: str = Field(
        default="""You are a tool recommendation assistant for Claude Code with access to MCP servers.

CRITICAL PRIORITIZATION RULES:
1. Analyze the task type (code navigation, docs lookup, database query, planning, data processing, etc.)
2. Check available MCP server DESCRIPTIONS for capability matches
3. If ANY MCP server's description matches the task type -> recommend those tools FIRST
4. Only recommend built-in Claude Code tools (Grep, Read, Bash, WebSearch) if NO suitable MCP server exists

TASK TYPE MATCHING GUIDELINES:
- Task needs library/framework documentation -> Look for MCP servers describing "documentation", "library docs", "API reference"
- Task needs code navigation/architecture understanding -> Look for MCP servers describing "code analysis", "symbols", "semantic search"
- Task needs database operations -> Look for MCP servers describing "database", "PostgreSQL", "SQL"
- Task needs complex reasoning/planning -> Look for MCP servers describing "problem-solving", "thinking", "reasoning"
- Task needs data processing/large datasets -> Look for MCP servers describing "code execution", "data processing", "token optimization"

ANTI-PATTERNS (What NOT to recommend):
- Don't recommend WebSearch when an MCP server provides library/framework documentation
- Don't recommend Grep/Read for code architecture questions when an MCP server does semantic code analysis
- Don't recommend Bash for database queries when an MCP server provides database tools
- Don't recommend direct implementation when an MCP server provides structured reasoning

OUTPUT FORMAT:
Be concise and specific. Recommend 1-3 tools maximum with:
1. Which MCP server and tools to use (if applicable)
2. Brief rationale based on server description matching task type
3. Suggested workflow (e.g., "First call X, then use result with Y")
4. Only mention built-in tools if no MCP server is suitable""",
        description="System prompt for recommend_tools() MCP tool.",
    )


DEFAULT_IMPORT_MCP_SERVER_PROMPT = """You are an MCP server configuration extractor. Given documentation for an MCP server, extract the configuration needed to connect to it.

Return ONLY a valid JSON object (no markdown, no code blocks) with these fields:
- name: Server name (lowercase, no spaces, use hyphens)
- transport: "http", "stdio", or "websocket"
- url: Server URL (required for http/websocket transports)
- command: Command to run (required for stdio, e.g., "npx", "uv", "node")
- args: Array of command arguments (for stdio)
- env: Object of environment variables needed (use placeholder "<YOUR_KEY_NAME>" for secrets)
- headers: Object of HTTP headers needed (use placeholder "<YOUR_KEY_NAME>" for secrets)
- instructions: How to obtain any required API keys or setup steps

Example stdio server:
{"name": "filesystem", "transport": "stdio", "command": "npx", "args": ["-y", "@anthropic-ai/filesystem-mcp"], "env": {}, "instructions": "No setup required"}

Example http server with API key:
{"name": "exa", "transport": "http", "url": "https://mcp.exa.ai/mcp", "headers": {"EXA_API_KEY": "<YOUR_EXA_API_KEY>"}, "instructions": "Get your API key from https://exa.ai/dashboard"}"""


class ImportMCPServerConfig(BaseModel):
    """MCP server import configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable MCP server import tool",
    )
    provider: str = Field(
        default="claude",
        description="LLM provider to use for config extraction",
    )
    model: str = Field(
        default="claude-haiku-4-5",
        description="Model to use for config extraction",
    )
    prompt: str = Field(
        default=DEFAULT_IMPORT_MCP_SERVER_PROMPT,
        description="System prompt for MCP server config extraction",
    )


class MCPClientProxyConfig(BaseModel):
    """MCP client proxy configuration for downstream MCP servers."""

    enabled: bool = Field(
        default=True,
        description="Enable MCP client proxy for downstream MCP servers",
    )
    connect_timeout: float = Field(
        default=30.0,
        description="Timeout in seconds for establishing connections to MCP servers",
    )
    proxy_timeout: int = Field(
        default=30,
        description="Timeout in seconds for proxy calls to downstream MCP servers",
    )
    tool_timeout: int = Field(
        default=30,
        description="Timeout in seconds for tool schema operations",
    )
    tool_timeouts: dict[str, float] = Field(
        default_factory=dict,
        description="Map of tool names to specific timeouts in seconds",
    )

    @field_validator("connect_timeout")
    @classmethod
    def validate_connect_timeout(cls, v: float) -> float:
        """Validate connect timeout is positive."""
        if v <= 0:
            raise ValueError("connect_timeout must be positive")
        return v

    @field_validator("proxy_timeout", "tool_timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """Validate timeout is positive."""
        if v <= 0:
            raise ValueError("Timeout must be positive")
        return v


class GobbyTasksConfig(BaseModel):
    """Configuration for gobby-tasks internal MCP server."""

    model_config = {"populate_by_name": True}

    enabled: bool = Field(
        default=True,
        description="Enable gobby-tasks internal MCP server",
    )
    show_result_on_create: bool = Field(
        default=False,
        description="Show full task result on create_task (False = minimal output with just id)",
    )
    expansion: TaskExpansionConfig = Field(
        default_factory=lambda: TaskExpansionConfig(),
        description="Task expansion configuration",
    )
    validation: TaskValidationConfig = Field(
        default_factory=lambda: TaskValidationConfig(),
        description="Task validation configuration",
    )


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    models: str = Field(
        description="Comma-separated list of available models for this provider",
    )
    auth_mode: Literal["subscription", "api_key", "adc"] = Field(
        default="subscription",
        description="Authentication mode: 'subscription' (CLI-based), 'api_key' (BYOK), 'adc' (Google ADC)",
    )

    def get_models_list(self) -> list[str]:
        """Return models as a list."""
        return [m.strip() for m in self.models.split(",") if m.strip()]


class LLMProvidersConfig(BaseModel):
    """
    Configuration for multiple LLM providers.

    Example YAML:
    ```yaml
    llm_providers:
      claude:
        models: claude-haiku-4-5,claude-sonnet-4-5,claude-opus-4-5
      codex:
        models: gpt-4o-mini,gpt-5-mini,gpt-5
        auth_mode: subscription
      gemini:
        models: gemini-2.0-flash,gemini-2.5-pro
        auth_mode: adc
      litellm:
        models: gpt-4o-mini,mistral-large
        auth_mode: api_key
      api_keys:
        OPENAI_API_KEY: sk-...
        MISTRAL_API_KEY: ...
    ```
    """

    claude: LLMProviderConfig | None = Field(
        default=None,
        description="Claude provider configuration",
    )
    codex: LLMProviderConfig | None = Field(
        default=None,
        description="Codex (OpenAI) provider configuration",
    )
    gemini: LLMProviderConfig | None = Field(
        default=None,
        description="Gemini provider configuration",
    )
    litellm: LLMProviderConfig | None = Field(
        default=None,
        description="LiteLLM provider configuration",
    )
    api_keys: dict[str, str] = Field(
        default_factory=dict,
        description="API keys for BYOK providers (key name -> key value)",
    )

    def get_enabled_providers(self) -> list[str]:
        """Return list of enabled provider names."""
        providers = []
        if self.claude:
            providers.append("claude")
        if self.codex:
            providers.append("codex")
        if self.gemini:
            providers.append("gemini")
        if self.litellm:
            providers.append("litellm")
        return providers


class TitleSynthesisConfig(BaseModel):
    """Title synthesis configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable title synthesis for sessions",
    )
    provider: str = Field(
        default="claude",
        description="LLM provider to use for title synthesis",
    )
    model: str = Field(
        default="claude-haiku-4-5",
        description="Model to use for title synthesis",
    )
    prompt: str | None = Field(
        default=None,
        description="Custom prompt template for title synthesis",
    )


class WebSocketBroadcastConfig(BaseModel):
    """Configuration for WebSocket event broadcasting."""

    enabled: bool = Field(
        default=True,
        description="Enable broadcasting hook events to WebSocket clients",
    )
    broadcast_events: list[str] = Field(
        default=[
            "session-start",
            "session-end",
            "pre-tool-use",
            "post-tool-use",
        ],
        description="List of hook event types to broadcast",
    )
    include_payload: bool = Field(
        default=True,
        description="Include event payload data in broadcast messages",
    )


class HookExtensionsConfig(BaseModel):
    """Configuration for hook extensions (broadcasting, webhooks, plugins)."""

    websocket: WebSocketBroadcastConfig = Field(
        default_factory=WebSocketBroadcastConfig,
        description="WebSocket broadcasting configuration",
    )


class TaskExpansionConfig(BaseModel):
    """Configuration for task expansion (breaking down broad tasks/epics)."""

    enabled: bool = Field(
        default=True,
        description="Enable automated task expansion",
    )
    provider: str = Field(
        default="claude",
        description="LLM provider to use for expansion",
    )
    model: str = Field(
        default="claude-opus-4-5",
        description="Model to use for expansion",
    )
    prompt: str | None = Field(
        default=None,
        description="Custom prompt template for task expansion",
    )
    codebase_research_enabled: bool = Field(
        default=True,
        description="Enable agentic codebase research for context gathering",
    )
    research_model: str | None = Field(
        default=None,
        description="Model to use for research agent (defaults to expansion model if None)",
    )
    research_max_steps: int = Field(
        default=10,
        description="Maximum number of steps for research agent loop",
    )
    system_prompt: str | None = Field(
        default=None,
        description="Custom system prompt for task expansion (overrides default)",
    )
    web_research_enabled: bool = Field(
        default=True,
        description="Enable web research for task expansion using MCP tools",
    )
    tdd_mode: bool = Field(
        default=True,
        description="Enable TDD mode: create test->implement task pairs with appropriate blocking for coding tasks",
    )
    max_subtasks: int = Field(
        default=15,
        description="Maximum number of subtasks to create per expansion",
    )
    default_strategy: Literal["auto", "phased", "sequential", "parallel"] = Field(
        default="auto",
        description="Default expansion strategy: auto (LLM decides), phased, sequential, or parallel",
    )


class TaskValidationConfig(BaseModel):
    """Configuration for task validation (checking completion against criteria)."""

    enabled: bool = Field(
        default=True,
        description="Enable automated task validation",
    )
    provider: str = Field(
        default="claude",
        description="LLM provider to use for validation",
    )
    model: str = Field(
        default="claude-haiku-4-5",
        description="Model to use for validation",
    )
    prompt: str | None = Field(
        default=None,
        description="Custom prompt template for task validation",
    )
    criteria_prompt: str | None = Field(
        default=None,
        description="Custom prompt template for generating validation criteria from task description",
    )


class WorkflowConfig(BaseModel):
    """Workflow engine configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable workflow engine",
    )
    timeout: float = Field(
        default=30.0,
        description="Default timeout in seconds for workflow execution (e.g. LLM calls)",
    )

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: float) -> float:
        """Validate timeout is positive."""
        if v <= 0:
            raise ValueError("Timeout must be positive")
        return v


class MessageTrackingConfig(BaseModel):
    """Configuration for session message tracking."""

    enabled: bool = Field(
        default=True,
        description="Enable session message tracking",
    )
    poll_interval: float = Field(
        default=5.0,
        description="Polling interval in seconds for transcript updates",
    )
    debounce_delay: float = Field(
        default=1.0,
        description="Debounce delay in seconds for message processing",
    )
    max_message_length: int = Field(
        default=10000,
        description="Maximum length of a single message content",
    )
    broadcast_enabled: bool = Field(
        default=True,
        description="Enable broadcasting message events",
    )

    @field_validator("poll_interval", "debounce_delay")
    @classmethod
    def validate_positive(cls, v: float) -> float:
        """Validate value is positive."""
        if v <= 0:
            raise ValueError("Value must be positive")
        return v


class SessionLifecycleConfig(BaseModel):
    """Configuration for session lifecycle management.

    Handles:
    - Pausing active sessions with no recent activity
    - Expiring stale sessions (active/paused for too long)
    - Background transcript processing for expired sessions
    """

    active_session_pause_minutes: int = Field(
        default=30,
        description="Minutes of inactivity before active sessions are marked paused",
    )
    stale_session_timeout_hours: int = Field(
        default=24,
        description="Hours after which inactive sessions are marked expired",
    )
    expire_check_interval_minutes: int = Field(
        default=60,
        description="How often to check for stale sessions (minutes)",
    )
    transcript_processing_interval_minutes: int = Field(
        default=5,
        description="How often to process pending transcripts (minutes)",
    )
    transcript_processing_batch_size: int = Field(
        default=10,
        description="Maximum sessions to process per batch",
    )

    @field_validator(
        "active_session_pause_minutes",
        "stale_session_timeout_hours",
        "expire_check_interval_minutes",
        "transcript_processing_interval_minutes",
        "transcript_processing_batch_size",
    )
    @classmethod
    def validate_positive(cls, v: int) -> int:
        """Validate value is positive."""
        if v <= 0:
            raise ValueError("Value must be positive")
        return v


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
    provider: str = Field(
        default="claude",
        description="LLM provider to use for memory extraction",
    )
    model: str = Field(
        default="claude-haiku-4-5",
        description="Model to use for memory extraction",
    )
    extraction_prompt: str = Field(
        default="""You are an expert at extracting valuable information from development session transcripts.
Respond with ONLY valid JSON - no markdown, no explanations, no code blocks.

Analyze the following session summary and extract any facts, preferences, or patterns worth remembering for future sessions.

Types of memories to extract:
- "fact": Technical facts about the project (architecture, dependencies, conventions)
- "preference": User preferences for tools, patterns, or approaches
- "pattern": Recurring patterns or solutions that worked well
- "context": Important project context (goals, constraints, decisions)

Session Summary:
{summary}

Return a JSON array directly (empty array [] if nothing worth remembering):
[
  {{
    "content": "The specific fact, preference, or pattern to remember",
    "memory_type": "fact|preference|pattern|context",
    "importance": 0.5,
    "tags": ["optional", "tags"]
  }}
]

Guidelines:
- Only extract information that would be valuable in future sessions
- Set importance 0.3-0.5 for nice-to-know, 0.6-0.8 for important, 0.9-1.0 for critical
- Keep content concise but complete (one clear statement per memory)
- Avoid duplicating obvious information or temporary context""",
        description="Prompt template for memory extraction (use {summary} placeholder)",
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


class DaemonConfig(BaseModel):
    """
    Main configuration for Gobby daemon.

    Configuration is loaded with the following priority:
    1. CLI arguments (highest)
    2. YAML file (~/.gobby/config.yaml)
    3. Defaults (lowest)

    Note: machine_id is stored separately in ~/.gobby/machine_id
    """

    model_config = {"populate_by_name": True}

    # Daemon settings
    daemon_port: int = Field(
        default=8765,
        description="Port for daemon to listen on",
    )
    daemon_health_check_interval: float = Field(
        default=10.0,
        description="Daemon health check interval in seconds",
    )

    # Local storage
    database_path: str = Field(
        default="~/.gobby/gobby.db",
        description="Path to SQLite database file",
    )

    # Sub-configs
    websocket: WebSocketSettings = Field(
        default_factory=WebSocketSettings,
        description="WebSocket server configuration",
    )
    logging: LoggingSettings = Field(
        default_factory=LoggingSettings,
        description="Logging configuration",
    )
    session_summary: SessionSummaryConfig = Field(
        default_factory=SessionSummaryConfig,
        description="Session summary generation configuration",
    )
    compact_handoff: CompactHandoffConfig = Field(
        default_factory=CompactHandoffConfig,
        description="Compact handoff context configuration",
    )
    mcp_client_proxy: MCPClientProxyConfig = Field(
        default_factory=MCPClientProxyConfig,
        description="MCP client proxy configuration",
    )
    gobby_tasks: GobbyTasksConfig = Field(
        default_factory=GobbyTasksConfig,
        alias="gobby-tasks",
        serialization_alias="gobby-tasks",
        description="gobby-tasks internal MCP server configuration",
    )

    # Multi-provider LLM configuration
    llm_providers: LLMProvidersConfig = Field(
        default_factory=LLMProvidersConfig,
        description="Multi-provider LLM configuration",
    )
    title_synthesis: TitleSynthesisConfig = Field(
        default_factory=TitleSynthesisConfig,
        description="Title synthesis configuration",
    )
    code_execution: CodeExecutionConfig = Field(
        default_factory=CodeExecutionConfig,
        description="Code execution configuration",
    )
    recommend_tools: RecommendToolsConfig = Field(
        default_factory=RecommendToolsConfig,
        description="Tool recommendation configuration",
    )
    import_mcp_server: ImportMCPServerConfig = Field(
        default_factory=ImportMCPServerConfig,
        description="MCP server import configuration",
    )
    hook_extensions: HookExtensionsConfig = Field(
        default_factory=HookExtensionsConfig,
        description="Hook extensions configuration",
    )
    workflow: WorkflowConfig = Field(
        default_factory=WorkflowConfig,
        description="Workflow engine configuration",
    )
    memory: MemoryConfig = Field(
        default_factory=MemoryConfig,
        description="Memory system configuration",
    )
    memory_sync: MemorySyncConfig = Field(
        default_factory=MemorySyncConfig,
        description="Memory synchronization configuration",
    )
    skill_sync: SkillSyncConfig = Field(
        default_factory=SkillSyncConfig,
        description="Skill synchronization configuration",
    )
    skills: SkillConfig = Field(
        default_factory=SkillConfig,
        description="Skill learning configuration",
    )
    message_tracking: MessageTrackingConfig = Field(
        default_factory=MessageTrackingConfig,
        description="Session message tracking configuration",
    )
    session_lifecycle: SessionLifecycleConfig = Field(
        default_factory=SessionLifecycleConfig,
        description="Session lifecycle management configuration",
    )

    def get_code_execution_config(self) -> CodeExecutionConfig:
        """Get code execution configuration."""
        return self.code_execution

    def get_recommend_tools_config(self) -> RecommendToolsConfig:
        """Get recommend_tools configuration."""
        return self.recommend_tools

    def get_import_mcp_server_config(self) -> ImportMCPServerConfig:
        """Get import_mcp_server configuration."""
        return self.import_mcp_server

    def get_mcp_client_proxy_config(self) -> MCPClientProxyConfig:
        """Get MCP client proxy configuration."""
        return self.mcp_client_proxy

    def get_memory_config(self) -> MemoryConfig:
        """Get memory configuration."""
        return self.memory

    def get_memory_sync_config(self) -> MemorySyncConfig:
        """Get memory sync configuration."""
        return self.memory_sync

    def get_skill_sync_config(self) -> SkillSyncConfig:
        """Get skill sync configuration."""
        return self.skill_sync

    def get_skills_config(self) -> SkillConfig:
        """Get skills configuration."""
        return self.skills

    def get_gobby_tasks_config(self) -> GobbyTasksConfig:
        """Get gobby-tasks configuration."""
        return self.gobby_tasks

    @field_validator("daemon_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port number is in valid range."""
        if not (1024 <= v <= 65535):
            raise ValueError("Port must be between 1024 and 65535")
        return v

    @field_validator("daemon_health_check_interval")
    @classmethod
    def validate_health_check_interval(cls, v: float) -> float:
        """Validate health check interval is in valid range."""
        if not (1.0 <= v <= 300.0):
            raise ValueError("daemon_health_check_interval must be between 1.0 and 300.0 seconds")
        return v


def load_yaml(config_file: str) -> dict[str, Any]:
    """
    Load YAML or JSON configuration file.

    Args:
        config_file: Path to YAML or JSON configuration file

    Returns:
        Dictionary with parsed YAML/JSON content

    Raises:
        ValueError: If YAML/JSON is invalid or file format is wrong
    """
    config_path = Path(config_file).expanduser()

    if not config_path.exists():
        return {}

    # Validate file extension matches format
    file_ext = config_path.suffix.lower()
    if file_ext not in [".yaml", ".yml", ".json"]:
        raise ValueError(
            f"Config file must have .yaml, .yml, or .json extension, got: {file_ext}\n"
            f"File: {config_path}"
        )

    import json

    try:
        with open(config_path) as f:
            content = f.read()

        # Handle JSON files
        if file_ext == ".json":
            return json.loads(content) if content.strip() else {}

        # Handle YAML files
        data = yaml.safe_load(content)
        return data if data is not None else {}

    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in config file: {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file: {e}") from e


def apply_cli_overrides(
    config_dict: dict[str, Any],
    cli_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Apply CLI argument overrides to config dictionary.

    Args:
        config_dict: Configuration dictionary
        cli_overrides: Dictionary of CLI overrides

    Returns:
        Configuration dictionary with CLI overrides applied
    """
    if cli_overrides is None:
        return config_dict

    # Apply overrides at top level
    for key, value in cli_overrides.items():
        if "." in key:
            # Handle nested keys like "logging.level"
            parts = key.split(".")
            current = config_dict
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        else:
            config_dict[key] = value

    return config_dict


def generate_default_config(config_file: str) -> None:
    """
    Generate default configuration file from Pydantic model defaults.

    Args:
        config_file: Path where to create the config file
    """
    config_path = Path(config_file).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Use Pydantic model defaults as source of truth
    default_config = DaemonConfig().model_dump(mode="python", exclude_none=True)

    with open(config_path, "w") as f:
        yaml.safe_dump(default_config, f, default_flow_style=False, sort_keys=False)

    # Set restrictive permissions (owner read/write only)
    config_path.chmod(0o600)


def load_config(
    config_file: str | None = None,
    cli_overrides: dict[str, Any] | None = None,
    create_default: bool = False,
) -> DaemonConfig:
    """
    Load configuration with hierarchy: CLI > YAML > Defaults.

    Args:
        config_file: Path to YAML config file (default: ~/.gobby/config.yaml)
        cli_overrides: Dictionary of CLI argument overrides
        create_default: Create default config file if it doesn't exist

    Returns:
        Validated DaemonConfig instance

    Raises:
        ValueError: If configuration is invalid or required fields are missing
    """
    if config_file is None:
        config_file = "~/.gobby/config.yaml"

    config_path = Path(config_file).expanduser()

    # Create default config if requested and file doesn't exist
    if create_default and not config_path.exists():
        generate_default_config(config_file)

    # Load YAML configuration
    config_dict = load_yaml(config_file)

    # Apply CLI argument overrides
    config_dict = apply_cli_overrides(config_dict, cli_overrides)

    # Validate and create config object
    try:
        config = DaemonConfig(**config_dict)
        return config
    except Exception as e:
        raise ValueError(
            f"Configuration validation failed: {e}\n"
            f"Please check your configuration file at {config_file}"
        ) from e


def save_config(config: DaemonConfig, config_file: str | None = None) -> None:
    """
    Save configuration to YAML file.

    Args:
        config: DaemonConfig instance to save
        config_file: Path to YAML config file (default: ~/.gobby/config.yaml)

    Raises:
        OSError: If file operations fail
    """
    if config_file is None:
        config_file = "~/.gobby/config.yaml"

    config_path = Path(config_file).expanduser()

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert config to dict, excluding None values to keep file clean
    config_dict = config.model_dump(mode="python", exclude_none=True)

    # Write to YAML file
    with open(config_path, "w") as f:
        yaml.safe_dump(config_dict, f, default_flow_style=False, sort_keys=False)

    # Set restrictive permissions (owner read/write only)
    config_path.chmod(0o600)
