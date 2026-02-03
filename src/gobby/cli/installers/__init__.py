"""
CLI installation modules for Gobby hooks.

This package contains per-CLI installation logic extracted from the main install.py
using the strangler fig pattern for incremental migration.
"""

from .antigravity import install_antigravity
from .claude import install_claude, uninstall_claude
from .codex import install_codex_notify, uninstall_codex_notify
from .copilot import install_copilot, uninstall_copilot
from .cursor import install_cursor, uninstall_cursor
from .gemini import install_gemini, uninstall_gemini
from .git_hooks import install_git_hooks
from .shared import (
    install_cli_content,
    install_default_mcp_servers,
    install_shared_content,
)
from .windsurf import install_windsurf, uninstall_windsurf

__all__ = [
    # Shared
    "install_shared_content",
    "install_cli_content",
    "install_default_mcp_servers",
    # Claude
    "install_claude",
    "uninstall_claude",
    # Gemini
    "install_gemini",
    "uninstall_gemini",
    # Codex
    "install_codex_notify",
    "uninstall_codex_notify",
    # Cursor
    "install_cursor",
    "uninstall_cursor",
    # Windsurf
    "install_windsurf",
    "uninstall_windsurf",
    # Copilot
    "install_copilot",
    "uninstall_copilot",
    # Git Hooks
    "install_git_hooks",
    # Antigravity
    "install_antigravity",
]
