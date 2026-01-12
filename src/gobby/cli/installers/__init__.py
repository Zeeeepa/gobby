"""
CLI installation modules for Gobby hooks.

This package contains per-CLI installation logic extracted from the main install.py
using the strangler fig pattern for incremental migration.
"""

from .antigravity import install_antigravity
from .claude import install_claude, uninstall_claude
from .codex import install_codex_notify, uninstall_codex_notify
from .gemini import install_gemini, uninstall_gemini
from .git_hooks import install_git_hooks
from .shared import (
    install_cli_content,
    install_default_mcp_servers,
    install_shared_content,
)

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
    # Git Hooks
    "install_git_hooks",
    # Antigravity
    "install_antigravity",
]
