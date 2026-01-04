"""Validation models for Task System V2.

Provides Issue dataclass and related enums for representing validation issues.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class IssueType(Enum):
    """Types of issues that can occur during task validation."""

    TEST_FAILURE = "test_failure"
    LINT_ERROR = "lint_error"
    ACCEPTANCE_GAP = "acceptance_gap"
    TYPE_ERROR = "type_error"
    SECURITY = "security"


class IssueSeverity(Enum):
    """Severity levels for validation issues."""

    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"


@dataclass
class Issue:
    """Represents a validation issue found during task verification.

    Attributes:
        issue_type: The category of issue (test failure, lint error, etc.)
        severity: How critical the issue is (blocker, major, minor)
        title: A short summary of the issue
        location: File path and line number where the issue occurred (optional)
        details: Extended description of the issue (optional)
        suggested_fix: Recommended action to resolve the issue (optional)
        recurring_count: Number of times this issue has recurred across iterations
    """

    issue_type: IssueType
    severity: IssueSeverity
    title: str
    location: str | None = None
    details: str | None = None
    suggested_fix: str | None = None
    recurring_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize Issue to dictionary for JSON storage."""
        return {
            "type": self.issue_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "location": self.location,
            "details": self.details,
            "suggested_fix": self.suggested_fix,
            "recurring_count": self.recurring_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Issue":
        """Deserialize Issue from dictionary.

        Args:
            data: Dictionary with issue fields. Required: type, severity, title.

        Returns:
            Issue instance

        Raises:
            KeyError: If required fields ("type", "severity", "title") are missing
            ValueError: If type or severity values are invalid
        """
        # Parse enums - these will raise ValueError if invalid
        issue_type = IssueType(data["type"])
        severity = IssueSeverity(data["severity"])

        return cls(
            issue_type=issue_type,
            severity=severity,
            title=data["title"],
            location=data.get("location"),
            details=data.get("details"),
            suggested_fix=data.get("suggested_fix"),
            recurring_count=data.get("recurring_count", 0),
        )
