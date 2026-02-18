"""Compatibility patches for claude-agent-sdk.

Monkey-patches parse_message to skip unknown message types (e.g.
rate_limit_event) instead of raising MessageParseError, which would
kill the entire streaming generator.

Import this module before using the SDK streaming APIs.
"""

from __future__ import annotations

import logging
from typing import Any

import claude_agent_sdk._internal.client as _internal_client
import claude_agent_sdk._internal.message_parser as _message_parser
from claude_agent_sdk._errors import MessageParseError

logger = logging.getLogger(__name__)

_original_parse_message = _message_parser.parse_message


def _tolerant_parse_message(data: dict[str, Any]) -> object | None:
    """parse_message wrapper that returns None for unknown message types."""
    try:
        return _original_parse_message(data)
    except MessageParseError:
        msg_type = data.get("type", "?") if isinstance(data, dict) else "?"
        logger.warning("Skipping unrecognized SDK message type: %s", msg_type)
        return None


# Patch both import sites so the tolerant version is used everywhere:
# 1. Module-level import in _internal/client.py (InternalClient.process_query)
_internal_client.parse_message = _tolerant_parse_message  # type: ignore[attr-defined,assignment]
# 2. Module attribute for lazy imports in client.py (ClaudeSDKClient.receive_messages)
_message_parser.parse_message = _tolerant_parse_message  # type: ignore[assignment]
