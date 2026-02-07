"""
Summary module - backward-compatible aliases.

The SummaryFileGenerator class has been removed. Summary file writing is now
handled by the workflow-driven generate_handoff() in summary_actions.py.
"""

from gobby.sessions.transcripts.claude import ClaudeTranscriptParser

# Backward-compatible alias
TranscriptProcessor = ClaudeTranscriptParser
