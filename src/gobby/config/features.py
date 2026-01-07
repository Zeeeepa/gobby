"""
Feature configuration module.

Contains MCP proxy and tool feature Pydantic config models:
- CodeExecutionConfig: Code execution MCP tool settings
- ToolSummarizerConfig: Tool description summarization settings
- RecommendToolsConfig: Tool recommendation settings
- ImportMCPServerConfig: MCP server import settings
- MetricsConfig: Metrics endpoint settings
- ProjectVerificationConfig: Project verification command settings

Extracted from app.py using Strangler Fig pattern for code decomposition.
"""

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "CodeExecutionConfig",
    "ToolSummarizerConfig",
    "RecommendToolsConfig",
    "ImportMCPServerConfig",
    "MetricsConfig",
    "ProjectVerificationConfig",
    "DEFAULT_IMPORT_MCP_SERVER_PROMPT",
]


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


class ToolSummarizerConfig(BaseModel):
    """Tool description summarization configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable LLM-based tool description summarization",
    )
    provider: str = Field(
        default="claude",
        description="LLM provider to use for summarization",
    )
    model: str = Field(
        default="claude-haiku-4-5",
        description="Model to use for summarization (fast/cheap recommended)",
    )
    prompt: str = Field(
        default="""Summarize this MCP tool description in 180 characters or less.
Keep it to three sentences or less. Be concise and preserve the key functionality.
Do not add quotes, extra formatting, or code examples.

Description: {description}

Summary:""",
        description="Prompt template for tool description summarization (use {description} placeholder)",
    )
    system_prompt: str = Field(
        default="You are a technical summarizer. Create concise tool descriptions.",
        description="System prompt for tool description summarization",
    )
    server_description_prompt: str = Field(
        default="""Write a single concise sentence describing what the '{server_name}' MCP server does based on its tools.

Tools:
{tools_list}

Description (1 sentence, try to keep under 100 characters):""",
        description="Prompt template for server description generation (use {server_name} and {tools_list} placeholders)",
    )
    server_description_system_prompt: str = Field(
        default="You write concise technical descriptions.",
        description="System prompt for server description generation",
    )


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
    hybrid_rerank_prompt: str = Field(
        default="""You are an expert at selecting tools for tasks.
Task: {task_description}

Candidate tools (ranked by semantic similarity):
{candidate_list}

Re-rank these tools by relevance to the task and provide reasoning.
Return the top {top_k} most relevant as JSON:
{{
  "recommendations": [
    {{
      "server": "server_name",
      "tool": "tool_name",
      "reason": "Why this tool is the best choice"
    }}
  ]
}}""",
        description="Prompt template for hybrid mode re-ranking (use {task_description}, {candidate_list}, {top_k} placeholders)",
    )
    llm_prompt: str = Field(
        default="""You are an expert at selecting the right tools for a given task.
Task: {task_description}

Available Servers: {available_servers}

Please recommend which tools from these servers would be most useful for this task.
Return a JSON object with this structure:
{{
  "recommendations": [
    {{
      "server": "server_name",
      "tool": "tool_name",
      "reason": "Why this tool is useful"
    }}
  ]
}}""",
        description="Prompt template for LLM mode recommendations (use {task_description}, {available_servers} placeholders)",
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
    github_fetch_prompt: str = Field(
        default="""Fetch the README from this GitHub repository and extract MCP server configuration:

{github_url}

If the URL doesn't point directly to a README, try to find and fetch the README.md file.

After reading the documentation, extract the MCP server configuration as a JSON object.""",
        description="User prompt template for GitHub import (use {github_url} placeholder)",
    )
    search_fetch_prompt: str = Field(
        default="""Search for MCP server: {search_query}

Find the official documentation or GitHub repository for this MCP server.
Then fetch and read the README or installation docs.

After reading the documentation, extract the MCP server configuration as a JSON object.""",
        description="User prompt template for search-based import (use {search_query} placeholder)",
    )


class MetricsConfig(BaseModel):
    """Configuration for metrics and status endpoints."""

    list_limit: int = Field(
        default=10000,
        description="Maximum items to fetch when counting sessions/tasks/skills for metrics. "
        "Set higher for large installs to avoid underreporting. "
        "Use 0 for unbounded (uses COUNT queries instead of list).",
    )

    @field_validator("list_limit")
    @classmethod
    def validate_list_limit(cls, v: int) -> int:
        """Validate list_limit is non-negative."""
        if v < 0:
            raise ValueError("list_limit must be non-negative")
        return v


class ProjectVerificationConfig(BaseModel):
    """Project verification commands configuration.

    Stores project-specific commands for running tests, type checking, linting, etc.
    Used by task expansion to generate precise validation criteria with actual commands.
    """

    unit_tests: str | None = Field(
        default=None,
        description="Command to run unit tests (e.g., 'uv run pytest tests/ -v')",
    )
    type_check: str | None = Field(
        default=None,
        description="Command to run type checking (e.g., 'uv run mypy src/')",
    )
    lint: str | None = Field(
        default=None,
        description="Command to run linting (e.g., 'uv run ruff check src/')",
    )
    integration: str | None = Field(
        default=None,
        description="Command to run integration tests",
    )
    custom: dict[str, str] = Field(
        default_factory=dict,
        description="Custom verification commands (name -> command)",
    )
