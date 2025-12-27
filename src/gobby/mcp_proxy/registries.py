"""Internal registry initialization."""

import logging
from typing import Any

from gobby.config.app import DaemonConfig

logger = logging.getLogger("gobby.mcp.registries")


def setup_internal_registries(
    config: DaemonConfig,
    session_manager: Any,
    memory_manager: Any,
    skill_learner: Any,
    # Add other managers as needed
) -> Any:
    """
    Setup internal MCP registries (tasks, messages, etc.).

    Returns:
        InternalRegistryManager containing all registries
    """
    # This mock mimics the extraction of the large setup block from stdio.py
    # Ideally we'd return a proper Manager object.

    class InternalRegistryManager:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, func):
            self.tools[name] = func

        def get_tools(self):
            return self.tools

    registry = InternalRegistryManager()

    # Initialize tasks registry
    # Initialize messages registry
    # Initialize memory registry
    # Initialize skills registry

    logger.info("Internal registries initialized")
    return registry
