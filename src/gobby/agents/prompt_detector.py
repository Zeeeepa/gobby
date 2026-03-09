"""Detect and auto-dismiss blocking CLI prompts in tmux pane output.

When agents are spawned in clone/worktree directories, CLI tools like
Claude Code show a "Do you trust the files in this folder?" prompt that
blocks execution. This detector identifies those prompts so the lifecycle
monitor can dismiss them by sending the appropriate key sequence.
"""

from __future__ import annotations

import re


class PromptDetector:
    """Detects blocking CLI prompts (e.g. folder trust) in tmux pane output.

    Separate from ``IdleDetector`` — that handles idle-at-prompt vs working.
    This handles interactive prompts that block agent startup entirely.
    """

    TRUST_PROMPT_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"Do you trust the files", re.IGNORECASE),
        re.compile(r"Is this a project you created or one you trust", re.IGNORECASE),
        re.compile(r"Trust.*Folder", re.IGNORECASE),
    )

    # Key sequence to send: Enter to accept "Trust Folder" (option 1).
    # Do NOT use "2\n" (Trust parent Folder) — that would trust the
    # parent directory, granting access to sibling clone directories
    # when multiple dev pipelines run in parallel.
    TRUST_DISMISS_KEYS = "\n"

    def __init__(self) -> None:
        self._dismissed: set[str] = set()

    def detect_trust_prompt(self, pane_output: str) -> bool:
        """Return True if pane output contains a folder trust prompt."""
        for pattern in self.TRUST_PROMPT_PATTERNS:
            if pattern.search(pane_output):
                return True
        return False

    def mark_dismissed(self, run_id: str) -> None:
        """Record that we already dismissed this agent's trust prompt."""
        self._dismissed.add(run_id)

    def was_dismissed(self, run_id: str) -> bool:
        """Check if this agent's trust prompt was already dismissed."""
        return run_id in self._dismissed

    def clear(self, run_id: str) -> None:
        """Remove tracking state for an agent (on cleanup)."""
        self._dismissed.discard(run_id)
