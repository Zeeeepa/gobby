"""Artifact type classifier.

Automatically classifies content into artifact types:
- code: Programming language code blocks
- file_path: File or directory paths
- error: Error messages and stack traces
- command_output: Terminal/shell command output
- structured_data: JSON, YAML, TOML, XML
- text: Plain text (default)

Also extracts relevant metadata for each type (language, extension, format, etc.)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = ["ArtifactType", "ClassificationResult", "classify_artifact"]


class ArtifactType(str, Enum):
    """Artifact type enumeration."""

    CODE = "code"
    FILE_PATH = "file_path"
    ERROR = "error"
    COMMAND_OUTPUT = "command_output"
    STRUCTURED_DATA = "structured_data"
    TEXT = "text"


@dataclass
class ClassificationResult:
    """Result of artifact classification."""

    artifact_type: ArtifactType
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "artifact_type": self.artifact_type.value,
            "metadata": self.metadata,
        }


# Language detection patterns (more specific patterns first)
_LANGUAGE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Python
    (
        "python",
        re.compile(
            r"^\s*(def\s+\w+|class\s+\w+|import\s+\w+|from\s+\w+\s+import|async\s+def\s+\w+|@\w+)",
            re.MULTILINE,
        ),
    ),
    # TypeScript (must be before JavaScript - has interface/type)
    (
        "typescript",
        re.compile(
            r"^\s*(interface\s+\w+|type\s+\w+\s*=|:\s*(string|number|boolean|any)\b)", re.MULTILINE
        ),
    ),
    # JavaScript
    (
        "javascript",
        re.compile(
            r"^\s*(function\s+\w+|const\s+\w+\s*=|let\s+\w+\s*=|var\s+\w+\s*=|=>\s*\{)",
            re.MULTILINE,
        ),
    ),
    # Rust
    (
        "rust",
        re.compile(
            r"^\s*(fn\s+\w+|impl\s+|struct\s+\w+|enum\s+\w+|use\s+\w+|pub\s+fn)", re.MULTILINE
        ),
    ),
    # Go
    ("go", re.compile(r"^\s*(func\s+\w+|func\s+\(\w+|package\s+\w+|import\s+\()", re.MULTILINE)),
    # SQL
    (
        "sql",
        re.compile(
            r"^\s*(SELECT\s+|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|CREATE\s+TABLE|DROP\s+TABLE)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    # Shell/Bash
    (
        "bash",
        re.compile(
            r"(^#!/bin/(ba)?sh|^\s*for\s+\w+\s+in\s+|^\s*if\s+\[\[?\s+|^\s*while\s+|echo\s+[\"'])",
            re.MULTILINE,
        ),
    ),
]

# Markdown code fence pattern
_CODE_FENCE_PATTERN = re.compile(r"^```(\w*).*?\n(.*?)```", re.DOTALL | re.MULTILINE)

# File path patterns
_UNIX_PATH_PATTERN = re.compile(r"^(/[\w./\-_]+|\.{1,2}/[\w./\-_]+)$")
_WINDOWS_PATH_PATTERN = re.compile(r"^[A-Za-z]:\\[\w\\/.\-_]+$")
_RELATIVE_PATH_PATTERN = re.compile(r"^[\w\-_]+/[\w./\-_]+\.\w+$")

# Error patterns
_ERROR_PATTERNS = [
    re.compile(r"^Traceback \(most recent call last\):", re.MULTILINE),
    re.compile(r"^\w+Error:\s+", re.MULTILINE),
    re.compile(r"^TypeError:\s+", re.MULTILINE),
    re.compile(r"^Exception\s+", re.MULTILINE),
    re.compile(r"^Error:\s+", re.MULTILINE),
    re.compile(r"thread\s+'.*'\s+panicked\s+at", re.MULTILINE),
    re.compile(r"^\s+at\s+[\w.]+\([\w.]+:\d+\)$", re.MULTILINE),  # JS stack trace line
]

# Command output patterns
_COMMAND_OUTPUT_PATTERNS = [
    re.compile(r"^On branch\s+\w+", re.MULTILINE),  # git status
    re.compile(r"^\$ \w+", re.MULTILINE),  # shell prompt
    re.compile(r"^npm\s+(WARN|ERR!?|notice)", re.MULTILINE),  # npm
    re.compile(r"^={3,}\s+test session starts\s+={3,}$", re.MULTILINE),  # pytest
    re.compile(r"^total\s+\d+\s*$", re.MULTILINE),  # ls -l
    re.compile(r"^(d|-)rwx", re.MULTILINE),  # ls -l permissions
    re.compile(r"^added\s+\d+\s+packages?", re.MULTILINE),  # npm install
    re.compile(r"^collected\s+\d+\s+items?", re.MULTILINE),  # pytest
    re.compile(r"^\d+\s+passed", re.MULTILINE),  # pytest results
]


def _detect_language(content: str) -> str | None:
    """Detect programming language from content."""
    for lang, pattern in _LANGUAGE_PATTERNS:
        if pattern.search(content):
            return lang
    return None


def _is_file_path(content: str) -> tuple[bool, dict[str, Any]]:
    """Check if content is a file path and extract metadata."""
    content = content.strip()

    # Don't classify multi-line content as a file path
    if "\n" in content:
        return False, {}

    metadata: dict[str, Any] = {}

    # Check patterns
    if _UNIX_PATH_PATTERN.match(content):
        pass
    elif _WINDOWS_PATH_PATTERN.match(content):
        pass
    elif _RELATIVE_PATH_PATTERN.match(content):
        pass
    else:
        return False, {}

    # Extract filename and extension
    parts = content.replace("\\", "/").split("/")
    filename = parts[-1]
    metadata["filename"] = filename

    if "." in filename:
        ext = filename.rsplit(".", 1)[-1]
        metadata["extension"] = ext
    else:
        metadata["extension"] = None

    return True, metadata


def _is_error(content: str) -> bool:
    """Check if content is an error message or stack trace."""
    for pattern in _ERROR_PATTERNS:
        if pattern.search(content):
            return True
    return False


def _is_command_output(content: str) -> bool:
    """Check if content is command output."""
    for pattern in _COMMAND_OUTPUT_PATTERNS:
        if pattern.search(content):
            return True
    return False


def _is_json(content: str) -> bool:
    """Check if content is valid JSON."""
    content = content.strip()
    if not (content.startswith("{") or content.startswith("[")):
        return False
    try:
        json.loads(content)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def _is_yaml(content: str) -> bool:
    """Check if content looks like YAML (simple heuristic)."""
    content = content.strip()
    lines = content.split("\n")

    # YAML typically has key: value patterns
    # Must have actual values after the colon (not just colons in prose)
    yaml_kv_pattern = re.compile(r"^\s*[\w\-_]+:\s*\S")
    yaml_list_with_kv_pattern = re.compile(r"^\s*-\s+[\w\-_]+:\s*")

    yaml_kv_lines = 0
    total_non_empty = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        total_non_empty += 1
        # Count lines with key: value pattern (not just list items)
        if yaml_kv_pattern.match(line) or yaml_list_with_kv_pattern.match(line):
            yaml_kv_lines += 1

    # Need at least 2 key-value lines and they should be significant portion
    return yaml_kv_lines >= 2 and (yaml_kv_lines / max(total_non_empty, 1)) > 0.3


def _is_toml(content: str) -> bool:
    """Check if content looks like TOML."""
    content = content.strip()

    # TOML has [section] headers and key = value
    section_pattern = re.compile(r"^\s*\[[\w.\-]+\]\s*$", re.MULTILINE)
    kv_pattern = re.compile(r"^\s*[\w\-]+\s*=\s*", re.MULTILINE)

    has_section = section_pattern.search(content) is not None
    has_kv = kv_pattern.search(content) is not None

    return has_section and has_kv


def _is_xml(content: str) -> bool:
    """Check if content looks like XML."""
    content = content.strip()

    # XML starts with <?xml or <tag>
    if content.startswith("<?xml"):
        return True

    # Check for matching opening/closing tags
    tag_pattern = re.compile(r"^<(\w+)[^>]*>.*</\1>", re.DOTALL)
    return tag_pattern.match(content) is not None


def _is_code_block(content: str) -> tuple[bool, dict[str, Any]]:
    """Check if content is a markdown code block and extract language."""
    match = _CODE_FENCE_PATTERN.match(content.strip())
    if match:
        lang = match.group(1).lower() if match.group(1) else None
        return True, {"language": lang} if lang else {}
    return False, {}


def classify_artifact(content: str) -> ClassificationResult:
    """
    Classify content into an artifact type with metadata.

    Args:
        content: The content to classify

    Returns:
        ClassificationResult with artifact_type and extracted metadata
    """
    if not content or not content.strip():
        return ClassificationResult(artifact_type=ArtifactType.TEXT, metadata={})

    # Check for markdown code fence first
    is_code_fence, fence_metadata = _is_code_block(content)
    if is_code_fence:
        metadata = fence_metadata.copy()
        # If no language in fence, try to detect from content
        if "language" not in metadata or not metadata["language"]:
            inner_content = _CODE_FENCE_PATTERN.match(content.strip())
            if inner_content:
                detected_lang = _detect_language(inner_content.group(2))
                if detected_lang:
                    metadata["language"] = detected_lang
        return ClassificationResult(artifact_type=ArtifactType.CODE, metadata=metadata)

    # Check for file path (single line only)
    is_path, path_metadata = _is_file_path(content)
    if is_path:
        return ClassificationResult(artifact_type=ArtifactType.FILE_PATH, metadata=path_metadata)

    # Check for error messages/stack traces
    if _is_error(content):
        metadata = {}
        # Try to extract error type
        error_match = re.search(r"^(\w+Error):", content, re.MULTILINE)
        if error_match:
            metadata["error"] = error_match.group(1)
        return ClassificationResult(artifact_type=ArtifactType.ERROR, metadata=metadata)

    # Check for code patterns BEFORE structured data
    # (TypeScript interfaces look like YAML otherwise)
    detected_lang = _detect_language(content)
    if detected_lang:
        return ClassificationResult(
            artifact_type=ArtifactType.CODE, metadata={"language": detected_lang}
        )

    # Check for structured data formats
    if _is_json(content):
        return ClassificationResult(
            artifact_type=ArtifactType.STRUCTURED_DATA, metadata={"format": "json"}
        )

    if _is_xml(content):
        return ClassificationResult(
            artifact_type=ArtifactType.STRUCTURED_DATA, metadata={"format": "xml"}
        )

    if _is_toml(content):
        return ClassificationResult(
            artifact_type=ArtifactType.STRUCTURED_DATA, metadata={"format": "toml"}
        )

    if _is_yaml(content):
        return ClassificationResult(
            artifact_type=ArtifactType.STRUCTURED_DATA, metadata={"format": "yaml"}
        )

    # Check for command output
    if _is_command_output(content):
        return ClassificationResult(artifact_type=ArtifactType.COMMAND_OUTPUT, metadata={})

    # Default to text
    return ClassificationResult(artifact_type=ArtifactType.TEXT, metadata={})
