"""
Gobby Agents Module.

This module provides the subagent spawning system, enabling agents to spawn
independent subagents that can use any LLM provider and follow workflows.

Components:
- AgentRunner: Orchestrates agent execution with workflow integration
- Session management: Creates and links child sessions to parents
- Terminal spawning: Launches agents in separate terminal windows

Usage:
    from gobby.agents import AgentRunner, AgentConfig

    runner = AgentRunner(db, session_storage, executors)
    result = await runner.run(AgentConfig(
        prompt="Review the auth changes",
        parent_session_id="sess-123",
        project_id="proj-abc",
        machine_id="machine-1",
        source="claude",
        provider="claude",
    ))
"""

from gobby.agents.registry import RunningAgent
from gobby.agents.runner import AgentConfig, AgentRunContext, AgentRunner
from gobby.agents.session import ChildSessionConfig, ChildSessionManager

__all__ = [
    "AgentConfig",
    "AgentRunContext",
    "AgentRunner",
    "RunningAgent",
    "ChildSessionConfig",
    "ChildSessionManager",
]
