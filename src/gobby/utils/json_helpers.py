"""JSON extraction utilities for parsing LLM responses.

This module provides robust JSON extraction from text that may contain
markdown code blocks, preamble text, or other non-JSON content.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def extract_json_from_text(text: str) -> str | None:
    """
    Extract JSON from text, handling markdown code blocks and mixed content.

    Uses json.JSONDecoder.raw_decode() which properly handles all JSON
    edge cases (nested strings, escapes, backticks in strings, etc.)
    rather than brittle regex patterns.

    Args:
        text: Raw text that may contain JSON, possibly wrapped in markdown
              code blocks or with preamble/postamble text.

    Returns:
        Extracted JSON string, or None if no valid JSON found.

    Examples:
        >>> extract_json_from_text('{"key": "value"}')
        '{"key": "value"}'

        >>> extract_json_from_text('Here is the result:\\n```json\\n{"key": "value"}\\n```')
        '{"key": "value"}'

        >>> extract_json_from_text('No JSON here')
        None
    """
    if not text:
        return None

    decoder = json.JSONDecoder()

    # Build list of positions to try, prioritizing code block content
    positions_to_try: list[int] = []

    # Look for ```json marker first (most specific)
    code_block_idx = text.find("```json")
    if code_block_idx != -1:
        brace_pos = text.find("{", code_block_idx + 7)
        if brace_pos != -1:
            positions_to_try.append(brace_pos)

    # Then try plain ``` marker
    if not positions_to_try:
        code_block_idx = text.find("```")
        if code_block_idx != -1:
            brace_pos = text.find("{", code_block_idx + 3)
            if brace_pos != -1:
                positions_to_try.append(brace_pos)

    # Finally try raw JSON (first { in text)
    first_brace = text.find("{")
    if first_brace != -1 and first_brace not in positions_to_try:
        positions_to_try.append(first_brace)

    # Try each position until we find valid JSON
    for pos in positions_to_try:
        try:
            # raw_decode returns (obj, end_idx) where end_idx is absolute position
            _, end_idx = decoder.raw_decode(text, pos)
            return text[pos:end_idx]
        except json.JSONDecodeError:
            continue

    return None


def extract_json_object(text: str) -> dict | None:
    """
    Extract and parse a JSON object from text.

    Convenience wrapper that extracts JSON string and parses it.

    Args:
        text: Raw text that may contain JSON.

    Returns:
        Parsed JSON dict, or None if no valid JSON found.
    """
    json_str = extract_json_from_text(text)
    if json_str is None:
        return None

    try:
        result = json.loads(json_str)
        if isinstance(result, dict):
            return result
        logger.warning(f"Extracted JSON is not an object: {type(result)}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse extracted JSON: {e}")
        return None
