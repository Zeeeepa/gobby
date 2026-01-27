"""
Configuration package for Gobby daemon.

This package provides Pydantic config models for all daemon settings.
Configuration classes are organized into submodules by functionality:

Module structure:
- app.py: Main DaemonConfig aggregator and utility functions
- logging.py: LoggingSettings
- servers.py: WebSocket and MCP proxy configs
- llm_providers.py: LLM provider configurations
- persistence.py: Memory storage configs
- tasks.py: Task expansion, validation, and workflow configs
- extensions.py: Hook extension configs (webhooks, plugins)
- sessions.py: Session lifecycle and tracking configs
- features.py: MCP proxy feature configs (code execution, tool recommendation)

Import from submodules directly for specific configs:
    from gobby.config.tasks import TaskValidationConfig
    from gobby.config.extensions import WebhooksConfig

Import from this package for app-level items:
    from gobby.config import DaemonConfig, load_config
"""

# Core configuration and utilities from app.py
from gobby.config.app import (
    DaemonConfig,
    expand_env_vars,
    generate_default_config,
    load_config,
    load_yaml,
    save_config,
)

__all__ = [
    # Core app-level exports only
    "DaemonConfig",
    "expand_env_vars",
    "generate_default_config",
    "load_config",
    "load_yaml",
    "save_config",
]
