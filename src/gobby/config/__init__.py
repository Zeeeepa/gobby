"""
Configuration package for Gobby daemon.

This package provides Pydantic config models for all daemon settings.
Configuration classes are organized into submodules by functionality:

Module structure:
- app.py: Main DaemonConfig aggregator and utility functions
- logging.py: LoggingSettings
- servers.py: WebSocket and MCP proxy configs
- llm_providers.py: LLM provider configurations
- persistence.py: Memory and skill storage configs
- tasks.py: Task expansion, validation, and workflow configs
- extensions.py: Hook extension configs (webhooks, plugins)
- sessions.py: Session lifecycle and tracking configs
- features.py: MCP proxy feature configs (code execution, tool recommendation)
"""

# Core configuration and utilities from app.py
from gobby.config.app import (
    DaemonConfig,
    expand_env_vars,
    load_config,
    save_config,
)

# Extension configs
from gobby.config.extensions import (
    HookExtensionsConfig,
    PluginItemConfig,
    PluginsConfig,
    WebhookEndpointConfig,
    WebhooksConfig,
    WebSocketBroadcastConfig,
)

# Feature configs
from gobby.config.features import (
    CodeExecutionConfig,
    ImportMCPServerConfig,
    MetricsConfig,
    ProjectVerificationConfig,
    RecommendToolsConfig,
    ToolSummarizerConfig,
)

# LLM provider configs
from gobby.config.llm_providers import (
    LLMProviderConfig,
    LLMProvidersConfig,
)

# Logging configs
from gobby.config.logging import LoggingSettings

# Persistence configs
from gobby.config.persistence import (
    MemoryConfig,
    MemorySyncConfig,
)

# Server configs
from gobby.config.servers import (
    MCPClientProxyConfig,
    WebSocketSettings,
)

# Session configs
from gobby.config.sessions import (
    ContextInjectionConfig,
    MessageTrackingConfig,
    SessionLifecycleConfig,
    SessionSummaryConfig,
    TitleSynthesisConfig,
)

# Task configs
from gobby.config.tasks import (
    CompactHandoffConfig,
    GobbyTasksConfig,
    PatternCriteriaConfig,
    TaskExpansionConfig,
    TaskValidationConfig,
    WorkflowConfig,
)

__all__ = [
    # Core
    "DaemonConfig",
    "expand_env_vars",
    "load_config",
    "save_config",
    # Extension configs
    "HookExtensionsConfig",
    "PluginItemConfig",
    "PluginsConfig",
    "WebhookEndpointConfig",
    "WebhooksConfig",
    "WebSocketBroadcastConfig",
    # Feature configs
    "CodeExecutionConfig",
    "ImportMCPServerConfig",
    "MetricsConfig",
    "ProjectVerificationConfig",
    "RecommendToolsConfig",
    "ToolSummarizerConfig",
    # LLM provider configs
    "LLMProviderConfig",
    "LLMProvidersConfig",
    # Logging configs
    "LoggingSettings",
    # Persistence configs
    "MemoryConfig",
    "MemorySyncConfig",
    # Server configs
    "MCPClientProxyConfig",
    "WebSocketSettings",
    # Session configs
    "ContextInjectionConfig",
    "MessageTrackingConfig",
    "SessionLifecycleConfig",
    "SessionSummaryConfig",
    "TitleSynthesisConfig",
    # Task configs
    "CompactHandoffConfig",
    "GobbyTasksConfig",
    "PatternCriteriaConfig",
    "TaskExpansionConfig",
    "TaskValidationConfig",
    "WorkflowConfig",
]
