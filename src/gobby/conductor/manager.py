"""ConductorManager — persistent tick-based orchestration agent.

The conductor is a ChatSession (haiku model) that receives cron ticks,
checks task/pipeline states, and dispatches dev/QA agents. Between ticks
it's idle; autocompress handles context growth.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.config.conductor import ConductorConfig
    from gobby.servers.chat_session import ChatSession
    from gobby.storage.cron_models import CronJob
    from gobby.storage.sessions import LocalSessionManager

logger = logging.getLogger(__name__)

CONDUCTOR_SYSTEM_PROMPT = """\
You are the Conductor — a persistent orchestration agent for the Gobby platform.

## Role
You receive periodic ticks and decide what work needs to happen. You are the brain
that keeps development moving forward.

## On Each Tick
1. Check task state: use `list_tasks` and `suggest_next_tasks` to find ready work
2. Check pipeline state: use `get_pipeline_status` to find stalled or waiting pipelines
3. Check budget: use `get_budget_status` to verify token/cost limits
4. Dispatch agents: use `spawn_agent` or `dispatch_batch` for ready tasks
5. Report: briefly summarize what you did or found

## Rules
- Be concise. You are a daemon, not a conversationalist.
- Only dispatch work when tasks are ready and budget allows.
- If nothing needs attention, say "No action needed" and stop.
- Use progressive tool discovery: list_mcp_servers → list_tools → get_tool_schema → call_tool.
- Never dispatch agents for tasks that already have active agents.
"""


class ConductorManager:
    """Manages a persistent ChatSession that acts as the tick-based conductor.

    Implements the CronHandler interface (__call__) so it can be registered
    directly with CronExecutor.register_handler().
    """

    def __init__(
        self,
        project_id: str,
        project_path: str | None,
        session_manager: LocalSessionManager,
        config: ConductorConfig,
    ) -> None:
        self._project_id = project_id
        self._project_path = project_path
        self._session_manager = session_manager
        self._config = config
        self._session: ChatSession | None = None
        self._busy = False
        self._last_activity: datetime | None = None
        self._conversation_id = f"conductor-{project_id}"

    async def __call__(self, job: CronJob) -> str:
        """CronHandler interface — called by CronExecutor on each tick."""
        if self._config.skip_if_busy and self._busy:
            return "Conductor busy, skipping tick"
        return await self._handle_tick()

    async def _handle_tick(self) -> str:
        """Process a conductor tick."""
        self._busy = True
        try:
            session = await self._ensure_session()
            self._last_activity = datetime.now(UTC)
            tick_msg = (
                f"Conductor tick at {datetime.now(UTC).isoformat()}. "
                "Check tasks, pipelines, and budget. Dispatch agents if needed."
            )
            parts: list[str] = []
            async for event in session.send_message(tick_msg):
                from gobby.llm.claude_models import DoneEvent, TextChunk

                if isinstance(event, TextChunk):
                    parts.append(event.content)
                elif isinstance(event, DoneEvent):
                    break
            return f"Conductor: {''.join(parts)[:500]}"
        except Exception as e:
            logger.warning("Conductor tick failed: %s", e)
            await self._destroy_session()
            return f"Conductor tick failed: {e}"
        finally:
            self._busy = False

    async def _ensure_session(self) -> ChatSession:
        """Get or create the conductor ChatSession.

        Tears down idle sessions that haven't received a tick within
        idle_timeout_seconds, then creates a fresh one.
        """
        # Tear down idle sessions
        if self._session and self._last_activity:
            idle = (datetime.now(UTC) - self._last_activity).total_seconds()
            if idle > self._config.idle_timeout_seconds:
                logger.info("Conductor idle for %.0fs, tearing down session", idle)
                await self._destroy_session()

        if self._session and self._session.is_connected:
            return self._session

        # Lazy import to avoid circular deps at module level
        from gobby.servers.chat_session import ChatSession

        session = ChatSession(
            conversation_id=self._conversation_id,
            project_id=self._project_id,
            project_path=self._project_path,
        )
        session.system_prompt_override = CONDUCTOR_SYSTEM_PROMPT

        # Register in DB for session tracking
        db_session = self._session_manager.register(
            external_id=self._conversation_id,
            machine_id="conductor",
            source="conductor",
            project_id=self._project_id,
        )
        session.db_session_id = db_session.id
        session.seq_num = db_session.seq_num
        session._session_manager_ref = self._session_manager

        await session.start(model=self._config.model)
        self._session = session
        logger.info("Conductor session created (model=%s)", self._config.model)
        return session

    async def _destroy_session(self) -> None:
        """Tear down the current conductor session."""
        if self._session:
            try:
                await self._session.stop()
            except Exception as e:
                logger.debug("Error stopping conductor session: %s", e)
            self._session = None

    async def shutdown(self) -> None:
        """Clean shutdown — called by GobbyRunner on stop."""
        await self._destroy_session()
        logger.info("Conductor shut down")
