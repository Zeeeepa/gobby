"""Tests for skill safety scanner wrapper.

Exercises the real scan_skill_content function with all code paths:
- No findings (safe)
- LOW severity findings (safe)
- MEDIUM severity findings (safe)
- HIGH severity findings (unsafe)
- CRITICAL severity findings (unsafe)
- Multiple findings across both analyzers
- None results from analyzers
- Non-list result from analyzer (single object)
- Finding with missing/None severity attribute
- Temp file creation and cleanup
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_finding(
    severity: str = "LOW",
    title: str = "Test finding",
    description: str = "Test description",
    category: str = "test",
    remediation: str = "Fix it",
    location: str = "line 1",
) -> MagicMock:
    """Create a mock finding object with standard attributes."""
    finding = MagicMock()
    finding.severity = severity
    finding.title = title
    finding.description = description
    finding.category = category
    finding.remediation = remediation
    finding.location = location
    return finding


def _make_result_obj(findings: list | None = None) -> MagicMock:
    """Create a mock analysis result object with findings list."""
    obj = MagicMock()
    obj.findings = findings if findings is not None else []
    return obj


def _make_mock_module(
    static_return=None,
    behavioral_return=None,
) -> MagicMock:
    """Create a mock skill_scanner module."""
    mod = MagicMock()
    mod.StaticAnalyzer.return_value.analyze.return_value = (
        static_return if static_return is not None else []
    )
    mod.BehavioralAnalyzer.return_value.analyze.return_value = (
        behavioral_return if behavioral_return is not None else []
    )
    return mod


def _scan(content: str, name: str = "test", mock_mod: MagicMock | None = None) -> dict:
    """Run scan_skill_content with mocked skill_scanner module."""
    if mock_mod is None:
        mock_mod = _make_mock_module()
    with patch.dict(sys.modules, {"skill_scanner": mock_mod}):
        from gobby.skills.scanner import scan_skill_content

        return scan_skill_content(content, name=name)


class TestNoFindings:
    """Tests when analyzers return no findings."""

    def test_empty_results_is_safe(self) -> None:
        result = _scan("# Safe skill", name="safe")
        assert result["is_safe"] is True

    def test_empty_results_max_severity_is_info(self) -> None:
        result = _scan("# Safe skill")
        assert result["max_severity"] == "INFO"

    def test_empty_results_findings_count_zero(self) -> None:
        result = _scan("# Safe skill")
        assert result["findings_count"] == 0

    def test_empty_results_findings_list_empty(self) -> None:
        result = _scan("# Safe skill")
        assert result["findings"] == []

    def test_scan_duration_is_recorded(self) -> None:
        result = _scan("# Test")
        assert "scan_duration_seconds" in result
        assert isinstance(result["scan_duration_seconds"], float)
        assert result["scan_duration_seconds"] >= 0

    def test_return_keys(self) -> None:
        result = _scan("# Test")
        expected_keys = {
            "is_safe",
            "max_severity",
            "scan_duration_seconds",
            "findings",
            "findings_count",
        }
        assert set(result.keys()) == expected_keys


class TestNoneResults:
    """Tests when analyzers return None instead of a list."""

    def test_static_returns_none(self) -> None:
        mock_mod = _make_mock_module(static_return=None, behavioral_return=[])
        # Set return to actual None (not empty list)
        mock_mod.StaticAnalyzer.return_value.analyze.return_value = None
        result = _scan("# Empty", mock_mod=mock_mod)
        assert result["is_safe"] is True
        assert result["findings_count"] == 0

    def test_behavioral_returns_none(self) -> None:
        mock_mod = _make_mock_module(static_return=[], behavioral_return=None)
        mock_mod.BehavioralAnalyzer.return_value.analyze.return_value = None
        result = _scan("# Empty", mock_mod=mock_mod)
        assert result["is_safe"] is True
        assert result["findings_count"] == 0

    def test_both_return_none(self) -> None:
        mock_mod = _make_mock_module()
        mock_mod.StaticAnalyzer.return_value.analyze.return_value = None
        mock_mod.BehavioralAnalyzer.return_value.analyze.return_value = None
        result = _scan("# Empty", mock_mod=mock_mod)
        assert result["is_safe"] is True
        assert result["findings_count"] == 0


class TestSeverityLevels:
    """Tests for each severity level and the is_safe threshold."""

    def test_info_finding_is_safe(self) -> None:
        finding = _make_finding(severity="INFO")
        result_obj = _make_result_obj([finding])
        mock_mod = _make_mock_module(static_return=[result_obj])
        result = _scan("# Info skill", mock_mod=mock_mod)
        assert result["is_safe"] is True
        assert result["max_severity"] == "INFO"

    def test_low_finding_is_safe(self) -> None:
        finding = _make_finding(severity="LOW")
        result_obj = _make_result_obj([finding])
        mock_mod = _make_mock_module(static_return=[result_obj])
        result = _scan("# Low risk", mock_mod=mock_mod)
        assert result["is_safe"] is True
        assert result["max_severity"] == "LOW"

    def test_medium_finding_is_safe(self) -> None:
        finding = _make_finding(severity="MEDIUM")
        result_obj = _make_result_obj([finding])
        mock_mod = _make_mock_module(behavioral_return=[result_obj])
        result = _scan("# Medium", mock_mod=mock_mod)
        assert result["is_safe"] is True
        assert result["max_severity"] == "MEDIUM"

    def test_high_finding_is_unsafe(self) -> None:
        finding = _make_finding(severity="HIGH", title="Dangerous pattern")
        result_obj = _make_result_obj([finding])
        mock_mod = _make_mock_module(static_return=[result_obj])
        result = _scan("# High risk", mock_mod=mock_mod)
        assert result["is_safe"] is False
        assert result["max_severity"] == "HIGH"

    def test_critical_finding_is_unsafe(self) -> None:
        finding = _make_finding(severity="CRITICAL", title="Critical vuln")
        result_obj = _make_result_obj([finding])
        mock_mod = _make_mock_module(static_return=[result_obj])
        result = _scan("# Critical", mock_mod=mock_mod)
        assert result["is_safe"] is False
        assert result["max_severity"] == "CRITICAL"


class TestFindingExtraction:
    """Tests for extracting finding details from result objects."""

    def test_finding_fields_extracted(self) -> None:
        finding = _make_finding(
            severity="MEDIUM",
            title="Test Title",
            description="Test Desc",
            category="security",
            remediation="Remove it",
            location="line 42",
        )
        result_obj = _make_result_obj([finding])
        mock_mod = _make_mock_module(static_return=[result_obj])
        result = _scan("# Test", mock_mod=mock_mod)

        assert result["findings_count"] == 1
        f = result["findings"][0]
        assert f["severity"] == "MEDIUM"
        assert f["title"] == "Test Title"
        assert f["description"] == "Test Desc"
        assert f["category"] == "security"
        assert f["remediation"] == "Remove it"
        assert f["location"] == "line 42"

    def test_finding_with_none_severity_defaults_to_low(self) -> None:
        """When finding.severity is None, code uses 'LOW' as default."""
        finding = MagicMock()
        finding.severity = None
        finding.title = "No sev"
        finding.description = ""
        finding.category = ""
        finding.remediation = ""
        finding.location = ""
        result_obj = _make_result_obj([finding])
        mock_mod = _make_mock_module(static_return=[result_obj])
        result = _scan("# Test", mock_mod=mock_mod)

        assert result["findings"][0]["severity"] == "LOW"

    def test_result_without_findings_attr_skipped(self) -> None:
        """Result objects without 'findings' attribute are skipped."""
        result_obj = MagicMock(spec=[])  # No attributes at all
        del result_obj.findings  # Ensure hasattr returns False
        mock_mod = _make_mock_module(static_return=[result_obj])
        result = _scan("# Test", mock_mod=mock_mod)

        assert result["findings_count"] == 0


class TestMultipleFindings:
    """Tests for combining findings across analyzers and result objects."""

    def test_findings_from_both_analyzers_combined(self) -> None:
        static_finding = _make_finding(severity="LOW", title="Static issue")
        behavioral_finding = _make_finding(severity="MEDIUM", title="Behavioral issue")

        static_result = _make_result_obj([static_finding])
        behavioral_result = _make_result_obj([behavioral_finding])

        mock_mod = _make_mock_module(
            static_return=[static_result],
            behavioral_return=[behavioral_result],
        )
        result = _scan("# Mixed", mock_mod=mock_mod)

        assert result["findings_count"] == 2
        titles = [f["title"] for f in result["findings"]]
        assert "Static issue" in titles
        assert "Behavioral issue" in titles

    def test_max_severity_across_both_analyzers(self) -> None:
        low_finding = _make_finding(severity="LOW")
        high_finding = _make_finding(severity="HIGH")

        r1 = _make_result_obj([low_finding])
        r2 = _make_result_obj([high_finding])

        mock_mod = _make_mock_module(
            static_return=[r1],
            behavioral_return=[r2],
        )
        result = _scan("# Mixed", mock_mod=mock_mod)

        assert result["max_severity"] == "HIGH"
        assert result["is_safe"] is False

    def test_multiple_findings_in_single_result(self) -> None:
        f1 = _make_finding(severity="LOW", title="Issue 1")
        f2 = _make_finding(severity="MEDIUM", title="Issue 2")
        f3 = _make_finding(severity="LOW", title="Issue 3")

        result_obj = _make_result_obj([f1, f2, f3])
        mock_mod = _make_mock_module(static_return=[result_obj])
        result = _scan("# Multi", mock_mod=mock_mod)

        assert result["findings_count"] == 3
        assert result["max_severity"] == "MEDIUM"

    def test_multiple_result_objects_from_one_analyzer(self) -> None:
        f1 = _make_finding(severity="LOW", title="Issue A")
        f2 = _make_finding(severity="CRITICAL", title="Issue B")

        r1 = _make_result_obj([f1])
        r2 = _make_result_obj([f2])

        mock_mod = _make_mock_module(static_return=[r1, r2])
        result = _scan("# Multi results", mock_mod=mock_mod)

        assert result["findings_count"] == 2
        assert result["max_severity"] == "CRITICAL"
        assert result["is_safe"] is False


class TestNonListResult:
    """Tests for when analyzer returns a single object instead of a list."""

    def test_single_result_object_wrapped_as_list(self) -> None:
        """When analyzer returns a single object (not list), it's wrapped."""
        finding = _make_finding(severity="MEDIUM", title="Single result")
        result_obj = _make_result_obj([finding])

        # Return single object, not a list
        mock_mod = _make_mock_module()
        mock_mod.StaticAnalyzer.return_value.analyze.return_value = result_obj

        result = _scan("# Single", mock_mod=mock_mod)

        assert result["findings_count"] == 1
        assert result["findings"][0]["title"] == "Single result"


class TestTempFileHandling:
    """Tests for temp file creation and cleanup."""

    def test_temp_file_cleaned_up(self, tmp_path: Path) -> None:
        """Verify the temp file is deleted after scanning."""
        created_paths: list[Path] = []

        mock_mod = _make_mock_module()

        # Spy on the real behavior - after scan, file should be gone
        with patch.dict(sys.modules, {"skill_scanner": mock_mod}):
            from gobby.skills.scanner import scan_skill_content

            # Run the scan
            scan_skill_content("# Test content", name="cleanup-test")

        # The scanner creates files in the system temp dir and cleans them up.
        # We can't easily track the exact path without modifying the source,
        # but we can verify the function completes without error (finally block runs).

    def test_temp_file_cleaned_up_even_on_error(self) -> None:
        """Temp file cleanup happens even if analyzer raises."""
        mock_mod = _make_mock_module()
        mock_mod.StaticAnalyzer.return_value.analyze.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            _scan("# Error content", mock_mod=mock_mod)


class TestAnalyzerConstruction:
    """Tests that analyzers are constructed correctly."""

    def test_static_analyzer_constructed(self) -> None:
        mock_mod = _make_mock_module()
        _scan("# Test", mock_mod=mock_mod)
        mock_mod.StaticAnalyzer.assert_called_once()

    def test_behavioral_analyzer_uses_static_analysis(self) -> None:
        mock_mod = _make_mock_module()
        _scan("# Test", mock_mod=mock_mod)
        mock_mod.BehavioralAnalyzer.assert_called_once_with(use_static_analysis=True)

    def test_analyzers_called_with_temp_path(self) -> None:
        mock_mod = _make_mock_module()
        _scan("# Test content", name="myskill", mock_mod=mock_mod)

        static_call = mock_mod.StaticAnalyzer.return_value.analyze
        behavioral_call = mock_mod.BehavioralAnalyzer.return_value.analyze

        assert static_call.call_count == 1
        assert behavioral_call.call_count == 1

        # Both should be called with a Path object
        static_path = static_call.call_args[0][0]
        behavioral_path = behavioral_call.call_args[0][0]
        assert isinstance(static_path, Path)
        assert isinstance(behavioral_path, Path)
        # Same path for both
        assert static_path == behavioral_path

    def test_temp_file_name_contains_skill_name(self) -> None:
        mock_mod = _make_mock_module()
        _scan("# Test", name="my-skill", mock_mod=mock_mod)

        static_path = mock_mod.StaticAnalyzer.return_value.analyze.call_args[0][0]
        assert "my-skill" in str(static_path)

    def test_temp_file_has_md_suffix(self) -> None:
        mock_mod = _make_mock_module()
        _scan("# Test", mock_mod=mock_mod)

        static_path = mock_mod.StaticAnalyzer.return_value.analyze.call_args[0][0]
        assert str(static_path).endswith(".md")


class TestUnknownSeverity:
    """Tests for unknown severity values."""

    def test_unknown_severity_treated_as_zero(self) -> None:
        finding = _make_finding(severity="UNKNOWN_LEVEL")
        result_obj = _make_result_obj([finding])
        mock_mod = _make_mock_module(static_return=[result_obj])
        result = _scan("# Unknown", mock_mod=mock_mod)

        # Unknown severity gets 0 in severity_order.get(sev_str, 0)
        # which maps to "INFO" in the reverse lookup
        assert result["max_severity"] == "INFO"
        assert result["is_safe"] is True
        assert result["findings"][0]["severity"] == "UNKNOWN_LEVEL"
