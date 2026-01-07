"""
Terminal spawner configuration.

Loads terminal preferences and customizations from ~/.gobby/tty_config.yaml,
allowing users to reorder preferences, customize app paths, and add options.
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class TerminalConfig(BaseModel):
    """Configuration for a specific terminal emulator."""

    app_path: str | None = Field(
        default=None,
        description="macOS app bundle path (e.g., /Applications/Ghostty.app)",
    )
    command: str | None = Field(
        default=None,
        description="CLI command name for shutil.which() (e.g., ghostty, kitty)",
    )
    options: list[str] = Field(
        default_factory=list,
        description="Extra command-line options to pass to the terminal",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this terminal is enabled for use",
    )


class PlatformPreferences(BaseModel):
    """Terminal preference order by platform."""

    macos: list[str] = Field(
        default_factory=lambda: [
            "ghostty",
            "iterm",
            "kitty",
            "alacritty",
            "terminal.app",
            "tmux",  # Multiplexer (last resort)
        ],
        description="Terminal preference order for macOS",
    )
    linux: list[str] = Field(
        default_factory=lambda: [
            "ghostty",
            "kitty",
            "gnome-terminal",
            "konsole",
            "alacritty",
            "tmux",  # Multiplexer (last resort)
        ],
        description="Terminal preference order for Linux",
    )
    windows: list[str] = Field(
        default_factory=lambda: [
            "windows-terminal",
            "powershell",
            "alacritty",
            "wsl",
            "cmd",
        ],
        description="Terminal preference order for Windows",
    )


# Default terminal configurations (can be overridden in config file)
DEFAULT_TERMINAL_CONFIGS: dict[str, dict[str, Any]] = {
    "ghostty": {
        "app_path": "/Applications/Ghostty.app",
        "command": "ghostty",
    },
    "iterm": {
        "app_path": "/Applications/iTerm.app",
    },
    "terminal.app": {
        "app_path": "/System/Applications/Utilities/Terminal.app",
    },
    "kitty": {
        "app_path": "/Applications/kitty.app",
        "command": "kitty",
        "options": ["-o", "confirm_os_window_close=0"],
    },
    "alacritty": {
        "command": "alacritty",
    },
    "gnome-terminal": {
        "command": "gnome-terminal",
    },
    "konsole": {
        "command": "konsole",
    },
    "windows-terminal": {
        "command": "wt",
    },
    "cmd": {
        # Built-in on Windows, no command needed
    },
    "powershell": {
        # pwsh (PowerShell Core) is preferred, falls back to powershell (Windows PowerShell)
        "command": "pwsh",
    },
    "wsl": {
        "command": "wsl",
        # Options can specify distribution: ["-d", "Ubuntu"]
    },
    "tmux": {
        "command": "tmux",
        # Options can set socket name, config file, etc.
    },
}


class TTYConfig(BaseModel):
    """Terminal spawner configuration."""

    preferences: PlatformPreferences = Field(
        default_factory=PlatformPreferences,
        description="Terminal preference order by platform",
    )
    terminals: dict[str, TerminalConfig] = Field(
        default_factory=dict,
        description="Terminal-specific configurations (merged with defaults)",
    )

    def get_terminal_config(self, terminal_name: str) -> TerminalConfig:
        """
        Get configuration for a specific terminal.

        Merges user config with defaults, with user config taking precedence.

        Args:
            terminal_name: Name of the terminal (e.g., 'ghostty', 'iterm')

        Returns:
            TerminalConfig with merged settings
        """
        # Start with defaults
        defaults = DEFAULT_TERMINAL_CONFIGS.get(terminal_name, {})
        config_dict = dict(defaults)

        # Merge user config if present
        if terminal_name in self.terminals:
            user_config = self.terminals[terminal_name].model_dump(exclude_none=True)
            # For options, extend rather than replace
            if "options" in user_config and "options" in config_dict:
                config_dict["options"] = config_dict["options"] + user_config["options"]
                del user_config["options"]
            config_dict.update(user_config)

        return TerminalConfig(**config_dict)

    def get_preferences(self) -> list[str]:
        """
        Get terminal preference order for current platform.

        Returns:
            List of terminal names in preference order
        """
        system = platform.system()
        if system == "Darwin":
            return self.preferences.macos
        elif system == "Windows":
            return self.preferences.windows
        else:
            return self.preferences.linux


def load_tty_config(config_path: str | Path | None = None) -> TTYConfig:
    """
    Load terminal configuration from YAML file.

    Args:
        config_path: Path to config file (default: ~/.gobby/tty_config.yaml)

    Returns:
        TTYConfig instance (with defaults if file doesn't exist)
    """
    if config_path is None:
        config_path = Path.home() / ".gobby" / "tty_config.yaml"
    else:
        config_path = Path(config_path).expanduser()

    if not config_path.exists():
        return TTYConfig()

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
        return TTYConfig(**(data or {}))
    except Exception:
        # Fall back to defaults on any error
        return TTYConfig()


def generate_default_tty_config(config_path: str | Path | None = None) -> Path:
    """
    Generate default terminal configuration file.

    Args:
        config_path: Path to config file (default: ~/.gobby/tty_config.yaml)

    Returns:
        Path to the created config file
    """
    if config_path is None:
        config_path = Path.home() / ".gobby" / "tty_config.yaml"
    else:
        config_path = Path(config_path).expanduser()

    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate example config with comments
    config_content = """# Terminal spawner configuration for Gobby
# See: https://github.com/GobbyAI/gobby/docs/terminal-config.md

# Terminal preference order by platform (first available is used)
preferences:
  macos:
    - ghostty
    - iterm
    - kitty
    - alacritty
    - terminal.app
    - tmux
  linux:
    - ghostty
    - kitty
    - gnome-terminal
    - konsole
    - alacritty
    - tmux
  windows:
    - windows-terminal
    - powershell
    - alacritty
    - wsl
    - cmd

# Terminal-specific configurations (overrides defaults)
# Uncomment and modify as needed:
#
# terminals:
#   ghostty:
#     app_path: /Applications/Ghostty.app  # macOS app bundle path
#     command: ghostty                      # CLI command (Linux/other)
#     enabled: true                         # Set to false to skip this terminal
#
#   kitty:
#     app_path: /Applications/kitty.app
#     command: kitty
#     options:                              # Extra command-line options
#       - "-o"
#       - "confirm_os_window_close=0"
#
#   iterm:
#     app_path: /Applications/iTerm.app
#
#   powershell:
#     command: pwsh                         # Use 'powershell' for Windows PowerShell
#
#   wsl:
#     command: wsl
#     options:                              # Specify WSL distribution
#       - "-d"
#       - "Ubuntu"
#
#   tmux:
#     command: tmux
#     options:                              # Use specific socket/config
#       - "-L"
#       - "gobby"
"""

    with open(config_path, "w") as f:
        f.write(config_content)

    # Set restrictive permissions
    config_path.chmod(0o600)

    return config_path


# Global cached config instance
_config: TTYConfig | None = None


def get_tty_config() -> TTYConfig:
    """
    Get the terminal configuration (cached).

    Returns:
        TTYConfig instance
    """
    global _config
    if _config is None:
        _config = load_tty_config()
    return _config


def reload_tty_config() -> TTYConfig:
    """
    Reload terminal configuration from disk.

    Returns:
        New TTYConfig instance
    """
    global _config
    _config = load_tty_config()
    return _config
