"""Autonomous execution infrastructure for Gobby.

This module provides infrastructure for autonomous task execution including:
- Stop signal management for graceful shutdown
- Progress tracking for detecting stagnation
- Stuck detection for breaking out of loops
"""

from gobby.autonomous.stop_registry import StopRegistry, StopSignal

__all__ = ["StopRegistry", "StopSignal"]
