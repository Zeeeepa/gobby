"""Rule engine package.

Re-exports RuleEngine and _get_tool_identity for backwards compatibility.
"""

from gobby.workflows.engine.core import RuleEngine, _get_tool_identity

__all__ = ["RuleEngine", "_get_tool_identity"]
