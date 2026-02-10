"""
Gemini transcript parser.

Parses both JSONL transcript streams and native JSON session files from Gemini CLI.

JSONL format: Streamed events (init, message, tool_use, tool_result, result).
JSON format: Single session file at ~/.gemini/tmp/{SHA256(cwd)}/chats/session-*.json
  with {sessionId, messages: [{id, timestamp, type, content, toolCalls}]}.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from gobby.sessions.transcripts.base import ParsedMessage, TokenUsage

logger = logging.getLogger(__name__)


class GeminiTranscriptParser:
    """
    Parses transcript files from Gemini.

    Supports two formats:
    - JSONL: Streamed events (parse_line / parse_lines)
    - JSON: Native session file (parse_session_json)
    """

    def __init__(self, logger_instance: logging.Logger | None = None):
        """
        Initialize GeminiTranscriptParser.

        Args:
            logger_instance: Optional logger instance.
        """
        self.logger = logger_instance or logger

    def extract_last_messages(
        self, turns: list[dict[str, Any]], num_pairs: int = 2
    ) -> list[dict[str, Any]]:
        """
        Extract last N user<>agent message pairs.

        Handles Gemini CLI's type-based event format.
        """
        messages: list[dict[str, str]] = []
        for turn in reversed(turns):
            # Handle Gemini CLI's type-based format
            event_type = turn.get("type")
            role: str | None = None
            content: str | Any = None

            if event_type == "message":
                role = turn.get("role")
                content = turn.get("content")
            elif event_type in ("init", "result"):
                # Skip non-message events
                continue
            elif event_type == "tool_use":
                # Include tool calls as assistant messages
                role = "assistant"
                tool_name = turn.get("tool_name") or turn.get("function_name", "unknown")
                content = f"[Tool call: {tool_name}]"
            elif event_type == "tool_result":
                # Skip tool results for message extraction
                continue
            else:
                # Unknown event type, skip
                continue

            if role in ["user", "model", "assistant"]:
                norm_role = "assistant" if role == "model" else role

                # Handle complex content types if necessary
                if isinstance(content, list):
                    content = " ".join(str(part) for part in content)

                messages.insert(0, {"role": norm_role, "content": str(content or "")})
                if len(messages) >= num_pairs * 2:
                    break
        return messages

    def extract_turns_since_clear(
        self, turns: list[dict[str, Any]], max_turns: int = 50
    ) -> list[dict[str, Any]]:
        """
        Extract turns since the most recent session boundary.
        For Gemini, we might look for specific clear events or just return the tail.
        """
        # Placeholder: just return last N turns for now until we know the clear signal
        return turns[-max_turns:] if len(turns) > max_turns else turns

    def is_session_boundary(self, turn: dict[str, Any]) -> bool:
        """
        Check if a turn is a session boundary.
        """
        # Placeholder for Gemini specific boundary
        return False

    def parse_line(self, line: str, index: int) -> ParsedMessage | None:
        """
        Parse a single line from the transcript JSONL.

        Gemini CLI uses type-based events in JSONL format:
        - {"type":"init", "session_id":"...", "model":"...", "timestamp":"..."}
        - {"type":"message", "role":"user"|"model", "content":"...", ...}
        - {"type":"tool_use", "tool_name":"Bash", "parameters":{...}, ...}
        - {"type":"tool_result", "tool_id":"...", "status":"success", "output":"...", ...}
        - {"type":"result", "status":"success", "stats":{...}, ...}
        """
        if not line.strip():
            return None

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            self.logger.warning(f"Invalid JSON at line {index}")
            return None

        # Ensure data is a dict (JSON could be a string, number, etc.)
        if not isinstance(data, dict):
            self.logger.debug(f"Skipping non-object JSON at line {index}")
            return None

        # Extract timestamp
        timestamp_str = data.get("timestamp") or datetime.now(UTC).isoformat()
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except ValueError:
            timestamp = datetime.now(UTC)

        # Handle Gemini CLI's type-based event format
        event_type = data.get("type")

        # Initialize defaults
        role: str | None = None
        content: str | Any = ""
        content_type = "text"
        tool_name: str | None = None
        tool_input: dict[str, Any] | None = None
        tool_result: dict[str, Any] | None = None

        if event_type == "init":
            # Session initialization event - skip or treat as system
            return None

        elif event_type == "message":
            # Message event with role (user/model)
            role = data.get("role")
            content = data.get("content", "")

        elif event_type in ("user", "model"):
            # Role specified directly in type field
            role = event_type
            content = data.get("content", "")

        elif event_type == "tool_use":
            # Tool invocation event
            role = "assistant"
            content_type = "tool_use"
            tool_name = data.get("tool_name") or data.get("function_name")
            tool_input = data.get("parameters") or data.get("args") or data.get("input")
            content = f"Tool call: {tool_name}"

        elif event_type == "tool_result":
            # Tool result event
            role = "tool"
            content_type = "tool_result"
            tool_name = data.get("tool_name")
            output = data.get("output") or data.get("result") or ""
            tool_result = {"output": output, "status": data.get("status", "unknown")}
            content = str(output)[:500] if output else ""  # Truncate long outputs

        elif event_type == "result":
            # Final result event - skip
            return None

        else:
            # Unknown event type, skip
            logger.debug("Unknown Gemini event type: %s", event_type)
            return None

        # Validate role is set - skip lines with missing role
        if not role:
            return None

        # Normalize role: model -> assistant
        if role == "model":
            role = "assistant"

        # Normalize content - handle list content (rich parts)
        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict):
                    if "text" in part:
                        text_parts.append(str(part["text"]))
                    # Check for tool calls embedded in content
                    if "functionCall" in part and isinstance(part["functionCall"], dict):
                        content_type = "tool_use"
                        tool_name = part["functionCall"].get("name")
                        tool_input = part["functionCall"].get("args")
            content = " ".join(text_parts)
        else:
            content = str(content or "")

        return ParsedMessage(
            index=index,
            role=role,
            content=content,
            content_type=content_type,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_result=tool_result,
            timestamp=timestamp,
            raw_json=data,
            usage=self._extract_usage(data),
        )

    def _extract_usage(self, data: dict[str, Any]) -> TokenUsage | None:
        """Extract token usage from Gemini message data."""
        # Gemini API standard is usageMetadata
        usage_data = data.get("usageMetadata")

        if not usage_data:
            return None

        return TokenUsage(
            input_tokens=usage_data.get("promptTokenCount", 0),
            output_tokens=usage_data.get("candidatesTokenCount", 0),
            # Gemini doesn't always split cache tokens in this view, strictly speaking
            # but usually total is prompt + candidates
            total_cost_usd=None,  # Cost calculation not standard in CLI output
        )

    def parse_lines(self, lines: list[str], start_index: int = 0) -> list[ParsedMessage]:
        """
        Parse a list of transcript lines.
        """
        parsed_messages = []
        current_index = start_index

        for line in lines:
            message = self.parse_line(line, current_index)
            if message:
                parsed_messages.append(message)
                current_index += 1

        return parsed_messages

    def parse_session_json(self, data: dict[str, Any]) -> list[ParsedMessage]:
        """
        Parse a Gemini native JSON session file.

        Gemini stores sessions as single JSON files with structure:
        {
            "sessionId": "uuid",
            "projectHash": "sha256hex",
            "startTime": "ISO8601",
            "lastUpdated": "ISO8601",
            "messages": [
                {"id": "uuid", "timestamp": "ISO8601", "type": "user", "content": "..."},
                {"id": "uuid", "timestamp": "ISO8601", "type": "gemini", "content": "...",
                 "toolCalls": [...]},
                ...
            ]
        }

        Args:
            data: Parsed JSON dict from the session file.

        Returns:
            List of ParsedMessage objects.
        """
        messages = data.get("messages", [])
        parsed: list[ParsedMessage] = []
        index = 0

        for msg in messages:
            result = self._parse_session_message(msg, index)
            if result:
                parsed.extend(result)
                index += len(result)

        return parsed

    def _parse_session_message(self, msg: dict[str, Any], start_index: int) -> list[ParsedMessage]:
        """Parse a single message from a Gemini JSON session file.

        Returns a list because a gemini message with toolCalls produces
        multiple ParsedMessages (the response text + tool_use + tool_result).
        """
        msg_type = msg.get("type")
        content = msg.get("content", "")
        timestamp_str = msg.get("timestamp")

        try:
            timestamp = (
                datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                if timestamp_str
                else datetime.now(UTC)
            )
        except ValueError:
            timestamp = datetime.now(UTC)

        if msg_type == "user":
            return [
                ParsedMessage(
                    index=start_index,
                    role="user",
                    content=str(content),
                    content_type="text",
                    tool_name=None,
                    tool_input=None,
                    tool_result=None,
                    timestamp=timestamp,
                    raw_json=msg,
                    usage=self._extract_usage(msg),
                )
            ]

        elif msg_type == "gemini":
            results: list[ParsedMessage] = []
            idx = start_index

            # Main text response
            if content:
                results.append(
                    ParsedMessage(
                        index=idx,
                        role="assistant",
                        content=str(content),
                        content_type="text",
                        tool_name=None,
                        tool_input=None,
                        tool_result=None,
                        timestamp=timestamp,
                        raw_json=msg,
                        usage=self._extract_usage(msg),
                    )
                )
                idx += 1

            # Tool calls embedded in the message
            tool_calls = msg.get("toolCalls", [])
            for tc in tool_calls:
                tool_name = tc.get("name", "unknown")
                tool_args = tc.get("args")

                # Tool use
                results.append(
                    ParsedMessage(
                        index=idx,
                        role="assistant",
                        content=f"Tool call: {tool_name}",
                        content_type="tool_use",
                        tool_name=tool_name,
                        tool_input=tool_args,
                        tool_result=None,
                        timestamp=timestamp,
                        raw_json=tc,
                        usage=self._extract_usage(msg),
                    )
                )
                idx += 1

                # Tool result (if present)
                # Gemini stores result as a list: [{"functionResponse": {...}}]
                # but earlier code assumed a dict: {"functionResponse": {...}}
                result_value = tc.get("result")
                func_response = None
                if isinstance(result_value, list) and result_value:
                    first = result_value[0]
                    if isinstance(first, dict):
                        func_response = first.get("functionResponse")
                elif isinstance(result_value, dict):
                    func_response = result_value.get("functionResponse")
                if func_response:
                    output = str(func_response)[:500]
                    results.append(
                        ParsedMessage(
                            index=idx,
                            role="tool",
                            content=output,
                            content_type="tool_result",
                            tool_name=tool_name,
                            tool_input=None,
                            tool_result={"output": func_response, "status": "success"},
                            timestamp=timestamp,
                            raw_json=tc,
                            usage=self._extract_usage(msg),
                        )
                    )
                    idx += 1

            return results

        if msg_type in ("info", "warning"):
            # Skip info/warning messages — they're not conversation content
            return []

        # Unknown type
        return []
