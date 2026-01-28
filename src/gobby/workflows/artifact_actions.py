"""Artifact capture and read workflow actions.

Extracted from actions.py as part of strangler fig decomposition.
These functions handle file artifact capture and reading.
"""

import asyncio
import glob
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def capture_artifact(
    state: Any,
    pattern: str | None = None,
    save_as: str | None = None,
) -> dict[str, Any] | None:
    """Capture an artifact (file) and store its path in state.

    Args:
        state: WorkflowState object with artifacts dict
        pattern: Glob pattern to match files
        save_as: Name to store the artifact under

    Returns:
        Dict with captured filepath, or None if no match
    """
    if not pattern:
        return None

    # Use iglob generator to avoid building entire list on deep trees
    # Select the lexicographically smallest match for determinism
    first_match: str | None = None
    for match in glob.iglob(pattern, recursive=True):
        if first_match is None or match < first_match:
            first_match = match

    if first_match is None:
        return None

    filepath = os.path.abspath(first_match)

    if save_as:
        if not state.artifacts:
            state.artifacts = {}
        state.artifacts[save_as] = filepath

    return {"captured": filepath}


def read_artifact(
    state: Any,
    pattern: str | None = None,
    variable_name: str | None = None,
) -> dict[str, Any] | None:
    """Read an artifact's content into a workflow variable.

    Args:
        state: WorkflowState object with artifacts and variables dicts
        pattern: Glob pattern or artifact key to read
        variable_name: Variable name to store content in

    Returns:
        Dict with read_artifact, variable, and length, or None on error
    """
    if not pattern:
        return None

    if not variable_name:
        logger.warning("read_artifact: 'as' argument missing")
        return None

    # Check if pattern matches an existing artifact key first
    filepath = None
    if state.artifacts:
        filepath = state.artifacts.get(pattern)

    if not filepath:
        # Try as glob pattern - use sorted() for deterministic selection
        matches = sorted(glob.glob(pattern, recursive=True))
        if matches:
            filepath = os.path.abspath(matches[0])

    if not filepath or not os.path.exists(filepath):
        logger.warning(f"read_artifact: File not found for pattern '{pattern}'")
        return None

    try:
        # Use explicit encoding and error handling for cross-platform safety
        with open(filepath, encoding="utf-8", errors="replace") as f:
            content = f.read()

        if not state.variables:
            state.variables = {}

        state.variables[variable_name] = content
        return {"read_artifact": True, "variable": variable_name, "length": len(content)}

    except Exception as e:
        logger.error(f"read_artifact: Failed to read {filepath}: {e}")
        return None


# --- ActionHandler-compatible wrappers ---
# These match the ActionHandler protocol: (context: ActionContext, **kwargs) -> dict | None

if __name__ != "__main__":
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from gobby.workflows.actions import ActionContext


async def handle_capture_artifact(context: "ActionContext", **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for capture_artifact."""
    return await asyncio.to_thread(
        capture_artifact,
        state=context.state,
        pattern=kwargs.get("pattern"),
        save_as=kwargs.get("as"),
    )


async def handle_read_artifact(context: "ActionContext", **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for read_artifact."""
    return await asyncio.to_thread(
        read_artifact,
        state=context.state,
        pattern=kwargs.get("pattern"),
        variable_name=kwargs.get("as"),
    )
