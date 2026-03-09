"""
Codex-based autonomous agent runner.

Uses CodexAppServerClient for in-process autonomous execution with proper
hooks, stuck detection, and progress tracking — the same foundation as
the web chat UI but for autonomous agents.

Usage from spawn_executor:
    runner = CodexAutonomousRunner(...)
    task = asyncio.create_task(runner.run())
    # task stored on RunningAgent for lifecycle monitoring
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from gobby.adapters.codex_impl.adapter import CodexAdapter
from gobby.adapters.codex_impl.client import CodexAppServerClient
from gobby.servers.chat_session_helpers import build_compaction_context

logger = logging.getLogger(__name__)

# Type alias for the lifecycle callback provided by the caller.
# Receives event data dict, returns workflow response dict or None.
LifecycleCallback = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


class CodexAutonomousRunner:
    """In-process Codex runner for autonomous agent execution.

    Each runner owns a private CodexAppServerClient instance (not shared
    with the daemon). Multiple autonomous agents can run concurrently
    without handler conflicts.

    Codex handles tool calls internally — no multi-turn loop needed.
    Start thread → run one turn → turn completes.
    """

    def __init__(
        self,
        *,
        session_id: str,
        run_id: str,
        project_id: str,
        cwd: str,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,  # Interface compat, not used by Codex
        agent_run_manager: Any = None,
        on_before_agent: LifecycleCallback | None = None,
        on_pre_tool: LifecycleCallback | None = None,
        on_post_tool: LifecycleCallback | None = None,
        on_stop: LifecycleCallback | None = None,
        on_pre_compact: LifecycleCallback | None = None,  # Accepted, unused
        seq_num: int | None = None,
        resume_session_id: str | None = None,  # Codex thread_id for resume
    ) -> None:
        self.session_id = session_id
        self.run_id = run_id
        self.project_id = project_id
        self.cwd = cwd
        self.prompt = prompt
        self.model = model
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.agent_run_manager = agent_run_manager
        self.seq_num = seq_num
        self.resume_session_id = resume_session_id

        # Lifecycle callbacks
        self._on_before_agent = on_before_agent
        self._on_pre_tool = on_pre_tool
        self._on_post_tool = on_post_tool
        self._on_stop = on_stop
        self._on_pre_compact = on_pre_compact

        # Captured after thread creation
        self.thread_id: str | None = None
        self._client: CodexAppServerClient | None = None
        self._adapter: CodexAdapter | None = None

    async def run(self) -> str:
        """Execute the autonomous agent run.

        Returns the accumulated text output from the agent.
        Stores thread_id for future cross-mode resume.
        """
        if not CodexAdapter.is_codex_available():
            error = "Codex CLI not found in PATH"
            logger.error("CodexAutonomousRunner: %s", error)
            if self.agent_run_manager:
                self.agent_run_manager.fail(self.run_id, error=error)
            raise RuntimeError(error)

        session_ref = f"#{self.seq_num}" if self.seq_num else self.session_id

        # Build context prefix with system prompt + env context
        context_parts: list[str] = []
        if self.system_prompt:
            context_parts.append(self.system_prompt)
        context_parts.append(
            build_compaction_context(
                session_ref=session_ref,
                project_id=self.project_id,
                cwd=self.cwd,
                source="codex_autonomous",
            )
        )
        context_prefix = "\n\n".join(context_parts)

        # Create private client and adapter
        self._client = CodexAppServerClient()
        self._adapter = CodexAdapter()

        # Event tracking
        accumulated_text = ""
        turn_completed = asyncio.Event()
        turn_error: str | None = None

        def _on_delta(method: str, params: dict[str, Any]) -> None:
            nonlocal accumulated_text
            delta = params.get("delta", "")
            if delta:
                accumulated_text += delta

        def _on_turn_completed(method: str, params: dict[str, Any]) -> None:
            nonlocal turn_error
            error = params.get("error")
            if error:
                turn_error = str(error)
            turn_completed.set()

        async def _on_item_completed(method: str, params: dict[str, Any]) -> None:
            # Fire post-tool callback for tool items
            if self._on_post_tool:
                item = params.get("item", {})
                item_type = item.get("type", "")
                if item_type in CodexAdapter.TOOL_ITEM_TYPES:
                    tool_name = (
                        self._adapter.normalize_tool_name(item_type) if self._adapter else item_type
                    )
                    await self._on_post_tool(
                        {
                            "tool_name": tool_name,
                            "tool_input": item.get("metadata", {}),
                        }
                    )

        # Approval handler — auto-approve but route through pre_tool callback
        async def _handle_approval(method: str, params: dict[str, Any]) -> dict[str, Any]:
            if self._on_pre_tool and self._adapter:
                item_type = params.get("type", method.split("/")[-1] if "/" in method else method)
                tool_name = self._adapter.normalize_tool_name(item_type)
                resp = await self._on_pre_tool(
                    {
                        "tool_name": tool_name,
                        "tool_input": params,
                    }
                )
                if resp and resp.get("decision") == "block":
                    return {
                        "decision": "decline",
                        "reason": resp.get("reason", "Blocked by lifecycle"),
                    }
            return {"decision": "accept"}

        try:
            # Register handlers BEFORE start
            self._client.register_approval_handler(_handle_approval)
            self._client.add_notification_handler("item/agentMessage/delta", _on_delta)
            self._client.add_notification_handler("turn/completed", _on_turn_completed)

            # Wrap async post-tool handler for sync notification API
            _loop = asyncio.get_running_loop()

            def _on_item_completed_sync(method: str, params: dict[str, Any]) -> None:
                _loop.create_task(_on_item_completed(method, params))

            self._client.add_notification_handler("item/completed", _on_item_completed_sync)

            await self._client.start()

            # Start or resume thread
            if self.resume_session_id:
                thread = await self._client.resume_thread(self.resume_session_id)
            else:
                thread = await self._client.start_thread(
                    cwd=self.cwd,
                    model=self.model,
                    approval_policy="never",
                )
            self.thread_id = thread.id

            logger.info(
                "CodexAutonomousRunner started: run_id=%s session=%s thread=%s model=%s",
                self.run_id,
                session_ref,
                self.thread_id,
                self.model,
            )

            # Fire before_agent callback
            if self._on_before_agent:
                resp = await self._on_before_agent(
                    {
                        "prompt": self.prompt,
                        "source": "codex_autonomous",
                    }
                )
                if resp and resp.get("context"):
                    context_prefix = context_prefix + "\n\n" + resp["context"]

            # Start the turn
            await self._client.start_turn(
                thread_id=self.thread_id,
                prompt=self.prompt,
                context_prefix=context_prefix,
            )

            # Wait for turn completion
            await turn_completed.wait()

            if turn_error:
                logger.warning(
                    "CodexAutonomousRunner turn error: run_id=%s error=%s",
                    self.run_id,
                    turn_error,
                )

            logger.info(
                "CodexAutonomousRunner completed: run_id=%s thread=%s chars=%d",
                self.run_id,
                self.thread_id,
                len(accumulated_text),
            )

            # Store thread_id for cross-mode resume
            if self.thread_id and self.agent_run_manager:
                self.agent_run_manager.update_sdk_session_id(self.run_id, self.thread_id)

            # Mark the agent run as complete
            if self.agent_run_manager:
                self.agent_run_manager.complete(
                    self.run_id,
                    result=accumulated_text[:10_000],
                )

            return accumulated_text

        except asyncio.CancelledError:
            logger.info("CodexAutonomousRunner cancelled: run_id=%s", self.run_id)
            if self.agent_run_manager:
                self.agent_run_manager.fail(self.run_id, error="Cancelled")
            raise
        except Exception as e:
            logger.error(
                "CodexAutonomousRunner failed: run_id=%s error=%s",
                self.run_id,
                e,
                exc_info=True,
            )
            if self.agent_run_manager:
                self.agent_run_manager.fail(self.run_id, error=str(e))
            raise
        finally:
            if self._client:
                try:
                    await self._client.stop()
                except Exception:
                    logger.debug("CodexAutonomousRunner: stop error (ignored)", exc_info=True)
                self._client = None
            self._adapter = None
