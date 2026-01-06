"""
Configuration package for Gobby daemon.

This package provides Pydantic config models for all daemon settings.
Configs are being decomposed from app.py using Strangler Fig pattern.

Module structure (in progress):
- app.py: Main DaemonConfig and remaining configs
- logging.py: LoggingSettings
- llm_providers.py: LLM provider and AI feature configs
- servers.py: WebSocket and MCP proxy configs
- tasks.py: Task expansion and validation configs
- persistence.py: Memory and skill storage configs
- extensions.py: Hook extension configs (webhooks, plugins)
"""

# Currently all configs are in app.py - will migrate to submodules
from gobby.config.app import (
    CodeExecutionConfig,
    DaemonConfig,
    LLMProviderConfig,
    LLMProvidersConfig,
    LoggingSettings,
    MCPClientProxyConfig,
    PluginItemConfig,
    PluginsConfig,
    RecommendToolsConfig,
    SessionSummaryConfig,
    TitleSynthesisConfig,
    WebhookEndpointConfig,
    WebhooksConfig,
    WebSocketSettings,
    expand_env_vars,
    load_config,
    save_config,
)

# Re-exports for backwards compatibility
# As configs migrate to submodules, imports will change but __all__ stays the same
__all__ = [
    "CodeExecutionConfig",
    "DaemonConfig",
    "LLMProviderConfig",
    "LLMProvidersConfig",
    "LoggingSettings",
    "MCPClientProxyConfig",
    "PluginItemConfig",
    "PluginsConfig",
    "RecommendToolsConfig",
    "SessionSummaryConfig",
    "TitleSynthesisConfig",
    "WebhookEndpointConfig",
    "WebhooksConfig",
    "WebSocketSettings",
    "expand_env_vars",
    "load_config",
    "save_config",
]
