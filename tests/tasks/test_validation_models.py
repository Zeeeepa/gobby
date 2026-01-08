"""Tests for Issue dataclass and validation models."""

import json

import pytest

from gobby.tasks.validation_models import Issue, IssueSeverity, IssueType


class TestIssueType:
    """Tests for IssueType enum."""

    def test_valid_issue_types(self):
        """Test all valid issue types are defined."""
        assert IssueType.TEST_FAILURE.value == "test_failure"
        assert IssueType.LINT_ERROR.value == "lint_error"
        assert IssueType.ACCEPTANCE_GAP.value == "acceptance_gap"
        assert IssueType.TYPE_ERROR.value == "type_error"
        assert IssueType.SECURITY.value == "security"

    def test_issue_type_from_string(self):
        """Test creating IssueType from string value."""
        assert IssueType("test_failure") == IssueType.TEST_FAILURE
        assert IssueType("lint_error") == IssueType.LINT_ERROR


class TestIssueSeverity:
    """Tests for IssueSeverity enum."""

    def test_valid_severities(self):
        """Test all valid severities are defined."""
        assert IssueSeverity.BLOCKER.value == "blocker"
        assert IssueSeverity.MAJOR.value == "major"
        assert IssueSeverity.MINOR.value == "minor"

    def test_severity_from_string(self):
        """Test creating IssueSeverity from string value."""
        assert IssueSeverity("blocker") == IssueSeverity.BLOCKER
        assert IssueSeverity("minor") == IssueSeverity.MINOR


class TestIssue:
    """Tests for Issue dataclass."""

    def test_create_issue_with_required_fields(self):
        """Test creating an Issue with required fields only."""
        issue = Issue(
            issue_type=IssueType.TEST_FAILURE,
            severity=IssueSeverity.MAJOR,
            title="Test assertion failed",
        )

        assert issue.issue_type == IssueType.TEST_FAILURE
        assert issue.severity == IssueSeverity.MAJOR
        assert issue.title == "Test assertion failed"
        assert issue.location is None
        assert issue.details is None
        assert issue.suggested_fix is None
        assert issue.recurring_count == 0

    def test_create_issue_with_all_fields(self):
        """Test creating an Issue with all fields."""
        issue = Issue(
            issue_type=IssueType.LINT_ERROR,
            severity=IssueSeverity.MINOR,
            title="Missing semicolon",
            location="src/main.py:42",
            details="Expected semicolon at end of statement",
            suggested_fix="Add semicolon",
            recurring_count=3,
        )

        assert issue.issue_type == IssueType.LINT_ERROR
        assert issue.severity == IssueSeverity.MINOR
        assert issue.title == "Missing semicolon"
        assert issue.location == "src/main.py:42"
        assert issue.details == "Expected semicolon at end of statement"
        assert issue.suggested_fix == "Add semicolon"
        assert issue.recurring_count == 3

    def test_issue_to_dict(self):
        """Test Issue serialization to dictionary."""
        issue = Issue(
            issue_type=IssueType.SECURITY,
            severity=IssueSeverity.BLOCKER,
            title="SQL injection vulnerability",
            location="src/db.py:100",
            details="Unsanitized user input in query",
            suggested_fix="Use parameterized queries",
            recurring_count=1,
        )

        d = issue.to_dict()

        assert d["type"] == "security"
        assert d["severity"] == "blocker"
        assert d["title"] == "SQL injection vulnerability"
        assert d["location"] == "src/db.py:100"
        assert d["details"] == "Unsanitized user input in query"
        assert d["suggested_fix"] == "Use parameterized queries"
        assert d["recurring_count"] == 1

    def test_issue_from_dict(self):
        """Test Issue deserialization from dictionary."""
        d = {
            "type": "type_error",
            "severity": "major",
            "title": "Type mismatch",
            "location": "src/utils.py:25",
            "details": "Expected int, got str",
            "suggested_fix": "Convert type before assignment",
            "recurring_count": 2,
        }

        issue = Issue.from_dict(d)

        assert issue.issue_type == IssueType.TYPE_ERROR
        assert issue.severity == IssueSeverity.MAJOR
        assert issue.title == "Type mismatch"
        assert issue.location == "src/utils.py:25"
        assert issue.details == "Expected int, got str"
        assert issue.suggested_fix == "Convert type before assignment"
        assert issue.recurring_count == 2

    def test_issue_from_dict_minimal(self):
        """Test Issue deserialization with minimal fields."""
        d = {
            "type": "acceptance_gap",
            "severity": "minor",
            "title": "Missing feature",
        }

        issue = Issue.from_dict(d)

        assert issue.issue_type == IssueType.ACCEPTANCE_GAP
        assert issue.severity == IssueSeverity.MINOR
        assert issue.title == "Missing feature"
        assert issue.location is None
        assert issue.recurring_count == 0

    def test_issue_json_round_trip(self):
        """Test Issue JSON serialization round trip."""
        original = Issue(
            issue_type=IssueType.TEST_FAILURE,
            severity=IssueSeverity.BLOCKER,
            title="Critical test failure",
            location="tests/test_core.py:55",
            details="Assertion failed: expected True, got False",
            recurring_count=5,
        )

        # Serialize to JSON
        json_str = json.dumps(original.to_dict())

        # Deserialize from JSON
        restored = Issue.from_dict(json.loads(json_str))

        assert restored.issue_type == original.issue_type
        assert restored.severity == original.severity
        assert restored.title == original.title
        assert restored.location == original.location
        assert restored.details == original.details
        assert restored.recurring_count == original.recurring_count

    def test_issue_list_serialization(self):
        """Test serializing a list of Issues."""
        issues = [
            Issue(
                issue_type=IssueType.TEST_FAILURE,
                severity=IssueSeverity.MAJOR,
                title="Test 1 failed",
            ),
            Issue(
                issue_type=IssueType.LINT_ERROR,
                severity=IssueSeverity.MINOR,
                title="Unused import",
            ),
        ]

        # Serialize list
        json_str = json.dumps([i.to_dict() for i in issues])

        # Deserialize list
        restored = [Issue.from_dict(d) for d in json.loads(json_str)]

        assert len(restored) == 2
        assert restored[0].title == "Test 1 failed"
        assert restored[1].title == "Unused import"

    def test_issue_invalid_type_raises(self):
        """Test that invalid issue type raises ValueError."""
        with pytest.raises(ValueError):
            Issue.from_dict(
                {
                    "type": "invalid_type",
                    "severity": "major",
                    "title": "Test",
                }
            )

    def test_issue_invalid_severity_raises(self):
        """Test that invalid severity raises ValueError."""
        with pytest.raises(ValueError):
            Issue.from_dict(
                {
                    "type": "test_failure",
                    "severity": "invalid_severity",
                    "title": "Test",
                }
            )
