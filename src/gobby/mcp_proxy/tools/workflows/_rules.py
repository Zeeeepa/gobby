"""
MCP tools for rule CRUD operations.

Wraps LocalWorkflowDefinitionManager with workflow_type='rule' filtering.
Provides list, get, toggle, create, and delete operations for standalone rules.
"""

import json
import logging
from typing import Any

from gobby.storage.workflow_definitions import (
    LocalWorkflowDefinitionManager,
    WorkflowDefinitionRow,
)
from gobby.workflows.definitions import RuleDefinitionBody

logger = logging.getLogger(__name__)


def _rule_summary(row: WorkflowDefinitionRow) -> dict[str, Any]:
    """Build a summary dict for a rule row, including parsed definition fields."""
    body = json.loads(row.definition_json)
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "event": body.get("event"),
        "effect": body.get("effect"),
        "group": body.get("group"),
        "when": body.get("when"),
        "enabled": row.enabled,
        "priority": row.priority,
        "source": row.source,
        "tags": row.tags,
    }


def _rule_detail(row: WorkflowDefinitionRow) -> dict[str, Any]:
    """Build a detailed dict for a rule row, including full definition."""
    body = json.loads(row.definition_json)
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "event": body.get("event"),
        "group": body.get("group"),
        "when": body.get("when"),
        "match": body.get("match"),
        "effect": body.get("effect"),
        "enabled": row.enabled,
        "priority": row.priority,
        "source": row.source,
        "tags": row.tags,
    }


def list_rules(
    def_manager: LocalWorkflowDefinitionManager,
    event: str | None = None,
    group: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """
    List rules with optional filters.

    Dispatches to event/group-specific queries when those filters are provided,
    otherwise uses list_all with workflow_type='rule'.

    Args:
        def_manager: Definition storage manager
        event: Filter by event type (e.g. 'before_tool', 'stop')
        group: Filter by group name
        enabled: Filter by enabled status

    Returns:
        Dict with success, rules list, and count
    """
    if event:
        rows = def_manager.list_rules_by_event(event, enabled=enabled)
    elif group:
        rows = def_manager.list_rules_by_group(group, enabled=enabled)
    else:
        rows = def_manager.list_all(workflow_type="rule", enabled=enabled)

    rules = [_rule_summary(r) for r in rows]
    return {"success": True, "rules": rules, "count": len(rules)}


def get_rule(
    def_manager: LocalWorkflowDefinitionManager,
    name: str,
) -> dict[str, Any]:
    """
    Get a rule by name.

    Args:
        def_manager: Definition storage manager
        name: Rule name

    Returns:
        Dict with success and full rule detail, or error if not found
    """
    row = def_manager.get_by_name(name)
    if row is None or row.workflow_type != "rule":
        return {"success": False, "error": f"Rule '{name}' not found"}

    return {"success": True, "rule": _rule_detail(row)}


def toggle_rule(
    def_manager: LocalWorkflowDefinitionManager,
    name: str,
    enabled: bool,
) -> dict[str, Any]:
    """
    Toggle a rule's enabled state.

    Args:
        def_manager: Definition storage manager
        name: Rule name
        enabled: New enabled state

    Returns:
        Dict with success and updated rule, or error if not found
    """
    row = def_manager.get_by_name(name)
    if row is None or row.workflow_type != "rule":
        return {"success": False, "error": f"Rule '{name}' not found"}

    updated = def_manager.update(row.id, enabled=enabled)
    logger.info("Toggled rule '%s' enabled=%s", name, enabled)

    return {"success": True, "rule": _rule_detail(updated)}


def create_rule(
    def_manager: LocalWorkflowDefinitionManager,
    name: str,
    definition: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a new rule.

    Validates the definition with RuleDefinitionBody before inserting.

    Args:
        def_manager: Definition storage manager
        name: Rule name (must be unique)
        definition: Rule definition dict (event, effect, optional when/group/match)

    Returns:
        Dict with success and created rule, or error
    """
    # Validate with Pydantic
    try:
        RuleDefinitionBody.model_validate(definition)
    except Exception as e:
        return {"success": False, "error": f"Validation failed: {e}"}

    # Check for duplicate name
    existing = def_manager.get_by_name(name)
    if existing is not None:
        return {"success": False, "error": f"Rule '{name}' already exists"}

    row = def_manager.create(
        name=name,
        definition_json=json.dumps(definition),
        workflow_type="rule",
        enabled=True,
        source="custom",
    )
    logger.info("Created rule '%s' (id=%s)", name, row.id)

    return {"success": True, "rule": _rule_detail(row)}


def delete_rule(
    def_manager: LocalWorkflowDefinitionManager,
    name: str,
    force: bool = False,
) -> dict[str, Any]:
    """
    Delete a rule by name (soft-delete).

    Bundled rules are protected unless force=True.

    Args:
        def_manager: Definition storage manager
        name: Rule name
        force: Override bundled protection

    Returns:
        Dict with success, or error if not found/protected
    """
    row = def_manager.get_by_name(name)
    if row is None or row.workflow_type != "rule":
        return {"success": False, "error": f"Rule '{name}' not found"}

    if row.source == "bundled" and not force:
        return {
            "success": False,
            "error": (
                f"Rule '{name}' is bundled and will be re-created on restart. "
                "Use force=True to delete anyway."
            ),
        }

    deleted = def_manager.delete(row.id)
    if not deleted:
        return {"success": False, "error": f"Failed to delete rule '{name}'"}

    logger.info("Deleted rule '%s' (id=%s)", name, row.id)
    return {"success": True, "deleted": {"id": row.id, "name": row.name}}
