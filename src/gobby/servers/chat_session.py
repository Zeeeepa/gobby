"""
Chat session backed by ClaudeSDKClient for persistent multi-turn conversations.

Each ChatSession wraps a ClaudeSDKClient instance that maintains conversation
context across messages. Sessions are keyed by conversation_id (stable across
WebSocket reconnections) rather than ephemeral client_id.
"""

import asyncio
import logging
import os
import shutil
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookContext,
    HookMatcher,
    PermissionResultAllow,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolPermissionContext,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from claude_agent_sdk.types import (
    HookInput as SDKHookInput,
)
from claude_agent_sdk.types import (
    PostToolUseHookSpecificOutput,
    PreToolUseHookSpecificOutput,
    SyncHookJSONOutput,
    UserPromptSubmitHookSpecificOutput,
)

from gobby.llm.claude_models import (
    ChatEvent,
    DoneEvent,
    TextChunk,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)

logger = logging.getLogger(__name__)

# Fallback system prompt if the prompts system is unavailable
_FALLBACK_SYSTEM_PROMPT = "You are Gobby, a helpful AI coding assistant."


def _load_chat_system_prompt() -> str:
    """Load the chat system prompt from the prompts system.

    Uses PromptLoader with standard override precedence:
    project .gobby/prompts/ -> global ~/.gobby/prompts/ -> bundled defaults.
    """
    try:
        from gobby.prompts.loader import PromptLoader

        loader = PromptLoader()
        template = loader.load("chat/system")
        return template.content
    except Exception as e:
        logger.warning(f"Failed to load chat/system prompt, using fallback: {e}")
        return _FALLBACK_SYSTEM_PROMPT


def _find_cli_path() -> str | None:
    """Find Claude CLI path without resolving symlinks."""
    cli_path = shutil.which("claude")
    if cli_path and os.path.exists(cli_path) and os.access(cli_path, os.X_OK):
        return cli_path
    return None


def _find_project_root() -> Path | None:
    """Find the gobby project root from source tree.

    In dev mode the daemon runs from the repo, so we can derive the
    project root from this file's location.
    """
    candidate = Path(__file__).parent.parent.parent.parent
    if (candidate / ".gobby").is_dir():
        return candidate
    return None


def _find_mcp_config() -> str | None:
    """Find .mcp.json config file for MCP tool access."""
    cwd_config = Path.cwd() / ".mcp.json"
    if cwd_config.exists():
        return str(cwd_config)

    project_root = _find_project_root()
    if project_root:
        config = project_root / ".mcp.json"
        if config.exists():
            return str(config)

    return None


def _parse_server_name(full_tool_name: str) -> str:
    """Extract server name from mcp__{server}__{tool} format."""
    if full_tool_name.startswith("mcp__"):
        parts = full_tool_name.split("__")
        if len(parts) >= 2:
            return parts[1]
    return "builtin"


def _response_to_prompt_output(resp: dict[str, Any] | None) -> SyncHookJSONOutput:
    """Convert workflow HookResponse dict to UserPromptSubmit SDK output."""
    if not resp:
        return SyncHookJSONOutput()
    output = SyncHookJSONOutput()
    if resp.get("decision") == "block":
        output["decision"] = "block"
        if resp.get("reason"):
            output["reason"] = resp["reason"]
    context = resp.get("context")
    if context:
        output["hookSpecificOutput"] = UserPromptSubmitHookSpecificOutput(
            hookEventName="UserPromptSubmit",
            additionalContext=context,
        )
    return output


def _response_to_pre_tool_output(resp: dict[str, Any] | None) -> SyncHookJSONOutput:
    """Convert workflow HookResponse dict to PreToolUse SDK output."""
    if not resp:
        return SyncHookJSONOutput()
    output = SyncHookJSONOutput()
    if resp.get("decision") == "block":
        specific: PreToolUseHookSpecificOutput = PreToolUseHookSpecificOutput(
            hookEventName="PreToolUse",
            permissionDecision="deny",
        )
        if resp.get("reason"):
            specific["permissionDecisionReason"] = resp["reason"]
        output["hookSpecificOutput"] = specific
        if resp.get("reason"):
            output["reason"] = resp["reason"]
    elif resp.get("context"):
        # Inject context via reason field for PreToolUse (no additionalContext)
        output["reason"] = resp["context"]
    return output


def _response_to_post_tool_output(resp: dict[str, Any] | None) -> SyncHookJSONOutput:
    """Convert workflow HookResponse dict to PostToolUse SDK output."""
    if not resp:
        return SyncHookJSONOutput()
    output = SyncHookJSONOutput()
    context = resp.get("context")
    if context:
        output["hookSpecificOutput"] = PostToolUseHookSpecificOutput(
            hookEventName="PostToolUse",
            additionalContext=context,
        )
    return output


def _response_to_stop_output(resp: dict[str, Any] | None) -> SyncHookJSONOutput:
    """Convert workflow HookResponse dict to Stop SDK output."""
    if not resp:
        return SyncHookJSONOutput()
    output = SyncHookJSONOutput()
    if resp.get("decision") == "block":
        output["decision"] = "block"
        if resp.get("reason"):
            output["reason"] = resp["reason"]
    return output


def _response_to_compact_output(resp: dict[str, Any] | None) -> SyncHookJSONOutput:
    """Convert workflow HookResponse dict to PreCompact SDK output."""
    if not resp:
        return SyncHookJSONOutput()
    output = SyncHookJSONOutput()
    context = resp.get("context")
    if context:
        # PreCompact doesn't have hook-specific additionalContext,
        # use reason to surface info to the agent
        output["reason"] = context
    return output


@dataclass
class ChatSession:
    """
    A persistent chat session backed by ClaudeSDKClient.

    Maintains conversation context across messages and survives
    WebSocket disconnections. Sessions are identified by conversation_id.
    """

    conversation_id: str
    db_session_id: str | None = field(default=None)
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    _client: ClaudeSDKClient | None = field(default=None, repr=False)
    _connected: bool = field(default=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _model: str | None = field(default=None, repr=False)
    _pending_question: dict[str, Any] | None = field(default=None, repr=False)
    _pending_answer_event: asyncio.Event | None = field(default=None, repr=False)
    _pending_answers: dict[str, str] | None = field(default=None, repr=False)

    # Lifecycle callbacks — set by ChatMixin to bridge SDK hooks to workflow engine
    _on_before_agent: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None = field(
        default=None, repr=False
    )
    _on_pre_tool: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None = field(
        default=None, repr=False
    )
    _on_post_tool: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None = field(
        default=None, repr=False
    )
    _on_pre_compact: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None = field(
        default=None, repr=False
    )
    _on_stop: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None = field(
        default=None, repr=False
    )

    async def start(self, model: str | None = None) -> None:
        """Connect the ClaudeSDKClient with configured options."""
        cli_path = _find_cli_path()
        if not cli_path:
            raise RuntimeError("Claude CLI not found in PATH")

        mcp_config = _find_mcp_config()
        self._model = model

        # Use the gobby project root if found (dev mode), otherwise cwd.
        # TODO: Add project picker to UI for production so the user selects
        # the project before chatting, and pass that path here instead.
        project_root = _find_project_root()
        cwd = str(project_root) if project_root else str(Path.cwd())

        system_prompt = _load_chat_system_prompt()
        # Inject working directory so the agent doesn't hallucinate paths
        system_prompt += f"\n\n## Environment\n- Working directory: {cwd}\n"

        # Build SDK hooks from lifecycle callbacks
        sdk_hooks = self._build_sdk_hooks()

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            max_turns=None,
            model=model or "claude-sonnet-4-5",
            allowed_tools=["mcp__gobby__*"],
            can_use_tool=self._can_use_tool,
            cli_path=cli_path,
            mcp_servers=mcp_config if mcp_config is not None else {},
            cwd=cwd,
            hooks=sdk_hooks if sdk_hooks else None,  # type: ignore[arg-type]
        )

        self._client = ClaudeSDKClient(options=options)
        await self._client.connect()
        self._connected = True
        self.last_activity = datetime.now(UTC)
        logger.debug(f"ChatSession {self.conversation_id} started")

    def _build_sdk_hooks(self) -> dict[str, list[HookMatcher]] | None:
        """Build SDK hook matchers from lifecycle callbacks."""
        hooks: dict[str, list[HookMatcher]] = {}

        if self._on_before_agent:
            cb = self._on_before_agent

            async def _prompt_hook(
                inp: SDKHookInput,
                tool_use_id: str | None,
                ctx: HookContext,
            ) -> SyncHookJSONOutput:
                data = {"prompt_text": inp.get("prompt", ""), "source": "claude_sdk_web_chat"}  # type: ignore[union-attr]
                resp = await cb(data)
                return _response_to_prompt_output(resp)

            hooks["UserPromptSubmit"] = [HookMatcher(matcher=None, hooks=[_prompt_hook])]

        if self._on_pre_tool:
            cb_pre = self._on_pre_tool

            async def _pre_tool_hook(
                inp: SDKHookInput,
                tool_use_id: str | None,
                ctx: HookContext,
            ) -> SyncHookJSONOutput:
                data = {
                    "tool_name": inp.get("tool_name", ""),  # type: ignore[union-attr]
                    "tool_input": inp.get("tool_input", {}),  # type: ignore[union-attr]
                }
                resp = await cb_pre(data)
                return _response_to_pre_tool_output(resp)

            hooks["PreToolUse"] = [HookMatcher(matcher=None, hooks=[_pre_tool_hook])]

        if self._on_post_tool:
            cb_post = self._on_post_tool

            async def _post_tool_hook(
                inp: SDKHookInput,
                tool_use_id: str | None,
                ctx: HookContext,
            ) -> SyncHookJSONOutput:
                data = {
                    "tool_name": inp.get("tool_name", ""),  # type: ignore[union-attr]
                    "tool_input": inp.get("tool_input", {}),  # type: ignore[union-attr]
                    "tool_response": inp.get("tool_response"),  # type: ignore[union-attr]
                }
                resp = await cb_post(data)
                return _response_to_post_tool_output(resp)

            hooks["PostToolUse"] = [HookMatcher(matcher=None, hooks=[_post_tool_hook])]

        if self._on_stop:
            cb_stop = self._on_stop

            async def _stop_hook(
                inp: SDKHookInput,
                tool_use_id: str | None,
                ctx: HookContext,
            ) -> SyncHookJSONOutput:
                data = {"stop_hook_active": inp.get("stop_hook_active", False)}  # type: ignore[union-attr]
                resp = await cb_stop(data)
                return _response_to_stop_output(resp)

            hooks["Stop"] = [HookMatcher(matcher=None, hooks=[_stop_hook])]

        if self._on_pre_compact:
            cb_compact = self._on_pre_compact

            async def _compact_hook(
                inp: SDKHookInput,
                tool_use_id: str | None,
                ctx: HookContext,
            ) -> SyncHookJSONOutput:
                data = {
                    "trigger": inp.get("trigger", "auto"),  # type: ignore[union-attr]
                }
                resp = await cb_compact(data)
                return _response_to_compact_output(resp)

            hooks["PreCompact"] = [HookMatcher(matcher=None, hooks=[_compact_hook])]

        return hooks if hooks else None

    async def _can_use_tool(
        self,
        tool_name: str,
        input_data: dict[str, Any],
        context: ToolPermissionContext,
    ) -> PermissionResultAllow:
        """Callback for tool permission checks.

        Auto-approves all tools except AskUserQuestion, which blocks
        until the user provides answers via provide_answer().
        """
        if tool_name != "AskUserQuestion":
            return PermissionResultAllow(updated_input=input_data)

        # Store the pending question and block until answered
        self._pending_question = input_data
        self._pending_answers = None
        self._pending_answer_event = asyncio.Event()

        try:
            await asyncio.wait_for(self._pending_answer_event.wait(), timeout=600.0)
        except TimeoutError:
            self._pending_answers = {"error": "Timed out waiting for user response"}
            logger.warning(f"AskUserQuestion timed out for session {self.conversation_id}")

        result = PermissionResultAllow(
            updated_input={
                "questions": input_data.get("questions", []),
                "answers": self._pending_answers,
            }
        )

        # Clear pending state
        self._pending_question = None
        self._pending_answer_event = None
        self._pending_answers = None

        return result

    def provide_answer(self, answers: dict[str, str]) -> None:
        """Provide answers to a pending AskUserQuestion, unblocking the callback."""
        self._pending_answers = answers
        if self._pending_answer_event is not None:
            self._pending_answer_event.set()

    @property
    def has_pending_question(self) -> bool:
        """Whether an AskUserQuestion is currently awaiting a response."""
        return self._pending_question is not None

    async def send_message(self, content: str | list[dict[str, Any]]) -> AsyncIterator[ChatEvent]:
        """
        Send a user message and yield streaming events.

        Content can be a plain string or a list of content blocks
        (e.g. text + images in the standard Claude API format).

        Yields ChatEvent instances (TextChunk, ToolCallEvent,
        ToolResultEvent, DoneEvent) matching the existing protocol.
        """
        if not self._client or not self._connected:
            raise RuntimeError("ChatSession not connected. Call start() first.")

        async with self._lock:
            self.last_activity = datetime.now(UTC)

            if isinstance(content, list):
                # SDK expects str or AsyncIterable[dict] — wrap content blocks
                # in an async generator yielding a single user message
                async def _content_blocks() -> AsyncIterator[dict[str, Any]]:
                    yield {"role": "user", "content": content}

                await self._client.query(_content_blocks())
            else:
                await self._client.query(content)

            tool_calls_count = 0
            needs_spacing_before_text = False
            has_text = False

            try:
                async for message in self._client.receive_response():
                    if isinstance(message, ResultMessage):
                        # Fallback: if no text was streamed (e.g. Opus thinking-only
                        # response), emit the ResultMessage.result as a TextChunk
                        if message.result and not has_text:
                            yield TextChunk(content=message.result)
                        cost_usd = getattr(message, "total_cost_usd", None)
                        duration_ms = getattr(message, "duration_ms", None)
                        yield DoneEvent(
                            tool_calls_count=tool_calls_count,
                            cost_usd=cost_usd,
                            duration_ms=duration_ms,
                        )

                    elif isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, ThinkingBlock):
                                yield ThinkingEvent(content=block.thinking)
                            elif isinstance(block, TextBlock):
                                has_text = True
                                text = block.text
                                if needs_spacing_before_text and text:
                                    text = text.lstrip("\n")
                                    if text:
                                        text = "\n\n" + text
                                yield TextChunk(content=text)
                                needs_spacing_before_text = False
                            elif isinstance(block, ToolUseBlock):
                                tool_calls_count += 1
                                server_name = _parse_server_name(block.name)
                                yield ToolCallEvent(
                                    tool_call_id=block.id,
                                    tool_name=block.name,
                                    server_name=server_name,
                                    arguments=block.input if isinstance(block.input, dict) else {},
                                )

                    elif isinstance(message, UserMessage):
                        if isinstance(message.content, list):
                            for block in message.content:
                                if isinstance(block, ToolResultBlock):
                                    is_error = getattr(block, "is_error", False)
                                    yield ToolResultEvent(
                                        tool_call_id=block.tool_use_id,
                                        success=not is_error,
                                        result=block.content if not is_error else None,
                                        error=str(block.content) if is_error else None,
                                    )
                                    needs_spacing_before_text = True

            except ExceptionGroup as eg:
                errors = [f"{type(exc).__name__}: {exc}" for exc in eg.exceptions]
                yield TextChunk(content=f"Generation failed: {'; '.join(errors)}")
                yield DoneEvent(tool_calls_count=tool_calls_count)
            except Exception as e:
                logger.error(f"ChatSession {self.conversation_id} error: {e}", exc_info=True)
                yield TextChunk(content=f"Generation failed: {e}")
                yield DoneEvent(tool_calls_count=tool_calls_count)

    async def interrupt(self) -> None:
        """Interrupt the current response stream."""
        if self._client and self._connected:
            try:
                await self._client.interrupt()
            except Exception as e:
                logger.warning(f"ChatSession {self.conversation_id} interrupt error: {e}")

    async def stop(self) -> None:
        """Disconnect the ClaudeSDKClient and clean up."""
        if self._client:
            try:
                await self._client.disconnect()
            except RuntimeError as e:
                # The SDK's Query._tg.__aexit__() raises RuntimeError when
                # stop() is called from a different asyncio task than the one
                # that called start() (e.g. idle cleanup or shutdown).
                if "cancel scope" in str(e):
                    logger.debug(
                        f"ChatSession {self.conversation_id} cross-task disconnect (expected): {e}"
                    )
                else:
                    logger.warning(f"ChatSession {self.conversation_id} disconnect error: {e}")
            except Exception as e:
                logger.warning(f"ChatSession {self.conversation_id} disconnect error: {e}")
            finally:
                self._client = None
                self._connected = False
                logger.debug(f"ChatSession {self.conversation_id} stopped")

    @property
    def model(self) -> str | None:
        """The current model for this session."""
        return self._model

    async def switch_model(self, new_model: str) -> None:
        """Switch to a different Claude model mid-conversation."""
        if not self._client or not self._connected:
            raise RuntimeError("ChatSession not connected")
        await self._client.set_model(new_model)
        self._model = new_model

    @property
    def is_connected(self) -> bool:
        """Whether the session is currently connected."""
        return self._connected
