"""CLI detection helpers for install/uninstall commands."""

import os
import shutil
import sys
from pathlib import Path


def _is_claude_code_installed() -> bool:
    """Check if Claude Code CLI is installed."""
    return shutil.which("claude") is not None


def _is_gemini_cli_installed() -> bool:
    """Check if Gemini CLI is installed."""
    return shutil.which("gemini") is not None


def _is_codex_cli_installed() -> bool:
    """Check if OpenAI Codex CLI is installed."""
    return shutil.which("codex") is not None


def _is_cursor_installed() -> bool:
    """Check if Cursor is installed."""
    # Cursor is an IDE, check for common install locations
    if sys.platform == "darwin":
        return Path("/Applications/Cursor.app").exists()
    elif sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", ""), "Programs", "cursor").exists()
    else:
        # Linux - check common locations
        return (Path.home() / ".local" / "share" / "cursor").exists() or shutil.which(
            "cursor"
        ) is not None


def _is_windsurf_installed() -> bool:
    """Check if Windsurf (Codeium) is installed."""
    # Windsurf is an IDE
    if sys.platform == "darwin":
        return Path("/Applications/Windsurf.app").exists()
    elif sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", ""), "Programs", "windsurf").exists()
    else:
        return shutil.which("windsurf") is not None


def _is_copilot_cli_installed() -> bool:
    """Check if GitHub Copilot CLI is installed."""
    # Check for gh copilot extension or standalone CLI
    return shutil.which("gh") is not None or shutil.which("github-copilot-cli") is not None
