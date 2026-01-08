"""Autonomous execution infrastructure for Gobby.

This module provides infrastructure for autonomous task execution including:
- Stop signal management for graceful shutdown
- Progress tracking for detecting stagnation
- Stuck detection for breaking out of loops
"""

from gobby.autonomous.progress_tracker import (
    ProgressEvent,
    ProgressSummary,
    ProgressTracker,
    ProgressType,
)
from gobby.autonomous.stop_registry import StopRegistry, StopSignal
from gobby.autonomous.stuck_detector import (
    StuckDetectionResult,
    StuckDetector,
    TaskSelectionEvent,
)

__all__ = [
    "ProgressEvent",
    "ProgressSummary",
    "ProgressTracker",
    "ProgressType",
    "StopRegistry",
    "StopSignal",
    "StuckDetectionResult",
    "StuckDetector",
    "TaskSelectionEvent",
]
