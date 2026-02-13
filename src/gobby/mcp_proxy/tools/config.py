"""
Internal MCP tools for daemon configuration.

Exposes functionality for:
- get_config(key): Get a config value by dotted key
- get_config_section(prefix): Get an entire section as nested dict
- set_config(key, value): Set a config value by dotted key
- list_config_keys(prefix?): List all config keys
- ensure_defaults(section): Populate missing keys from Pydantic defaults
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.config_store import flatten_config, unflatten_config

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig
    from gobby.storage.config_store import ConfigStore

logger = logging.getLogger(__name__)

__all__ = ["create_config_registry"]


def create_config_registry(
    config: DaemonConfig,
    config_store: ConfigStore,
    config_setter: Callable[[DaemonConfig], None],
) -> InternalToolRegistry:
    """
    Create a config tool registry for reading/writing daemon configuration.

    Args:
        config: Current in-memory DaemonConfig
        config_store: DB-backed config key-value store
        config_setter: Callback to update in-memory config on ServiceContainer

    Returns:
        InternalToolRegistry with config tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-config",
        description="Daemon configuration - get_config, get_config_section, set_config, list_config_keys, ensure_defaults",
    )

    # Mutable reference so tools always read the latest config
    _state = {"config": config}

    def _current_config() -> DaemonConfig:
        return _state["config"]

    def _flat_config() -> dict[str, Any]:
        """Flatten current in-memory config to dotted keys."""
        return flatten_config(_current_config().model_dump(mode="json"))

    @registry.tool(
        name="get_config",
        description="Get a config value by dotted key (e.g. 'skills.hubs.clawdhub.type'). Reads from in-memory config.",
    )
    def get_config(key: str) -> dict[str, Any]:
        """Get a single config value by dotted key."""
        flat = _flat_config()
        if key in flat:
            return {"success": True, "key": key, "value": flat[key]}
        return {"success": False, "error": f"Key '{key}' not found in config"}

    @registry.tool(
        name="get_config_section",
        description="Get an entire config section as nested dict (e.g. 'skills.hubs'). Filters by prefix from in-memory config.",
    )
    def get_config_section(prefix: str) -> dict[str, Any]:
        """Get a config section filtered by dotted-path prefix."""
        flat = _flat_config()
        # Filter keys matching the prefix (exact prefix + '.' boundary)
        section_prefix = prefix + "."
        filtered = {
            k[len(section_prefix):]: v
            for k, v in flat.items()
            if k.startswith(section_prefix)
        }
        # Also include exact match
        if prefix in flat:
            return {"success": True, "prefix": prefix, "value": flat[prefix]}
        if not filtered:
            return {"success": False, "error": f"No keys found under prefix '{prefix}'"}
        nested = unflatten_config(filtered)
        return {"success": True, "prefix": prefix, "section": nested}

    @registry.tool(
        name="set_config",
        description="Set a config value by dotted key. Validates via DaemonConfig, persists to DB, and updates in-memory config.",
    )
    def set_config(key: str, value: Any) -> dict[str, Any]:
        """Set a config value. Validates, persists to DB, updates in-memory."""
        from gobby.config.app import DaemonConfig as DaemonConfigCls
        from gobby.config.app import deep_merge

        try:
            # Build a nested dict from the dotted key
            update_nested = unflatten_config({key: value})

            # Deep-merge into current config dict
            current_dict = _current_config().model_dump(mode="json")
            deep_merge(current_dict, update_nested)

            # Validate by constructing a new DaemonConfig
            new_config = DaemonConfigCls(**current_dict)

            # Persist to DB
            config_store.set(key, value, source="mcp")

            # Update in-memory config
            _state["config"] = new_config
            config_setter(new_config)

            return {"success": True, "key": key, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="list_config_keys",
        description="List all config keys stored in the database, optionally filtered by prefix.",
    )
    def list_config_keys(prefix: str | None = None) -> dict[str, Any]:
        """List config keys from the DB, optionally filtered by prefix."""
        keys = config_store.list_keys(prefix=prefix)
        return {"success": True, "count": len(keys), "keys": keys}

    @registry.tool(
        name="ensure_defaults",
        description="Populate missing config keys from Pydantic defaults for a given section prefix. Useful for bootstrapping config on existing installs.",
    )
    def ensure_defaults(section: str) -> dict[str, Any]:
        """For a section prefix, insert Pydantic default values for any keys not already in DB."""
        from gobby.config.app import DaemonConfig as DaemonConfigCls

        try:
            # Get all defaults from a fresh DaemonConfig
            defaults_flat = flatten_config(DaemonConfigCls().model_dump(mode="json"))

            # Filter to the requested section
            section_prefix = section + "."
            section_defaults = {
                k: v for k, v in defaults_flat.items()
                if k.startswith(section_prefix) or k == section
            }

            if not section_defaults:
                return {
                    "success": False,
                    "error": f"No default keys found for section '{section}'",
                }

            # Find which keys are already in DB
            existing_keys = set(config_store.list_keys(prefix=section))

            # Only insert missing ones
            missing = {k: v for k, v in section_defaults.items() if k not in existing_keys}

            if not missing:
                return {
                    "success": True,
                    "message": f"All {len(section_defaults)} keys already present for '{section}'",
                    "inserted": 0,
                }

            count = config_store.set_many(missing, source="defaults")
            return {
                "success": True,
                "inserted": count,
                "total_section_keys": len(section_defaults),
                "keys_inserted": sorted(missing.keys()),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    return registry
