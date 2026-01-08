"""Issue extraction from LLM validation responses.

Provides utilities for parsing structured issues from validation LLM responses.
"""

import logging
from typing import Any

from gobby.tasks.validation_models import Issue, IssueSeverity, IssueType
from gobby.utils.json_helpers import extract_json_object

logger = logging.getLogger(__name__)


def parse_issues_from_response(response: str) -> list[Issue]:
    """Parse structured issues from an LLM validation response.

    Supports multiple response formats:
    - Raw JSON object with "issues" array
    - JSON wrapped in markdown code blocks
    - JSON with preamble text

    Falls back gracefully on parse failures.

    Args:
        response: Raw LLM response text

    Returns:
        List of Issue objects. Empty list if no issues found or parse fails.
    """
    if not response or not response.strip():
        return []

    content = response.strip()

    # Try to extract JSON from the response
    json_data = _extract_json(content)

    if json_data is None:
        # Could not parse JSON - try to create fallback issue from text
        return _create_fallback_issue(content)

    # Extract issues array from parsed JSON
    issues_data = json_data.get("issues", [])

    if not isinstance(issues_data, list):
        return []

    # Parse each issue
    issues: list[Issue] = []
    for issue_dict in issues_data:
        if not isinstance(issue_dict, dict):
            continue

        issue = _parse_single_issue(issue_dict)
        if issue:
            issues.append(issue)

    return issues


def _extract_json(content: str) -> dict[str, Any] | None:
    """Extract and parse JSON from response content.

    Handles:
    - Raw JSON
    - JSON in markdown code blocks
    - JSON with preamble text

    Args:
        content: Response content to parse

    Returns:
        Parsed dict or None if parsing fails
    """
    return extract_json_object(content)


def _parse_single_issue(issue_dict: dict[str, Any]) -> Issue | None:
    """Parse a single issue dictionary into an Issue object.

    Args:
        issue_dict: Dictionary with issue fields

    Returns:
        Issue object or None if required fields are missing/invalid
    """
    # Check required fields
    type_str = issue_dict.get("type")
    severity_str = issue_dict.get("severity")
    title = issue_dict.get("title")

    if not all([type_str, severity_str, title]):
        logger.debug(f"Issue missing required fields: {issue_dict}")
        return None

    # Ensure title is a string
    title = str(title)

    # Parse enums
    try:
        issue_type = IssueType(type_str)
    except ValueError:
        logger.debug(f"Invalid issue type: {type_str}")
        return None

    try:
        severity = IssueSeverity(severity_str)
    except ValueError:
        logger.debug(f"Invalid severity: {severity_str}")
        return None

    # Handle optional fields - convert null to None
    location = issue_dict.get("location")
    if location is None or location == "null":
        location = None

    details = issue_dict.get("details")
    if details is None or details == "null":
        details = None

    suggested_fix = issue_dict.get("suggested_fix")
    if suggested_fix is None or suggested_fix == "null":
        suggested_fix = None

    recurring_count = issue_dict.get("recurring_count", 0)
    if not isinstance(recurring_count, int):
        recurring_count = 0

    return Issue(
        issue_type=issue_type,
        severity=severity,
        title=title,
        location=location,
        details=details,
        suggested_fix=suggested_fix,
        recurring_count=recurring_count,
    )


def _create_fallback_issue(content: str) -> list[Issue]:
    """Create a fallback issue from unstructured text.

    Used when JSON parsing fails but there's meaningful content.

    Args:
        content: Unstructured text content

    Returns:
        List with single fallback Issue, or empty list
    """
    # Don't create fallback for very short content
    if len(content) < 20:
        return []

    # Try to extract a meaningful title from the content
    # Take first sentence or first 100 chars
    title = content.split(".")[0].strip()
    if len(title) > 100:
        title = title[:97] + "..."
    if not title:
        title = "Validation issue"

    return [
        Issue(
            issue_type=IssueType.ACCEPTANCE_GAP,
            severity=IssueSeverity.MAJOR,
            title=title,
            details=content[:1000] if len(content) > 1000 else content,
        )
    ]
