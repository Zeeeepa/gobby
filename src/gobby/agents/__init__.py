"""
Gobby Agents Module.

This module provides the subagent spawning system, enabling agents to spawn
independent subagents that can use any LLM provider and follow workflows.

Components:
- AgentRunner: Orchestrates agent execution with workflow integration
- Session management: Creates and links child sessions to parents
- Terminal spawning: Launches agents in separate terminal windows

Usage:
    from gobby.agents import AgentRunner

    runner = AgentRunner(config)
    result = await runner.start_agent(
        workflow="code-review.yaml",
        prompt="Review the auth changes",
        provider="claude",
    )
"""

# Exports will be added as components are implemented
__all__: list[str] = []
