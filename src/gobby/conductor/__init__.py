"""Gobby Conductor module.

The Conductor is the orchestration layer for managing complex multi-agent workflows.
This module provides:
- TokenTracker: LiteLLM-based pricing and token tracking
- Budget management and cost monitoring
- Agent coordination and task distribution
"""

from gobby.conductor.pricing import TokenTracker

__all__ = ["TokenTracker"]
