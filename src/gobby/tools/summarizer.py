"""
Tool description summarization using Claude Agent SDK.

Intelligently summarizes long MCP tool descriptions to fit within
the 200-character limit for config file storage.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.config.features import ToolSummarizerConfig
from gobby.prompts import PromptLoader

logger = logging.getLogger(__name__)

# Maximum description length for tool summaries
MAX_DESCRIPTION_LENGTH = 200

# Module-level config reference (set by init_summarizer_config)
_config: ToolSummarizerConfig | None = None
_loader: PromptLoader | None = None

DEFAULT_SUMMARY_PROMPT = """Summarize this MCP tool description in 180 characters or less.
Keep it to three sentences or less. Be concise and preserve the key functionality.
Do not add quotes, extra formatting, or code examples.

Description: {description}

Summary:"""

DEFAULT_SUMMARY_SYSTEM_PROMPT = "You are a technical summarizer. Create concise tool descriptions."

DEFAULT_SERVER_DESC_PROMPT = """Write a single concise sentence describing what the '{server_name}' MCP server does based on its tools.

Tools:
{tools_list}

Description (1 sentence, try to keep under 100 characters):"""

DEFAULT_SERVER_DESC_SYSTEM_PROMPT = "You write concise technical descriptions."


def init_summarizer_config(config: ToolSummarizerConfig, project_dir: str | None = None) -> None:
    """Initialize the summarizer with configuration."""
    from pathlib import Path

    global _config, _loader
    _config = config
    _loader = PromptLoader(project_dir=Path(project_dir) if project_dir else None)
    # Register fallbacks
    _loader.register_fallback("features/tool_summary", lambda: DEFAULT_SUMMARY_PROMPT)
    _loader.register_fallback("features/tool_summary_system", lambda: DEFAULT_SUMMARY_SYSTEM_PROMPT)
    _loader.register_fallback("features/server_description", lambda: DEFAULT_SERVER_DESC_PROMPT)
    _loader.register_fallback(
        "features/server_description_system", lambda: DEFAULT_SERVER_DESC_SYSTEM_PROMPT
    )


def _get_config() -> ToolSummarizerConfig:
    """Get the current config, with fallback to defaults."""
    if _config is not None:
        return _config
    # Import here to avoid circular imports
    from gobby.config.features import ToolSummarizerConfig

    # Ensure loader defaults exist even if init wasn't called
    global _loader
    if _loader is None:
        _loader = PromptLoader()

    return ToolSummarizerConfig()


async def _summarize_description_with_claude(description: str) -> str:
    """
    Summarize a tool description using Claude Agent SDK.

    Args:
        description: Long tool description to summarize

    Returns:
        Summarized description (max 180 chars)
    """
    config = _get_config()

    try:
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

        # Get summary prompt
        prompt_path = config.prompt_path or "features/tool_summary"
        try:
            # We assume _loader is initialized by _get_config() logic or init
            if _loader is None:
                raise RuntimeError("Summarizer not initialized")
            prompt = _loader.render(prompt_path, {"description": description})
        except (FileNotFoundError, OSError, KeyError, ValueError, RuntimeError) as e:
            logger.debug(f"Failed to load prompt from {prompt_path}: {e}, using default")
            prompt = DEFAULT_SUMMARY_PROMPT.format(description=description)

        # Get system prompt
        sys_prompt_path = config.system_prompt_path or "features/tool_summary_system"
        try:
            if _loader is None:
                raise RuntimeError("Summarizer not initialized")
            system_prompt = _loader.render(sys_prompt_path, {})
        except (FileNotFoundError, OSError, KeyError, ValueError, RuntimeError) as e:
            logger.debug(f"Failed to load system prompt from {sys_prompt_path}: {e}, using default")
            system_prompt = DEFAULT_SUMMARY_SYSTEM_PROMPT

        # Configure for single-turn completion
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            max_turns=1,
            model=config.model,
            allowed_tools=[],
            permission_mode="default",
        )

        # Run async query
        summary_text = ""
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        summary_text = block.text
        return summary_text.strip()

    except Exception as e:
        logger.warning(f"Failed to summarize description with Claude: {e}")
        # Fallback: truncate to 200 chars with ellipsis
        return description[:197] + "..." if len(description) > 200 else description


async def summarize_tools(tools: list[Any]) -> list[dict[str, Any]]:
    """
    Create lightweight tool summaries with intelligent description shortening.

    Args:
        tools: List of MCP Tool objects with name, description, and inputSchema

    Returns:
        List of dicts with name, summarized description, and args:
        [{"name": "tool_name", "description": "Short summary...", "args": {...}}]
    """
    summaries = []

    for tool in tools:
        description = tool.description or ""

        # Summarize if needed
        if len(description) > MAX_DESCRIPTION_LENGTH:
            logger.debug(
                f"Summarizing description for tool '{tool.name}' ({len(description)} chars)"
            )
            description = await _summarize_description_with_claude(description)

        summaries.append(
            {
                "name": tool.name,
                "description": description,
                "args": tool.inputSchema if hasattr(tool, "inputSchema") else {},
            }
        )

    return summaries


async def generate_server_description(
    server_name: str, tool_summaries: list[dict[str, Any]]
) -> str:
    """
    Generate a concise server description from tool summaries.

    Uses Claude Haiku to synthesize a single-sentence description of what
    the MCP server does based on all its available tools.

    Args:
        server_name: Name of the MCP server
        tool_summaries: List of tool summaries from summarize_tools()

    Returns:
        Single-sentence description (aiming for <100 chars)
    """
    config = _get_config()

    try:
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

        # Build tools list for prompt
        tools_list = "\n".join([f"- {t['name']}: {t['description']}" for t in tool_summaries])

        # Build prompt
        prompt_path = config.server_description_prompt_path or "features/server_description"
        context = {
            "server_name": server_name,
            "tools_list": tools_list,
        }
        try:
            if _loader is None:
                _get_config()  # force init
            if _loader is None:
                # Still None after _get_config, use default
                prompt = DEFAULT_SERVER_DESC_PROMPT.format(**context)
            else:
                prompt = _loader.render(prompt_path, context)
        except (FileNotFoundError, OSError, KeyError, ValueError, RuntimeError) as e:
            logger.debug(f"Failed to load prompt from {prompt_path}: {e}, using default")
            prompt = DEFAULT_SERVER_DESC_PROMPT.format(**context)

        # Get system prompt
        sys_prompt_path = (
            config.server_description_system_prompt_path or "features/server_description_system"
        )
        try:
            if _loader is None:
                system_prompt = DEFAULT_SERVER_DESC_SYSTEM_PROMPT
            else:
                system_prompt = _loader.render(sys_prompt_path, {})
        except (FileNotFoundError, OSError, KeyError, ValueError, RuntimeError) as e:
            logger.debug(f"Failed to load system prompt from {sys_prompt_path}: {e}, using default")
            system_prompt = DEFAULT_SERVER_DESC_SYSTEM_PROMPT

        # Configure for single-turn completion
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            max_turns=1,
            model=config.model,
            allowed_tools=[],
            permission_mode="default",
        )

        # Run async query
        description = ""
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        description = block.text

        return description.strip()

    except Exception as e:
        logger.warning(f"Failed to generate server description for '{server_name}': {e}")
        # Fallback: Generate simple description from first few tools
        if tool_summaries:
            first_tools = ", ".join([t["name"] for t in tool_summaries[:3]])
            return f"Provides {first_tools} and more"
        return f"MCP server: {server_name}"
