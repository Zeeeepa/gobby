"""
Sessions package for multi-CLI session management.

This package provides:
- SessionManager: Session registration, handoff, and context restoration
- SummaryGenerator: LLM-powered session summaries and title synthesis
- Transcript parsers: CLI-specific transcript parsing (Claude, Codex, Gemini, etc.)
"""

from gobby.sessions.manager import SessionManager
from gobby.sessions.summary import SummaryGenerator

__all__ = ["SessionManager", "SummaryGenerator"]
