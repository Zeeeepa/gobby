"""Safety scanner wrapper for Cisco skill-scanner.

Thin wrapper around the skill-scanner package that runs deterministic
static-rule scanning and risk scoring. No API key required.
"""

import logging
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}


def scan_skill_content(content: str, name: str = "untitled") -> dict[str, Any]:
    """Scan skill content for safety issues.

    Uses Cisco's skill-scanner deterministic static rules and risk scoring.
    No API key required.

    Args:
        content: Skill markdown content to scan
        name: Skill name for reporting

    Returns:
        Dict with scan results:
        - is_safe: bool
        - max_severity: str
        - risk_level: str
        - risk_score: float
        - scan_duration_seconds: float
        - findings: list of finding dicts
        - findings_count: int

    Raises:
        ImportError: If skill-scanner is not installed
    """
    from skill_scanner.models.reports import SkillReport
    from skill_scanner.models.targets import (
        Platform,
        ScanTarget,
        Scope,
        SkillFile,
        TargetKind,
    )
    from skill_scanner.scoring.risk import evaluate_risk
    from skill_scanner.validation.static_rules import run_static_rules

    start = time.monotonic()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", prefix=f"skill-{name}-", delete=False
    ) as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        target = ScanTarget(
            id=name,
            kind=TargetKind.SKILL,
            platform=Platform.ALL,
            scope=Scope.REPO,
            entry_path=str(temp_path),
            root_dir=str(temp_path.parent),
            files=[
                SkillFile(
                    path=str(temp_path),
                    relative_path=temp_path.name,
                    size=len(content.encode()),
                )
            ],
        )

        static_findings = run_static_rules(target)

        report = SkillReport(
            target=target,
            deterministic_findings=static_findings,
        )
        report = evaluate_risk(report)

        findings: list[dict[str, Any]] = []
        max_severity_num = 0

        for finding in static_findings:
            sev_str = finding.severity.value.upper()
            findings.append(
                {
                    "severity": sev_str,
                    "title": finding.title,
                    "description": finding.description,
                    "category": finding.category.value,
                    "remediation": finding.recommendation or "",
                    "location": f"{finding.file_path}:{finding.line}" if finding.line else "",
                }
            )
            max_severity_num = max(max_severity_num, SEVERITY_ORDER.get(sev_str, 0))

        severity_names = {v: k for k, v in SEVERITY_ORDER.items()}
        max_severity = severity_names.get(max_severity_num, "INFO")
        duration = time.monotonic() - start

        return {
            "is_safe": max_severity_num < SEVERITY_ORDER["HIGH"],
            "max_severity": max_severity,
            "risk_level": report.risk_level.value,
            "risk_score": report.score,
            "scan_duration_seconds": round(duration, 3),
            "findings": findings,
            "findings_count": len(findings),
        }
    finally:
        temp_path.unlink(missing_ok=True)
