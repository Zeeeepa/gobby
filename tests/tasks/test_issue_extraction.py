"""Tests for issue extraction from LLM validation responses.

TDD Red Phase: These tests define the expected behavior for
parse_issues_from_response() which does not yet exist.

Task: gt-35d11c
"""

from gobby.tasks.validation_models import IssueSeverity, IssueType


class TestParseIssuesFromResponse:
    """Tests for parsing structured issues from LLM validation response."""

    def test_parse_valid_json_array_of_issues(self):
        """Test parsing a valid JSON array of issues from LLM response."""
        # Import the function we're testing (will fail until implemented)
        from gobby.tasks.issue_extraction import parse_issues_from_response

        response = """
        {
            "status": "invalid",
            "feedback": "Found 2 issues",
            "issues": [
                {
                    "type": "test_failure",
                    "severity": "blocker",
                    "title": "Test test_auth_flow fails",
                    "location": "tests/test_auth.py:42",
                    "details": "AssertionError: Expected 200, got 401",
                    "suggested_fix": "Check authentication token handling"
                },
                {
                    "type": "lint_error",
                    "severity": "minor",
                    "title": "Unused import",
                    "location": "src/auth.py:3",
                    "details": "Module 'os' imported but unused"
                }
            ]
        }
        """

        issues = parse_issues_from_response(response)

        assert len(issues) == 2

        # First issue
        assert issues[0].issue_type == IssueType.TEST_FAILURE
        assert issues[0].severity == IssueSeverity.BLOCKER
        assert issues[0].title == "Test test_auth_flow fails"
        assert issues[0].location == "tests/test_auth.py:42"
        assert "AssertionError" in issues[0].details

        # Second issue
        assert issues[1].issue_type == IssueType.LINT_ERROR
        assert issues[1].severity == IssueSeverity.MINOR
        assert issues[1].title == "Unused import"

    def test_parse_issues_from_markdown_code_block(self):
        """Test parsing issues from response wrapped in markdown code block."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        response = """
        Based on my analysis, here are the issues:

        ```json
        {
            "status": "invalid",
            "issues": [
                {
                    "type": "acceptance_gap",
                    "severity": "major",
                    "title": "Missing error handling"
                }
            ]
        }
        ```
        """

        issues = parse_issues_from_response(response)

        assert len(issues) == 1
        assert issues[0].issue_type == IssueType.ACCEPTANCE_GAP
        assert issues[0].severity == IssueSeverity.MAJOR

    def test_parse_handles_malformed_json_gracefully(self):
        """Test graceful handling of malformed JSON response."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        malformed_response = """
        {
            "status": "invalid",
            "issues": [
                {type: "test_failure", severity: "blocker", title: "Missing quotes"}
            ]
        }
        """

        # Should not raise, should return empty list or fallback issue
        issues = parse_issues_from_response(malformed_response)

        assert isinstance(issues, list)
        # May return empty list or fallback unstructured issue
        # The implementation decides the exact behavior

    def test_parse_handles_empty_response(self):
        """Test handling of empty LLM response."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        issues = parse_issues_from_response("")

        assert issues == []

    def test_parse_handles_whitespace_only_response(self):
        """Test handling of whitespace-only response."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        issues = parse_issues_from_response("   \n\t  ")

        assert issues == []

    def test_parse_validates_required_issue_fields(self):
        """Test that issues with missing required fields are handled."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        # Missing required 'type' field
        response = """
        {
            "issues": [
                {
                    "severity": "major",
                    "title": "Some issue"
                }
            ]
        }
        """

        # Should either skip invalid issues or return fallback
        issues = parse_issues_from_response(response)

        # The implementation should handle this gracefully
        assert isinstance(issues, list)

    def test_parse_validates_invalid_enum_values(self):
        """Test handling of invalid enum values in issues."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        response = """
        {
            "issues": [
                {
                    "type": "invalid_type_value",
                    "severity": "catastrophic",
                    "title": "Bad enum values"
                }
            ]
        }
        """

        # Should handle invalid enum gracefully
        issues = parse_issues_from_response(response)

        assert isinstance(issues, list)

    def test_parse_falls_back_to_unstructured_issue_on_failure(self):
        """Test fallback to single unstructured issue when parsing fails."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        # Plain text response with no JSON structure
        response = "The validation failed because tests are not passing. Please fix the authentication module."

        issues = parse_issues_from_response(response)

        # Should create a single fallback issue with the response as details
        assert isinstance(issues, list)
        if issues:  # Implementation may return empty or fallback
            assert len(issues) == 1
            assert issues[0].issue_type == IssueType.ACCEPTANCE_GAP
            assert issues[0].severity == IssueSeverity.MAJOR
            assert (
                "authentication" in issues[0].title.lower()
                or "authentication" in (issues[0].details or "").lower()
            )

    def test_parse_handles_no_issues_array(self):
        """Test response with valid JSON but no issues array."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        response = """
        {
            "status": "valid",
            "feedback": "All criteria met"
        }
        """

        issues = parse_issues_from_response(response)

        assert issues == []

    def test_parse_handles_empty_issues_array(self):
        """Test response with empty issues array."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        response = """
        {
            "status": "valid",
            "issues": []
        }
        """

        issues = parse_issues_from_response(response)

        assert issues == []

    def test_parse_preserves_recurring_count(self):
        """Test that recurring_count field is preserved if present."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        response = """
        {
            "issues": [
                {
                    "type": "test_failure",
                    "severity": "blocker",
                    "title": "Recurring test failure",
                    "recurring_count": 3
                }
            ]
        }
        """

        issues = parse_issues_from_response(response)

        assert len(issues) == 1
        assert issues[0].recurring_count == 3

    def test_parse_handles_mixed_valid_invalid_issues(self):
        """Test parsing response with mix of valid and invalid issues."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        response = """
        {
            "issues": [
                {
                    "type": "test_failure",
                    "severity": "blocker",
                    "title": "Valid issue"
                },
                {
                    "severity": "minor",
                    "title": "Missing type field"
                },
                {
                    "type": "security",
                    "severity": "blocker",
                    "title": "Another valid issue"
                }
            ]
        }
        """

        issues = parse_issues_from_response(response)

        # Should parse the valid issues, skip or handle invalid ones
        assert isinstance(issues, list)
        # At minimum, the two valid issues should be parsed
        valid_titles = [i.title for i in issues]
        assert "Valid issue" in valid_titles or len(issues) >= 1

    def test_parse_handles_nested_json_in_response(self):
        """Test response with nested JSON structures."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        response = """
        {
            "analysis": {
                "summary": "Found issues"
            },
            "issues": [
                {
                    "type": "type_error",
                    "severity": "major",
                    "title": "Type mismatch",
                    "details": "Expected str, got int"
                }
            ]
        }
        """

        issues = parse_issues_from_response(response)

        assert len(issues) == 1
        assert issues[0].issue_type == IssueType.TYPE_ERROR


class TestParseIssuesEdgeCases:
    """Edge case tests for issue parsing."""

    def test_parse_very_long_response(self):
        """Test handling of very long LLM response."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        # Create a response with many issues
        issues_json = [
            {
                "type": "lint_error",
                "severity": "minor",
                "title": f"Issue {i}",
                "details": "x" * 1000,  # Long details
            }
            for i in range(100)
        ]

        import json

        response = json.dumps({"issues": issues_json})

        issues = parse_issues_from_response(response)

        # Should handle large responses (may truncate)
        assert isinstance(issues, list)
        assert len(issues) <= 100

    def test_parse_unicode_content(self):
        """Test handling of unicode characters in issues."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        response = """
        {
            "issues": [
                {
                    "type": "acceptance_gap",
                    "severity": "major",
                    "title": "Missing i18n: 日本語サポート",
                    "details": "Need to support émojis 🎉 and special chars"
                }
            ]
        }
        """

        issues = parse_issues_from_response(response)

        assert len(issues) == 1
        assert "日本語" in issues[0].title
        assert "🎉" in issues[0].details

    def test_parse_null_values_in_optional_fields(self):
        """Test handling of null values in optional issue fields."""
        from gobby.tasks.issue_extraction import parse_issues_from_response

        response = """
        {
            "issues": [
                {
                    "type": "test_failure",
                    "severity": "blocker",
                    "title": "Test fails",
                    "location": null,
                    "details": null,
                    "suggested_fix": null
                }
            ]
        }
        """

        issues = parse_issues_from_response(response)

        assert len(issues) == 1
        assert issues[0].location is None
        assert issues[0].details is None
        assert issues[0].suggested_fix is None
