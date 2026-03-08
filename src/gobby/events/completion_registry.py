"""Completion event registry for push-based async operation notifications.

In-memory event bus that:
1. Lets pipeline executor block on completion events (wait step type)
2. Triggers wake callbacks to notify subscribing sessions when operations complete
3. Fires pipeline continuation callbacks for event-driven re-invocation
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)

# Type for the wake callback: (session_id, message, result) -> None
WakeCallback = Callable[[str, str, dict[str, Any]], Coroutine[Any, Any, None]]

# Type for pipeline rerun callback: (continuation_config, agent_result_or_None) -> None
PipelineRerunCallback = Callable[[dict[str, Any], dict[str, Any] | None], Coroutine[Any, Any, None]]


class CompletionEventRegistry:
    """In-memory registry for completion events with subscriber notifications.

    Used by:
    - PipelineExecutor: `wait` step type blocks via registry.wait()
    - Daemon: registry.notify() fires wake callbacks for subscribed sessions
    - Orchestrator: pipeline continuations trigger re-invocation on agent completion
    """

    def __init__(
        self,
        wake_callback: WakeCallback | None = None,
        pipeline_rerun_callback: PipelineRerunCallback | None = None,
        db: DatabaseProtocol | None = None,
    ) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._subscribers: dict[str, list[str]] = {}
        self._continuation_prompts: dict[str, str] = {}
        self._pipeline_continuations: dict[str, dict[str, Any]] = {}
        self._wake_callback = wake_callback
        self._pipeline_rerun_callback = pipeline_rerun_callback
        self._db = db

    def register(
        self,
        completion_id: str,
        subscribers: list[str],
        continuation_prompt: str | None = None,
    ) -> None:
        """Register a completion event with subscriber session IDs.

        Args:
            completion_id: Unique ID (execution_id or run_id)
            subscribers: Session IDs to notify on completion
            continuation_prompt: Optional prompt describing what to do with results
        """
        if completion_id in self._events:
            logger.warning("Overwriting existing completion registration: %s", completion_id)
        self._events[completion_id] = asyncio.Event()
        self._subscribers[completion_id] = list(subscribers)
        if continuation_prompt:
            self._continuation_prompts[completion_id] = continuation_prompt

    def is_registered(self, completion_id: str) -> bool:
        """Check if a completion event is registered."""
        return completion_id in self._events

    def register_continuation(
        self,
        completion_id: str,
        continuation_config: dict[str, Any],
    ) -> None:
        """Register a pipeline continuation for a completion event.

        When the completion event fires, the pipeline_rerun_callback will be
        invoked with the continuation_config, triggering a new pipeline pass.
        Also persists to DB for daemon restart recovery.

        Args:
            completion_id: The completion event ID (typically a run_id)
            continuation_config: Dict with pipeline_name, inputs, session_id, project_id
        """
        self._pipeline_continuations[completion_id] = continuation_config

        # Persist to DB for restart recovery
        if self._db is not None:
            try:
                self._db.execute(
                    "INSERT OR REPLACE INTO pipeline_continuations (run_id, config_json) VALUES (?, ?)",
                    (completion_id, json.dumps(continuation_config)),
                )
            except Exception:
                logger.debug("Failed to persist continuation for %s", completion_id, exc_info=True)

        logger.debug(
            "Registered pipeline continuation for %s: pipeline=%s",
            completion_id,
            continuation_config.get("pipeline_name", "?"),
        )

    def load_persisted_continuations(self) -> int:
        """Load continuations from DB into memory. Called on daemon startup.

        Returns number of continuations loaded.
        """
        if self._db is None:
            return 0
        try:
            rows = self._db.fetchall("SELECT run_id, config_json FROM pipeline_continuations")
            loaded = 0
            for row in rows:
                run_id = row["run_id"]
                config = json.loads(row["config_json"])
                self._pipeline_continuations[run_id] = config
                # Ensure there's an event registered so notify() works
                if run_id not in self._events:
                    self._events[run_id] = asyncio.Event()
                    self._subscribers[run_id] = []
                loaded += 1
            if loaded > 0:
                logger.info("Loaded %d persisted pipeline continuation(s) from DB", loaded)
            return loaded
        except Exception:
            logger.warning("Failed to load persisted continuations", exc_info=True)
            return 0

    async def notify(
        self,
        completion_id: str,
        result: dict[str, Any],
        message: str = "",
    ) -> None:
        """Signal completion and wake all subscribers.

        Args:
            completion_id: The completion event ID
            result: Result data to store and pass to wake callbacks
            message: Human-readable message for wake notifications
        """
        event = self._events.get(completion_id)
        if event is None:
            logger.debug("notify() called for unregistered ID %s — ignoring", completion_id)
            return

        # Include continuation_prompt in result so wake dispatcher can use it
        # Enrich a copy to avoid mutating the caller's dict
        cp = self._continuation_prompts.get(completion_id)
        if cp and "continuation_prompt" not in result:
            result = {**result, "continuation_prompt": cp}

        self._results[completion_id] = result
        event.set()

        # Wake each subscriber via callback (fail-open per subscriber)
        if self._wake_callback:
            for session_id in self._subscribers.get(completion_id, []):
                try:
                    await self._wake_callback(session_id, message, result)
                except Exception:
                    logger.warning(
                        "Wake callback failed for session %s (completion %s)",
                        session_id,
                        completion_id,
                        exc_info=True,
                    )

        # Fire pipeline continuation if registered
        continuation = self._pipeline_continuations.get(completion_id)
        if continuation and self._pipeline_rerun_callback:
            try:
                await self._pipeline_rerun_callback(continuation, result)
                self._pipeline_continuations.pop(completion_id, None)
                # Remove from DB
                if self._db is not None:
                    try:
                        self._db.execute(
                            "DELETE FROM pipeline_continuations WHERE run_id = ?",
                            (completion_id,),
                        )
                    except Exception:
                        pass
            except Exception:
                logger.error("Pipeline continuation failed for %s", completion_id, exc_info=True)

    async def wait(self, completion_id: str, timeout: float | None = None) -> dict[str, Any]:
        """Block until a completion event fires.

        Args:
            completion_id: The completion event ID to wait on
            timeout: Max seconds to wait (None = wait forever)

        Returns:
            The result dict stored by notify()

        Raises:
            KeyError: If completion_id is not registered
            asyncio.TimeoutError: If timeout expires before notification
        """
        event = self._events.get(completion_id)
        if event is None:
            raise KeyError(f"Completion event {completion_id!r} not registered")

        await asyncio.wait_for(event.wait(), timeout=timeout)
        return self._results[completion_id]

    def get_result(self, completion_id: str) -> dict[str, Any] | None:
        """Get the stored result for a completion event, or None."""
        return self._results.get(completion_id)

    def subscribe(self, completion_id: str, session_id: str) -> None:
        """Add a subscriber to an existing completion event.

        Args:
            completion_id: The completion event ID
            session_id: Session ID to add as subscriber

        Raises:
            KeyError: If completion_id is not registered
        """
        subs = self._subscribers.get(completion_id)
        if subs is None:
            raise KeyError(f"Completion event {completion_id!r} not registered")
        if session_id not in subs:
            subs.append(session_id)

    def get_subscribers(self, completion_id: str) -> list[str]:
        """Get subscriber session IDs for a completion event."""
        return list(self._subscribers.get(completion_id, []))

    def get_continuation_prompt(self, completion_id: str) -> str | None:
        """Get the continuation prompt for a completion event."""
        return self._continuation_prompts.get(completion_id)

    def find_continuation_by_execution(
        self, execution_id: str
    ) -> tuple[str, dict[str, Any]] | None:
        """Find continuation by execution_id. Returns (run_id, config_copy) or None."""
        for run_id, config in self._pipeline_continuations.items():
            if config.get("execution_id") == execution_id:
                return (run_id, dict(config))
        return None

    async def fire_continuation(self, run_id: str) -> bool:
        """Fire and clean up a continuation. Returns True if fired."""
        config = self._pipeline_continuations.pop(run_id, None)
        if config is None or self._pipeline_rerun_callback is None:
            return False
        await self._pipeline_rerun_callback(config, None)
        # DB cleanup
        if self._db:
            try:
                self._db.execute("DELETE FROM pipeline_continuations WHERE run_id = ?", (run_id,))
            except Exception:
                logger.debug("Failed to delete continuation %s from DB", run_id, exc_info=True)
        return True

    def cleanup(self, completion_id: str) -> None:
        """Remove all state for a completion event."""
        self._events.pop(completion_id, None)
        self._results.pop(completion_id, None)
        self._subscribers.pop(completion_id, None)
        self._continuation_prompts.pop(completion_id, None)
        self._pipeline_continuations.pop(completion_id, None)
        if self._db is not None:
            try:
                self._db.execute(
                    "DELETE FROM pipeline_continuations WHERE run_id = ?",
                    (completion_id,),
                )
            except Exception:
                pass
