"""Pipeline execution review — pure Python data gathering and prompt formatting.

Gathers structured review data from completed pipeline executions, formats
prompts for LLM analysis, and detects patterns across executions. No LLM
dependency — the conductor manager handles LLM interaction.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from gobby.workflows.pipeline_state import PipelineExecution, StepExecution

logger = logging.getLogger(__name__)


@dataclass
class StepTimeline:
    """Timeline entry for a single pipeline step."""

    step_id: str
    status: str
    duration_seconds: float | None
    error: str | None


@dataclass
class ExecutionReviewData:
    """Structured review data for a pipeline execution."""

    execution_id: str
    pipeline_name: str
    status: str
    total_duration_seconds: float | None
    steps: list[StepTimeline]
    errors: list[dict[str, str]]


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO timestamp string, returning None on failure."""
    if not ts:
        return None
    try:
        # Handle both with and without timezone
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _compute_duration(start: str | None, end: str | None) -> float | None:
    """Compute duration in seconds between two ISO timestamps."""
    start_dt = _parse_iso(start)
    end_dt = _parse_iso(end)
    if start_dt and end_dt:
        return (end_dt - start_dt).total_seconds()
    return None


def gather_review_data(
    execution: PipelineExecution,
    steps: list[StepExecution],
) -> ExecutionReviewData:
    """Build structured review data from an execution and its steps.

    Pure Python — no LLM calls. Computes durations, extracts errors,
    and builds a timeline suitable for LLM analysis or standalone storage.
    """
    step_timelines: list[StepTimeline] = []
    errors: list[dict[str, str]] = []

    for step in steps:
        duration = _compute_duration(step.started_at, step.completed_at)
        step_timelines.append(
            StepTimeline(
                step_id=step.step_id,
                status=step.status.value,
                duration_seconds=round(duration, 1) if duration is not None else None,
                error=step.error,
            )
        )
        if step.error:
            errors.append({"step_id": step.step_id, "error": step.error})

    total_duration = _compute_duration(execution.created_at, execution.completed_at)

    return ExecutionReviewData(
        execution_id=execution.id,
        pipeline_name=execution.pipeline_name,
        status=execution.status.value,
        total_duration_seconds=round(total_duration, 1) if total_duration is not None else None,
        steps=step_timelines,
        errors=errors,
    )


def format_review_prompt(data: ExecutionReviewData) -> str:
    """Format review data into a concise prompt for LLM analysis.

    Produces a compact text representation with specific analysis questions.
    Requests structured JSON response from the LLM.
    """
    step_count = len(data.steps)
    failed_count = sum(1 for s in data.steps if s.status == "failed")
    skipped_count = sum(1 for s in data.steps if s.status == "skipped")

    lines = [
        f'Pipeline "{data.pipeline_name}" {data.status}',
    ]
    if data.total_duration_seconds is not None:
        lines[0] += f" in {data.total_duration_seconds:.0f}s"
    lines[0] += f" ({step_count} steps"
    if failed_count:
        lines[0] += f", {failed_count} failed"
    if skipped_count:
        lines[0] += f", {skipped_count} skipped"
    lines[0] += ")."

    lines.append("")
    lines.append("Timeline:")
    for i, step in enumerate(data.steps, 1):
        duration_str = f"{step.duration_seconds:.0f}s" if step.duration_seconds is not None else "n/a"
        entry = f"  {i}. {step.step_id} ({duration_str}, {step.status})"
        if step.error:
            # Truncate long errors for prompt efficiency
            error_preview = step.error[:200]
            if len(step.error) > 200:
                error_preview += "..."
            entry += f' — error: "{error_preview}"'
        lines.append(entry)

    lines.append("")
    lines.append("Analyze this execution and respond with JSON (no markdown):")
    lines.append('{')
    lines.append('  "quality_signals": [{"signal": "...", "detail": "..."}],')
    lines.append('  "suggestions": ["actionable improvement suggestion"],')
    lines.append('  "summary": "one-sentence execution summary"')
    lines.append('}')
    lines.append("")
    lines.append("Consider: step duration outliers, errors indicating prompt/agent issues vs legitimate failures, unnecessary steps, missing tool restrictions.")

    return "\n".join(lines)


def build_review_json(
    data: ExecutionReviewData,
    llm_analysis: dict[str, object] | None = None,
) -> str:
    """Combine structured data and optional LLM analysis into final review JSON.

    Always includes the deterministic timeline and error summary. LLM-derived
    fields (quality_signals, suggestions, summary) are included when available.
    """
    review: dict[str, object] = {
        "reviewed_at": datetime.now(UTC).isoformat(),
        "timeline": [asdict(s) for s in data.steps],
        "total_duration_seconds": data.total_duration_seconds,
        "error_summary": data.errors,
    }

    if llm_analysis:
        review["quality_signals"] = llm_analysis.get("quality_signals", [])
        review["suggestions"] = llm_analysis.get("suggestions", [])
        review["summary"] = llm_analysis.get("summary", "")
    else:
        review["quality_signals"] = []
        review["suggestions"] = []
        review["summary"] = ""

    return json.dumps(review, default=str)


def detect_patterns(recent_reviews: list[dict[str, object]]) -> list[dict[str, str]]:
    """Detect recurring patterns across recent pipeline reviews.

    Analyzes timelines and errors from multiple reviews to find:
    - Steps that are consistently slow
    - Steps that fail frequently
    - Common error messages

    Args:
        recent_reviews: List of parsed review JSON dicts

    Returns:
        List of pattern dicts with 'type' and 'detail' keys
    """
    if len(recent_reviews) < 2:
        return []

    patterns: list[dict[str, str]] = []

    # Track step durations and failure counts
    step_durations: dict[str, list[float]] = {}
    step_failures: dict[str, int] = {}
    total_executions = len(recent_reviews)

    for review in recent_reviews:
        timeline = review.get("timeline", [])
        if not isinstance(timeline, list):
            continue
        for step in timeline:
            if not isinstance(step, dict):
                continue
            step_id = step.get("step_id", "")
            if not step_id:
                continue

            duration = step.get("duration_seconds")
            if isinstance(duration, int | float) and duration > 0:
                step_durations.setdefault(step_id, []).append(duration)

            if step.get("status") == "failed":
                step_failures[step_id] = step_failures.get(step_id, 0) + 1

    # Detect consistently slow steps (median > 60s across 3+ runs)
    for step_id, durations in step_durations.items():
        if len(durations) >= 3:
            sorted_d = sorted(durations)
            median = sorted_d[len(sorted_d) // 2]
            if median > 60:
                patterns.append({
                    "type": "recurring_slow_step",
                    "detail": (
                        f"Step '{step_id}' median {median:.0f}s "
                        f"across {len(durations)} runs"
                    ),
                })

    # Detect frequently failing steps (>= 30% failure rate)
    for step_id, fail_count in step_failures.items():
        rate = fail_count / total_executions
        if rate >= 0.3 and fail_count >= 2:
            patterns.append({
                "type": "common_failure",
                "detail": (
                    f"Step '{step_id}' fails in {fail_count}/{total_executions} "
                    f"runs ({rate:.0%})"
                ),
            })

    return patterns
