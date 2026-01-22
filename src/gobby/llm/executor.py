"""
Abstract base class for agent executors.

AgentExecutor defines the interface for executing agentic loops with tool calling.
Each LLM provider implements this interface to enable subagent spawning.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ToolSchema:
    """Schema definition for an MCP tool."""

    name: str
    """Tool name (e.g., 'create_task')."""

    description: str
    """Human-readable description of what the tool does."""

    input_schema: dict[str, Any]
    """JSON Schema for the tool's input parameters."""

    server_name: str | None = None
    """Optional server name this tool belongs to (e.g., 'gobby-tasks')."""


@dataclass
class ToolResult:
    """Result from executing a tool call."""

    tool_name: str
    """Name of the tool that was called."""

    success: bool
    """Whether the tool call succeeded."""

    result: Any = None
    """Result data from the tool (if success=True)."""

    error: str | None = None
    """Error message (if success=False)."""


@dataclass
class ToolCallRecord:
    """Record of a tool call made during agent execution."""

    tool_name: str
    """Name of the tool that was called."""

    arguments: dict[str, Any]
    """Arguments passed to the tool."""

    result: ToolResult | None = None
    """Result from the tool execution."""


@dataclass
class CostInfo:
    """Cost information from an LLM call."""

    prompt_tokens: int = 0
    """Number of tokens in the prompt."""

    completion_tokens: int = 0
    """Number of tokens in the completion."""

    total_cost: float = 0.0
    """Total cost in USD for this call."""

    model: str = ""
    """Model used for this call (LiteLLM format with prefix)."""


@dataclass
class AgentResult:
    """Result from running an agent to completion."""

    output: str
    """Final text output from the agent."""

    status: Literal["success", "partial", "blocked", "timeout", "error"]
    """Completion status of the agent run."""

    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    """List of all tool calls made during execution."""

    artifacts: dict[str, Any] = field(default_factory=dict)
    """Structured artifacts produced by the agent (via complete() tool)."""

    files_modified: list[str] = field(default_factory=list)
    """List of files modified during execution."""

    next_steps: list[str] = field(default_factory=list)
    """Suggested next steps from the agent."""

    error: str | None = None
    """Error message if status is 'error'."""

    turns_used: int = 0
    """Number of turns used during execution."""

    run_id: str | None = None
    """ID of the agent run (set by AgentRunner)."""

    child_session_id: str | None = None
    """ID of the child session created for this agent (set by AgentRunner)."""

    cost_info: CostInfo | None = None
    """Cost tracking information (populated by LiteLLM executor)."""


# Type alias for the tool handler callback
ToolHandler = Callable[[str, dict[str, Any]], Awaitable[ToolResult]]
"""
Callback function to execute a tool call.

Args:
    tool_name: Name of the tool to execute.
    arguments: Arguments to pass to the tool.

Returns:
    ToolResult with success/failure and result data.
"""


class AgentExecutor(ABC):
    """
    Abstract base class for executing agentic loops with tool calling.

    Each LLM provider (Claude, Gemini, Codex, LiteLLM) implements this interface
    to enable subagent spawning. The executor handles:

    - Running the agent loop with tool calling
    - Enforcing turn limits and timeouts
    - Calling tools via the provided tool_handler
    - Detecting completion (via 'complete' tool or natural end)
    - Returning structured results

    The tool_handler callback is provided by the caller (AgentRunner) and handles:
    - Workflow-based tool filtering
    - Routing to MCP servers
    - Recording tool metrics

    Example usage:
        >>> executor = ClaudeExecutor(config)
        >>> result = await executor.run(
        ...     prompt="Create a task called 'Fix bug'",
        ...     tools=[ToolSchema(name="create_task", ...)],
        ...     tool_handler=my_tool_handler,
        ... )
        >>> print(result.output)
        >>> print(result.status)
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Return the provider name for this executor.

        Returns:
            Provider name (e.g., "claude", "gemini", "litellm", "codex").
        """
        pass

    @abstractmethod
    async def run(
        self,
        prompt: str,
        tools: list[ToolSchema],
        tool_handler: ToolHandler,
        system_prompt: str | None = None,
        model: str | None = None,
        max_turns: int = 10,
        timeout: float = 120.0,
    ) -> AgentResult:
        """
        Execute an agentic loop with tool calling.

        Runs the agent with the given prompt, making tool calls as needed
        until completion, max_turns, or timeout.

        Args:
            prompt: The user prompt to process.
            tools: List of available tools with their schemas.
            tool_handler: Callback to execute tool calls. This is called
                whenever the agent wants to use a tool.
            system_prompt: Optional system prompt to set agent behavior.
            model: Optional model override. If None, uses provider default.
            max_turns: Maximum number of turns before stopping (default: 10).
            timeout: Maximum execution time in seconds (default: 120.0).

        Returns:
            AgentResult containing output, status, tool calls, and artifacts.

        Raises:
            No exceptions should be raised - errors are captured in AgentResult.
        """
        pass

    async def run_with_complete_tool(
        self,
        prompt: str,
        tools: list[ToolSchema],
        tool_handler: ToolHandler,
        system_prompt: str | None = None,
        model: str | None = None,
        max_turns: int = 10,
        timeout: float = 120.0,
    ) -> AgentResult:
        """
        Execute an agentic loop that requires explicit completion via 'complete' tool.

        This is a convenience wrapper that adds the 'complete' tool to the
        available tools and watches for its invocation to terminate the loop.

        The complete tool signature:
            complete(
                output: str,
                status: Literal["success", "partial", "blocked"] = "success",
                artifacts: dict[str, Any] = {},
                files_modified: list[str] = [],
                next_steps: list[str] = [],
            )

        Args:
            prompt: The user prompt to process.
            tools: List of available tools (complete tool is added automatically).
            tool_handler: Callback to execute tool calls.
            system_prompt: Optional system prompt.
            model: Optional model override.
            max_turns: Maximum turns before stopping.
            timeout: Maximum execution time in seconds.

        Returns:
            AgentResult populated from the complete() call, or with status='timeout'
            if the agent didn't call complete() before limits were reached.
        """
        # Add complete tool schema
        complete_tool = ToolSchema(
            name="complete",
            description=(
                "Signal that you have completed the task. Call this when you are done "
                "with all work. Provide a summary of what was accomplished, any artifacts "
                "produced, and suggested next steps."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "output": {
                        "type": "string",
                        "description": "Summary of what was accomplished.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["success", "partial", "blocked"],
                        "default": "success",
                        "description": "Completion status.",
                    },
                    "artifacts": {
                        "type": "object",
                        "description": "Structured outputs from the task.",
                        "default": {},
                    },
                    "files_modified": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of files that were modified.",
                        "default": [],
                    },
                    "next_steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Suggested next steps for the caller.",
                        "default": [],
                    },
                },
                "required": ["output"],
            },
        )

        all_tools = [*tools, complete_tool]
        completion_result: AgentResult | None = None

        async def wrapped_handler(tool_name: str, arguments: dict[str, Any]) -> ToolResult:
            nonlocal completion_result

            if tool_name == "complete":
                # Validate status against allowed values for complete() tool
                allowed_statuses = {"success", "partial", "blocked"}
                raw_status = arguments.get("status")
                validated_status: Literal["success", "partial", "blocked"] = (
                    raw_status if raw_status in allowed_statuses else "success"
                )

                # Extract completion data
                completion_result = AgentResult(
                    output=arguments.get("output", ""),
                    status=validated_status,
                    artifacts=arguments.get("artifacts", {}),
                    files_modified=arguments.get("files_modified", []),
                    next_steps=arguments.get("next_steps", []),
                )
                return ToolResult(
                    tool_name="complete",
                    success=True,
                    result="Task completed.",
                )

            # Delegate to the original handler
            return await tool_handler(tool_name, arguments)

        # Run with the wrapped handler
        result = await self.run(
            prompt=prompt,
            tools=all_tools,
            tool_handler=wrapped_handler,
            system_prompt=system_prompt,
            model=model,
            max_turns=max_turns,
            timeout=timeout,
        )

        # If complete() was called, use that result (preserving tool_calls and turns)
        if completion_result is not None:
            completion_result.tool_calls = result.tool_calls
            completion_result.turns_used = result.turns_used
            completion_result.cost_info = result.cost_info
            return completion_result

        # Otherwise, return the raw result (might be timeout or natural end)
        return result
