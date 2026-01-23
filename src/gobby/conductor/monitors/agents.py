"""Agent watcher for detecting stuck agents.

Provides monitoring for:
- Stuck agents: Running longer than threshold without progress
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.agents.registry import RunningAgentRegistry

logger = logging.getLogger(__name__)


@dataclass
class AgentWatcher:
    """Watcher for agent health and status.

    Detects:
    - Stuck agents: Running longer than threshold
    """

    agent_registry: RunningAgentRegistry

    def check(
        self,
        stuck_threshold_minutes: int = 15,
        mode: str | None = None,
    ) -> dict[str, Any]:
        """
        Check for agent health issues.

        Args:
            stuck_threshold_minutes: Minutes before an agent is considered stuck
            mode: Optional filter by agent mode (terminal, headless, etc.)

        Returns:
            Dict with stuck_agents and summary
        """
        stuck_agents = self._find_stuck_agents(
            threshold_minutes=stuck_threshold_minutes,
            mode=mode,
        )

        # Get all running agents for total count
        all_agents = self.agent_registry.list_all()
        if mode:
            all_agents = [a for a in all_agents if a.mode == mode]

        return {
            "stuck_agents": stuck_agents,
            "summary": {
                "stuck_count": len(stuck_agents),
                "total_running": len(all_agents),
                "checked_at": datetime.now(UTC).isoformat(),
            },
        }

    def _find_stuck_agents(
        self,
        threshold_minutes: int = 15,
        mode: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find agents that have been running longer than threshold.

        Args:
            threshold_minutes: Minutes before agent is considered stuck
            mode: Optional filter by agent mode

        Returns:
            List of stuck agent info dicts
        """
        all_agents = self.agent_registry.list_all()

        # Apply mode filter if specified
        if mode:
            all_agents = [a for a in all_agents if a.mode == mode]

        threshold = datetime.now(UTC) - timedelta(minutes=threshold_minutes)
        stuck_agents = []

        for agent in all_agents:
            # Check if agent has been running longer than threshold
            started_at = agent.started_at

            # Timezone policy: All timestamps are expected to be in UTC.
            # If started_at is naive (no tzinfo), log a warning and skip this agent
            # rather than assume UTC, as the source may be using local time.
            if started_at.tzinfo is None:
                logger.warning(
                    f"Agent {agent.run_id} has naive started_at timestamp "
                    f"({started_at}); skipping stuck detection. "
                    "Ensure the agent registry stores UTC timestamps."
                )
                continue

            if started_at < threshold:
                minutes_running = (datetime.now(UTC) - started_at).total_seconds() / 60
                stuck_agents.append(
                    {
                        "run_id": agent.run_id,
                        "session_id": agent.session_id,
                        "mode": agent.mode,
                        "started_at": started_at.isoformat(),
                        "minutes_running": round(minutes_running, 1),
                        "provider": getattr(agent, "provider", "unknown"),
                    }
                )

        return stuck_agents
