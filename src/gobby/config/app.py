"""
Configuration management for Gobby daemon.

Provides YAML-based configuration with CLI overrides,
configuration hierarchy (CLI > YAML > Defaults), and validation.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from gobby.compression import CompressionConfig
from gobby.config.extensions import (
    HookExtensionsConfig,
    PluginItemConfig,
    PluginsConfig,
    WebhookEndpointConfig,
    WebhooksConfig,
    WebSocketBroadcastConfig,
)
from gobby.config.features import (
    ImportMCPServerConfig,
    MetricsConfig,
    ProjectVerificationConfig,
    RecommendToolsConfig,
    ToolSummarizerConfig,
)

# Re-export from extracted modules (Strangler Fig pattern for backwards compatibility)
from gobby.config.llm_providers import LLMProviderConfig, LLMProvidersConfig
from gobby.config.logging import LoggingSettings
from gobby.config.persistence import (
    MemoryConfig,
    MemorySyncConfig,
)
from gobby.config.servers import MCPClientProxyConfig, WebSocketSettings
from gobby.config.sessions import (
    ArtifactHandoffConfig,
    ContextInjectionConfig,
    MessageTrackingConfig,
    SessionLifecycleConfig,
    SessionSummaryConfig,
    TitleSynthesisConfig,
)
from gobby.config.tasks import (
    CompactHandoffConfig,
    GobbyTasksConfig,
    PatternCriteriaConfig,
    TaskExpansionConfig,
    TaskValidationConfig,
    WorkflowConfig,
)

# Explicit exports for mypy (re-exported symbols from submodules)
__all__ = [
    # From gobby.compression
    "CompressionConfig",
    # From gobby.config.extensions
    "HookExtensionsConfig",
    "PluginItemConfig",
    "PluginsConfig",
    "WebhookEndpointConfig",
    "WebhooksConfig",
    "WebSocketBroadcastConfig",
    # From gobby.config.features
    "ImportMCPServerConfig",
    "MetricsConfig",
    "ProjectVerificationConfig",
    "RecommendToolsConfig",
    "ToolSummarizerConfig",
    # From gobby.config.llm_providers
    "LLMProviderConfig",
    "LLMProvidersConfig",
    # From gobby.config.logging
    "LoggingSettings",
    # From gobby.config.persistence
    "MemoryConfig",
    "MemorySyncConfig",
    # From gobby.config.servers
    "MCPClientProxyConfig",
    "WebSocketSettings",
    # From gobby.config.sessions
    "ArtifactHandoffConfig",
    "ContextInjectionConfig",
    "MessageTrackingConfig",
    "SessionLifecycleConfig",
    "SessionSummaryConfig",
    "TitleSynthesisConfig",
    # From gobby.config.tasks
    "CompactHandoffConfig",
    "GobbyTasksConfig",
    "PatternCriteriaConfig",
    "TaskExpansionConfig",
    "TaskValidationConfig",
    "WorkflowConfig",
    # Local definitions
    "DaemonConfig",
    "expand_env_vars",
    "load_yaml",
    "apply_cli_overrides",
    "generate_default_config",
    "load_config",
    "save_config",
]

# Pattern for environment variable substitution:
# ${VAR} - simple substitution
# ${VAR:-default} - with default value if VAR is unset or empty
ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def expand_env_vars(content: str) -> str:
    """
    Expand environment variables in configuration content.

    Supports two syntaxes:
    - ${VAR} - replaced with the value of VAR, or left unchanged if unset
    - ${VAR:-default} - replaced with VAR's value, or 'default' if unset/empty

    Args:
        content: Configuration file content as string

    Returns:
        Content with environment variables expanded
    """

    def replace_match(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default_value = match.group(2)  # None if no default specified

        env_value = os.environ.get(var_name)

        if env_value is not None and env_value != "":
            return env_value
        elif default_value is not None:
            return default_value
        else:
            # Leave unchanged if no value and no default
            return match.group(0)

    return ENV_VAR_PATTERN.sub(replace_match, content)


# WebSocketSettings moved to gobby.config.servers (re-exported above)
# LoggingSettings moved to gobby.config.logging (re-exported above)
# CompactHandoffConfig moved to gobby.config.tasks (re-exported above)

# ContextInjectionConfig, SessionSummaryConfig, TitleSynthesisConfig,
# MessageTrackingConfig, SessionLifecycleConfig
# moved to gobby.config.sessions (re-exported above)

# ToolSummarizerConfig, RecommendToolsConfig, ImportMCPServerConfig,
# MetricsConfig, ProjectVerificationConfig
# moved to gobby.config.features (re-exported above)

# WebSocketBroadcastConfig, WebhookEndpointConfig, WebhooksConfig,
# PluginItemConfig, PluginsConfig, HookExtensionsConfig
# moved to gobby.config.extensions (re-exported above)

# PatternCriteriaConfig, TaskExpansionConfig, TaskValidationConfig, WorkflowConfig,
# GobbyTasksConfig, CompactHandoffConfig
# moved to gobby.config.tasks (re-exported above)

# MCPClientProxyConfig moved to gobby.config.servers (re-exported above)
# LLMProviderConfig and LLMProvidersConfig moved to gobby.config.llm_providers (re-exported above)
# MemoryConfig, MemorySyncConfig
# moved to gobby.config.persistence (re-exported above)


class DaemonConfig(BaseModel):
    """
    Main configuration for Gobby daemon.

    Configuration is loaded with the following priority:
    1. CLI arguments (highest)
    2. YAML file (~/.gobby/config.yaml)
    3. Defaults (lowest)

    Note: machine_id is stored separately in ~/.gobby/machine_id
    """

    model_config = {"populate_by_name": True}

    # Daemon settings
    daemon_port: int = Field(
        default=8765,
        description="Port for daemon to listen on",
    )
    daemon_health_check_interval: float = Field(
        default=10.0,
        description="Daemon health check interval in seconds",
    )

    # Local storage
    database_path: str = Field(
        default="~/.gobby/gobby.db",
        description="Path to hub database for cross-project queries. Project-local databases are always at .gobby/gobby.db",
    )

    # Sub-configs
    websocket: WebSocketSettings = Field(
        default_factory=WebSocketSettings,
        description="WebSocket server configuration",
    )
    logging: LoggingSettings = Field(
        default_factory=LoggingSettings,
        description="Logging configuration",
    )
    session_summary: SessionSummaryConfig = Field(
        default_factory=SessionSummaryConfig,
        description="Session summary generation configuration",
    )
    compact_handoff: CompactHandoffConfig = Field(
        default_factory=CompactHandoffConfig,
        description="Compact handoff context configuration",
    )
    context_injection: ContextInjectionConfig = Field(
        default_factory=ContextInjectionConfig,
        description="Context injection configuration for subagent spawning",
    )
    artifact_handoff: ArtifactHandoffConfig = Field(
        default_factory=ArtifactHandoffConfig,
        description="Artifact inclusion in handoff context configuration",
    )
    mcp_client_proxy: MCPClientProxyConfig = Field(
        default_factory=MCPClientProxyConfig,
        description="MCP client proxy configuration",
    )
    gobby_tasks: GobbyTasksConfig = Field(
        default_factory=GobbyTasksConfig,
        alias="gobby-tasks",
        serialization_alias="gobby-tasks",
        description="gobby-tasks internal MCP server configuration",
    )

    # Multi-provider LLM configuration
    llm_providers: LLMProvidersConfig = Field(
        default_factory=LLMProvidersConfig,
        description="Multi-provider LLM configuration",
    )
    title_synthesis: TitleSynthesisConfig = Field(
        default_factory=TitleSynthesisConfig,
        description="Title synthesis configuration",
    )
    recommend_tools: RecommendToolsConfig = Field(
        default_factory=RecommendToolsConfig,
        description="Tool recommendation configuration",
    )
    tool_summarizer: ToolSummarizerConfig = Field(
        default_factory=ToolSummarizerConfig,
        description="Tool description summarization configuration",
    )
    import_mcp_server: ImportMCPServerConfig = Field(
        default_factory=ImportMCPServerConfig,
        description="MCP server import configuration",
    )
    hook_extensions: HookExtensionsConfig = Field(
        default_factory=HookExtensionsConfig,
        description="Hook extensions configuration",
    )
    workflow: WorkflowConfig = Field(
        default_factory=WorkflowConfig,
        description="Workflow engine configuration",
    )
    memory: MemoryConfig = Field(
        default_factory=MemoryConfig,
        description="Memory system configuration",
    )
    memory_sync: MemorySyncConfig = Field(
        default_factory=MemorySyncConfig,
        description="Memory synchronization configuration",
    )
    message_tracking: MessageTrackingConfig = Field(
        default_factory=MessageTrackingConfig,
        description="Session message tracking configuration",
    )
    session_lifecycle: SessionLifecycleConfig = Field(
        default_factory=SessionLifecycleConfig,
        description="Session lifecycle management configuration",
    )
    metrics: MetricsConfig = Field(
        default_factory=MetricsConfig,
        description="Metrics and status endpoint configuration",
    )
    verification_defaults: ProjectVerificationConfig = Field(
        default_factory=ProjectVerificationConfig,
        description="Default verification commands for projects without auto-detected config",
    )
    compression: CompressionConfig = Field(
        default_factory=CompressionConfig,
        description="LLMLingua-2 prompt compression configuration",
    )

    def get_recommend_tools_config(self) -> RecommendToolsConfig:
        """Get recommend_tools configuration."""
        return self.recommend_tools

    def get_tool_summarizer_config(self) -> ToolSummarizerConfig:
        """Get tool_summarizer configuration."""
        return self.tool_summarizer

    def get_import_mcp_server_config(self) -> ImportMCPServerConfig:
        """Get import_mcp_server configuration."""
        return self.import_mcp_server

    def get_mcp_client_proxy_config(self) -> MCPClientProxyConfig:
        """Get MCP client proxy configuration."""
        return self.mcp_client_proxy

    def get_memory_config(self) -> MemoryConfig:
        """Get memory configuration."""
        return self.memory

    def get_memory_sync_config(self) -> MemorySyncConfig:
        """Get memory sync configuration."""
        return self.memory_sync

    def get_gobby_tasks_config(self) -> GobbyTasksConfig:
        """Get gobby-tasks configuration."""
        return self.gobby_tasks

    def get_metrics_config(self) -> MetricsConfig:
        """Get metrics configuration."""
        return self.metrics

    def get_compression_config(self) -> CompressionConfig:
        """Get compression configuration."""
        return self.compression

    def get_verification_defaults(self) -> ProjectVerificationConfig:
        """Get default verification commands configuration."""
        return self.verification_defaults

    @field_validator("daemon_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port number is in valid range."""
        if not (1024 <= v <= 65535):
            raise ValueError("Port must be between 1024 and 65535")
        return v

    @field_validator("daemon_health_check_interval")
    @classmethod
    def validate_health_check_interval(cls, v: float) -> float:
        """Validate health check interval is in valid range."""
        if not (1.0 <= v <= 300.0):
            raise ValueError("daemon_health_check_interval must be between 1.0 and 300.0 seconds")
        return v


def load_yaml(config_file: str) -> dict[str, Any]:
    """
    Load YAML or JSON configuration file.

    Args:
        config_file: Path to YAML or JSON configuration file

    Returns:
        Dictionary with parsed YAML/JSON content

    Raises:
        ValueError: If YAML/JSON is invalid or file format is wrong
    """
    config_path = Path(config_file).expanduser()

    if not config_path.exists():
        return {}

    # Validate file extension matches format
    file_ext = config_path.suffix.lower()
    if file_ext not in [".yaml", ".yml", ".json"]:
        raise ValueError(
            f"Config file must have .yaml, .yml, or .json extension, got: {file_ext}\n"
            f"File: {config_path}"
        )

    import json

    try:
        with open(config_path) as f:
            content = f.read()

        # Expand environment variables before parsing
        content = expand_env_vars(content)

        # Handle JSON files
        if file_ext == ".json":
            return json.loads(content) if content.strip() else {}

        # Handle YAML files
        data = yaml.safe_load(content)
        return data if data is not None else {}

    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in config file: {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file: {e}") from e


def apply_cli_overrides(
    config_dict: dict[str, Any],
    cli_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Apply CLI argument overrides to config dictionary.

    Args:
        config_dict: Configuration dictionary
        cli_overrides: Dictionary of CLI overrides

    Returns:
        Configuration dictionary with CLI overrides applied
    """
    if cli_overrides is None:
        return config_dict

    # Apply overrides at top level
    for key, value in cli_overrides.items():
        if "." in key:
            # Handle nested keys like "logging.level"
            parts = key.split(".")
            current = config_dict
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        else:
            config_dict[key] = value

    return config_dict


def generate_default_config(config_file: str) -> None:
    """
    Generate default configuration file from Pydantic model defaults.

    Args:
        config_file: Path where to create the config file
    """
    config_path = Path(config_file).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Use Pydantic model defaults as source of truth
    default_config = DaemonConfig().model_dump(mode="python", exclude_none=True)

    with open(config_path, "w") as f:
        yaml.safe_dump(default_config, f, default_flow_style=False, sort_keys=False)

    # Set restrictive permissions (owner read/write only)
    config_path.chmod(0o600)


def load_config(
    config_file: str | None = None,
    cli_overrides: dict[str, Any] | None = None,
    create_default: bool = False,
) -> DaemonConfig:
    """
    Load configuration with hierarchy: CLI > YAML > Defaults.

    Args:
        config_file: Path to YAML config file (default: ~/.gobby/config.yaml)
        cli_overrides: Dictionary of CLI argument overrides
        create_default: Create default config file if it doesn't exist

    Returns:
        Validated DaemonConfig instance

    Raises:
        ValueError: If configuration is invalid or required fields are missing
    """
    if config_file is None:
        config_file = "~/.gobby/config.yaml"

    config_path = Path(config_file).expanduser()

    # Create default config if requested and file doesn't exist
    if create_default and not config_path.exists():
        generate_default_config(config_file)

    # Load YAML configuration
    config_dict = load_yaml(config_file)

    # Apply CLI argument overrides
    config_dict = apply_cli_overrides(config_dict, cli_overrides)

    # Validate and create config object
    try:
        config = DaemonConfig(**config_dict)
        return config
    except Exception as e:
        raise ValueError(
            f"Configuration validation failed: {e}\n"
            f"Please check your configuration file at {config_file}"
        ) from e


def save_config(config: DaemonConfig, config_file: str | None = None) -> None:
    """
    Save configuration to YAML file.

    Args:
        config: DaemonConfig instance to save
        config_file: Path to YAML config file (default: ~/.gobby/config.yaml)

    Raises:
        OSError: If file operations fail
    """
    if config_file is None:
        config_file = "~/.gobby/config.yaml"

    config_path = Path(config_file).expanduser()

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert config to dict, excluding None values to keep file clean
    config_dict = config.model_dump(mode="python", exclude_none=True)

    # Write to YAML file
    with open(config_path, "w") as f:
        yaml.safe_dump(config_dict, f, default_flow_style=False, sort_keys=False)

    # Set restrictive permissions (owner read/write only)
    config_path.chmod(0o600)
