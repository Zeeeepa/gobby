"""Rule engine re-export shim.

The implementation lives in gobby.workflows.engine. This module preserves
the original import path for backwards compatibility.
"""

from gobby.workflows.engine.core import RuleEngine, _get_tool_identity

__all__ = ["RuleEngine", "_get_tool_identity"]
