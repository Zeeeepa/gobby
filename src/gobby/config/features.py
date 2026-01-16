"""
Feature configuration module.

Contains MCP proxy and tool feature Pydantic config models:
- ToolSummarizerConfig: Tool description summarization settings
- RecommendToolsConfig: Tool recommendation settings
- ImportMCPServerConfig: MCP server import settings
- MetricsConfig: Metrics endpoint settings
- ProjectVerificationConfig: Project verification command settings
- TaskDescriptionConfig: LLM-based task description generation settings

Extracted from app.py using Strangler Fig pattern for code decomposition.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "ToolSummarizerConfig",
    "RecommendToolsConfig",
    "ImportMCPServerConfig",
    "MetricsConfig",
    "ProjectVerificationConfig",
    "HookStageConfig",
    "HooksConfig",
    "TaskDescriptionConfig",
    "DEFAULT_IMPORT_MCP_SERVER_PROMPT",
]


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
        description="DEPRECATED: Use prompt_path instead. Prompt template for tool description summarization",
    )
    prompt_path: str | None = Field(
        default=None,
        description="Path to custom tool summary prompt template (e.g., 'features/tool_summary')",
    )
    system_prompt: str = Field(
        default="You are a technical summarizer. Create concise tool descriptions.",
        description="DEPRECATED: Use system_prompt_path instead. System prompt for tool description summarization",
    )
    system_prompt_path: str | None = Field(
        default=None,
        description="Path to custom tool summary system prompt (e.g., 'features/tool_summary_system')",
    )
    server_description_prompt: str = Field(
        default="""Write a single concise sentence describing what the '{server_name}' MCP server does based on its tools.

Tools:
{tools_list}

Description (1 sentence, try to keep under 100 characters):""",
        description="DEPRECATED: Use server_description_prompt_path instead. Prompt template for server description generation",
    )
    server_description_prompt_path: str | None = Field(
        default=None,
        description="Path to custom server description prompt (e.g., 'features/server_description')",
    )
    server_description_system_prompt: str = Field(
        default="You write concise technical descriptions.",
        description="DEPRECATED: Use server_description_system_prompt_path instead. System prompt for server description generation",
    )
    server_description_system_prompt_path: str | None = Field(
        default=None,
        description="Path to custom server description system prompt (e.g., 'features/server_description_system')",
    )


class TaskDescriptionConfig(BaseModel):
    """Task description generation configuration.

    Controls LLM-based description generation for tasks created from specs.
    Used when structured extraction yields minimal results.
    """

    enabled: bool = Field(
        default=True,
        description="Enable LLM-based task description generation",
    )
    provider: str = Field(
        default="claude",
        description="LLM provider to use for description generation",
    )
    model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Model to use for description generation (fast/cheap recommended)",
    )
    min_structured_length: int = Field(
        default=50,
        description="Minimum length of structured extraction before LLM fallback triggers",
    )
    prompt: str = Field(
        default="""Generate a concise task description for this task from a spec document.

Task title: {task_title}
Section: {section_title}
Section content: {section_content}
Existing context: {existing_context}

Write a 1-2 sentence description focusing on the goal and deliverable.
Do not add quotes, extra formatting, or implementation details.""",
        description="DEPRECATED: Use prompt_path instead. Prompt template for task description generation",
    )
    prompt_path: str | None = Field(
        default=None,
        description="Path to custom task description prompt (e.g., 'features/task_description')",
    )
    system_prompt: str = Field(
        default="You are a technical writer creating concise task descriptions for developers.",
        description="DEPRECATED: Use system_prompt_path instead. System prompt for task description generation",
    )
    system_prompt_path: str | None = Field(
        default=None,
        description="Path to custom task description system prompt (e.g., 'features/task_description_system')",
    )

    @field_validator("min_structured_length")
    @classmethod
    def validate_min_structured_length(cls, v: int) -> int:
        """Validate min_structured_length is non-negative."""
        if v < 0:
            raise ValueError("min_structured_length must be non-negative")
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
        description="DEPRECATED: Use prompt_path instead. System prompt for recommend_tools() MCP tool.",
    )
    prompt_path: str | None = Field(
        default=None,
        description="Path to custom recommend tools system prompt (e.g., 'features/recommend_tools')",
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
        description="DEPRECATED: Use hybrid_rerank_prompt_path instead. Prompt template for hybrid mode re-ranking",
    )
    hybrid_rerank_prompt_path: str | None = Field(
        default=None,
        description="Path to custom hybrid re-rank prompt (e.g., 'features/recommend_tools_hybrid')",
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
        description="DEPRECATED: Use llm_prompt_path instead. Prompt template for LLM mode recommendations",
    )
    llm_prompt_path: str | None = Field(
        default=None,
        description="Path to custom LLM recommendation prompt (e.g., 'features/recommend_tools_llm')",
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
        description="DEPRECATED: Use prompt_path instead. System prompt for MCP server config extraction",
    )
    prompt_path: str | None = Field(
        default=None,
        description="Path to custom import MCP system prompt (e.g., 'features/import_mcp')",
    )
    github_fetch_prompt: str = Field(
        default="""Fetch the README from this GitHub repository and extract MCP server configuration:

{github_url}

If the URL doesn't point directly to a README, try to find and fetch the README.md file.

After reading the documentation, extract the MCP server configuration as a JSON object.""",
        description="DEPRECATED: Use github_fetch_prompt_path instead. User prompt template for GitHub import",
    )
    github_fetch_prompt_path: str | None = Field(
        default=None,
        description="Path to custom GitHub fetch prompt (e.g., 'features/import_mcp_github')",
    )
    search_fetch_prompt: str = Field(
        default="""Search for MCP server: {search_query}

Find the official documentation or GitHub repository for this MCP server.
Then fetch and read the README or installation docs.

After reading the documentation, extract the MCP server configuration as a JSON object.""",
        description="DEPRECATED: Use search_fetch_prompt_path instead. User prompt template for search-based import",
    )
    search_fetch_prompt_path: str | None = Field(
        default=None,
        description="Path to custom search fetch prompt (e.g., 'features/import_mcp_search')",
    )


class MetricsConfig(BaseModel):
    """Configuration for metrics and status endpoints."""

    list_limit: int = Field(
        default=10000,
        description="Maximum items to fetch when counting sessions/tasks for metrics. "
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
    Also used by git hooks to run verification commands at pre-commit, pre-push, etc.
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
    format: str | None = Field(
        default=None,
        description="Command to check formatting (e.g., 'uv run ruff format --check src/')",
    )
    integration: str | None = Field(
        default=None,
        description="Command to run integration tests",
    )
    security: str | None = Field(
        default=None,
        description="Command to run security scanning (e.g., 'bandit -r src/')",
    )
    code_review: str | None = Field(
        default=None,
        description="Command to run AI/automated code review (e.g., 'coderabbit review --ci')",
    )
    custom: dict[str, str] = Field(
        default_factory=dict,
        description="Custom verification commands (name -> command)",
    )

    # Standard field names for lookup
    _standard_fields: tuple[str, ...] = (
        "unit_tests",
        "type_check",
        "lint",
        "format",
        "integration",
        "security",
        "code_review",
    )

    def get_command(self, name: str) -> str | None:
        """Get a command by name, checking both standard and custom fields.

        Args:
            name: Command name (e.g., 'lint', 'unit_tests', or custom name)

        Returns:
            The command string if found, None otherwise
        """
        # Check standard fields first
        if name in self._standard_fields:
            return getattr(self, name, None)
        # Check custom commands
        return self.custom.get(name)

    def all_commands(self) -> dict[str, str]:
        """Return all defined commands as a dict.

        Returns:
            Dict mapping command names to command strings (only non-None values)
        """
        result: dict[str, str] = {}
        for field in self._standard_fields:
            if cmd := getattr(self, field, None):
                result[field] = cmd
        result.update(self.custom)
        return result


class HookStageConfig(BaseModel):
    """Configuration for a single git hook stage."""

    run: list[str] = Field(
        default_factory=list,
        description="List of verification command names to run (e.g., ['lint', 'format'])",
    )
    fail_fast: bool = Field(
        default=True,
        description="Stop on first failure (exit 1) vs run all and report",
    )
    timeout: int = Field(
        default=300,
        description="Timeout in seconds for each command",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this hook stage is active",
    )


class HooksConfig(BaseModel):
    """Git hooks configuration for verification commands.

    Maps git hook stages to verification commands defined in ProjectVerificationConfig.
    """

    pre_commit: HookStageConfig = Field(
        default_factory=HookStageConfig,
        alias="pre-commit",
        description="Pre-commit hook configuration",
    )
    pre_push: HookStageConfig = Field(
        default_factory=HookStageConfig,
        alias="pre-push",
        description="Pre-push hook configuration",
    )
    pre_merge: HookStageConfig = Field(
        default_factory=HookStageConfig,
        alias="pre-merge",
        description="Pre-merge hook configuration (runs before merge commits)",
    )

    model_config = ConfigDict(populate_by_name=True)

    def get_stage(self, stage: str) -> HookStageConfig:
        """Get configuration for a hook stage.

        Args:
            stage: Hook stage name (e.g., 'pre-commit', 'pre-push', 'pre-merge')

        Returns:
            HookStageConfig for the stage
        """
        # Normalize stage name (pre-commit -> pre_commit)
        attr_name = stage.replace("-", "_")
        return getattr(self, attr_name, HookStageConfig())
