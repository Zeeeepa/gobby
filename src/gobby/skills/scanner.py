"""Safety scanner wrapper for Cisco skill-scanner.

Thin wrapper around the skill-scanner package that provides
StaticAnalyzer + BehavioralAnalyzer scanning (no API key needed).
"""

import logging
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def scan_skill_content(content: str, name: str = "untitled") -> dict[str, Any]:
    """Scan skill content for safety issues.

    Uses Cisco's skill-scanner package (StaticAnalyzer + BehavioralAnalyzer).
    No API key required.

    Args:
        content: Skill markdown content to scan
        name: Skill name for reporting

    Returns:
        Dict with scan results:
        - is_safe: bool
        - max_severity: str
        - scan_duration_seconds: float
        - findings: list of finding dicts

    Raises:
        ImportError: If skill-scanner is not installed
    """
    from skill_scanner import BehavioralAnalyzer, StaticAnalyzer

    start = time.monotonic()

    # Scanner expects a file path, so write to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", prefix=f"skill-{name}-", delete=False
    ) as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        static = StaticAnalyzer()
        behavioral = BehavioralAnalyzer(use_static_analysis=True)

        static_results = static.analyze(temp_path)
        behavioral_results = behavioral.analyze(temp_path)

        # Combine findings
        findings: list[dict[str, Any]] = []
        severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
        max_severity_num = 0

        for result_set in [static_results, behavioral_results]:
            if not result_set:
                continue
            items = result_set if isinstance(result_set, list) else [result_set]
            for item in items:
                if hasattr(item, "findings"):
                    for finding in item.findings:
                        sev = getattr(finding, "severity", "LOW")
                        sev_str = str(sev).upper() if sev else "LOW"
                        findings.append(
                            {
                                "severity": sev_str,
                                "title": getattr(finding, "title", "Unknown"),
                                "description": getattr(finding, "description", ""),
                                "category": getattr(finding, "category", ""),
                                "remediation": getattr(finding, "remediation", ""),
                                "location": getattr(finding, "location", ""),
                            }
                        )
                        max_severity_num = max(max_severity_num, severity_order.get(sev_str, 0))

        # Determine max severity string
        severity_names = {v: k for k, v in severity_order.items()}
        max_severity = severity_names.get(max_severity_num, "INFO")

        duration = time.monotonic() - start

        return {
            "is_safe": max_severity_num < severity_order["HIGH"],
            "max_severity": max_severity,
            "scan_duration_seconds": round(duration, 3),
            "findings": findings,
            "findings_count": len(findings),
        }
    finally:
        temp_path.unlink(missing_ok=True)
