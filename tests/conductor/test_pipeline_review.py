"""Tests for pipeline review data gathering and prompt formatting."""

from __future__ import annotations

import json

import pytest

from gobby.conductor.pipeline_review import (
    ExecutionReviewData,
    StepTimeline,
    build_review_json,
    detect_patterns,
    format_review_prompt,
    gather_review_data,
)
from gobby.workflows.pipeline_state import (
    ExecutionStatus,
    PipelineExecution,
    StepExecution,
    StepStatus,
)

pytestmark = pytest.mark.unit


def _make_execution(
    execution_id: str = "pe-abc123",
    pipeline_name: str = "test-pipeline",
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    created_at: str = "2026-03-22T10:00:00+00:00",
    completed_at: str = "2026-03-22T10:02:25+00:00",
) -> PipelineExecution:
    return PipelineExecution(
        id=execution_id,
        pipeline_name=pipeline_name,
        project_id="test-project",
        status=status,
        created_at=created_at,
        updated_at=completed_at or created_at,
        completed_at=completed_at,
    )


def _make_step(
    step_id: str,
    status: StepStatus = StepStatus.COMPLETED,
    started_at: str = "2026-03-22T10:00:00+00:00",
    completed_at: str = "2026-03-22T10:00:10+00:00",
    error: str | None = None,
) -> StepExecution:
    return StepExecution(
        id=1,
        execution_id="pe-abc123",
        step_id=step_id,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        error=error,
    )


class TestGatherReviewData:
    """Tests for gather_review_data."""

    def test_basic_completed_execution(self) -> None:
        execution = _make_execution()
        steps = [
            _make_step("build", completed_at="2026-03-22T10:00:12+00:00"),
            _make_step(
                "test",
                started_at="2026-03-22T10:00:12+00:00",
                completed_at="2026-03-22T10:01:30+00:00",
            ),
        ]

        data = gather_review_data(execution, steps)

        assert data.execution_id == "pe-abc123"
        assert data.pipeline_name == "test-pipeline"
        assert data.status == "completed"
        assert data.total_duration_seconds == 145.0
        assert len(data.steps) == 2
        assert data.steps[0].step_id == "build"
        assert data.steps[0].duration_seconds == 12.0
        assert data.steps[1].duration_seconds == 78.0
        assert data.errors == []

    def test_execution_with_failed_step(self) -> None:
        execution = _make_execution(status=ExecutionStatus.FAILED)
        steps = [
            _make_step("build"),
            _make_step(
                "test",
                status=StepStatus.FAILED,
                started_at="2026-03-22T10:00:10+00:00",
                completed_at="2026-03-22T10:00:18+00:00",
                error="AssertionError: expected 3, got 2",
            ),
        ]

        data = gather_review_data(execution, steps)

        assert len(data.errors) == 1
        assert data.errors[0]["step_id"] == "test"
        assert "AssertionError" in data.errors[0]["error"]

    def test_execution_with_skipped_steps(self) -> None:
        execution = _make_execution(status=ExecutionStatus.FAILED)
        steps = [
            _make_step("build"),
            _make_step("test", status=StepStatus.FAILED, error="test failed"),
            _make_step("deploy", status=StepStatus.SKIPPED, started_at=None, completed_at=None),
        ]

        data = gather_review_data(execution, steps)

        assert data.steps[2].status == "skipped"
        assert data.steps[2].duration_seconds is None

    def test_no_steps(self) -> None:
        execution = _make_execution()
        data = gather_review_data(execution, [])

        assert data.steps == []
        assert data.errors == []

    def test_missing_timestamps(self) -> None:
        execution = _make_execution(completed_at=None)
        steps = [_make_step("build", started_at=None, completed_at=None)]

        data = gather_review_data(execution, steps)

        assert data.total_duration_seconds is None
        assert data.steps[0].duration_seconds is None


class TestFormatReviewPrompt:
    """Tests for format_review_prompt."""

    def test_basic_prompt_format(self) -> None:
        data = ExecutionReviewData(
            execution_id="pe-abc",
            pipeline_name="deploy",
            status="completed",
            total_duration_seconds=145.0,
            steps=[
                StepTimeline(
                    step_id="build", status="completed", duration_seconds=12.0, error=None
                ),
                StepTimeline(step_id="test", status="completed", duration_seconds=78.0, error=None),
            ],
            errors=[],
        )

        prompt = format_review_prompt(data)

        assert '"deploy" completed in 145s' in prompt
        assert "2 steps" in prompt
        assert "1. build (12s, completed)" in prompt
        assert "2. test (78s, completed)" in prompt
        assert "quality_signals" in prompt

    def test_prompt_with_failures(self) -> None:
        data = ExecutionReviewData(
            execution_id="pe-abc",
            pipeline_name="ci",
            status="failed",
            total_duration_seconds=30.0,
            steps=[
                StepTimeline(
                    step_id="lint", status="failed", duration_seconds=5.0, error="SyntaxError"
                ),
            ],
            errors=[{"step_id": "lint", "error": "SyntaxError"}],
        )

        prompt = format_review_prompt(data)

        assert "1 failed" in prompt
        assert 'error: "SyntaxError"' in prompt

    def test_prompt_truncates_long_errors(self) -> None:
        long_error = "x" * 300
        data = ExecutionReviewData(
            execution_id="pe-abc",
            pipeline_name="test",
            status="failed",
            total_duration_seconds=10.0,
            steps=[
                StepTimeline(
                    step_id="run", status="failed", duration_seconds=10.0, error=long_error
                ),
            ],
            errors=[],
        )

        prompt = format_review_prompt(data)

        assert "..." in prompt
        # Error should be truncated to ~200 chars + "..."
        assert long_error not in prompt


class TestBuildReviewJson:
    """Tests for build_review_json."""

    def test_with_llm_analysis(self) -> None:
        data = ExecutionReviewData(
            execution_id="pe-abc",
            pipeline_name="test",
            status="completed",
            total_duration_seconds=100.0,
            steps=[
                StepTimeline(
                    step_id="build", status="completed", duration_seconds=100.0, error=None
                )
            ],
            errors=[],
        )
        llm_analysis = {
            "quality_signals": [{"signal": "slow_step", "detail": "build is slow"}],
            "suggestions": ["Cache dependencies"],
            "summary": "Build step is slow",
        }

        result = json.loads(build_review_json(data, llm_analysis))

        assert result["reviewed_at"]
        assert len(result["timeline"]) == 1
        assert result["total_duration_seconds"] == 100.0
        assert result["quality_signals"][0]["signal"] == "slow_step"
        assert "Cache dependencies" in result["suggestions"]
        assert result["summary"] == "Build step is slow"

    def test_without_llm_analysis(self) -> None:
        data = ExecutionReviewData(
            execution_id="pe-abc",
            pipeline_name="test",
            status="completed",
            total_duration_seconds=50.0,
            steps=[
                StepTimeline(step_id="run", status="completed", duration_seconds=50.0, error=None)
            ],
            errors=[],
        )

        result = json.loads(build_review_json(data, None))

        assert result["timeline"][0]["step_id"] == "run"
        assert result["quality_signals"] == []
        assert result["suggestions"] == []
        assert result["summary"] == ""

    def test_with_errors(self) -> None:
        data = ExecutionReviewData(
            execution_id="pe-abc",
            pipeline_name="test",
            status="failed",
            total_duration_seconds=10.0,
            steps=[],
            errors=[{"step_id": "lint", "error": "bad syntax"}],
        )

        result = json.loads(build_review_json(data))

        assert len(result["error_summary"]) == 1
        assert result["error_summary"][0]["step_id"] == "lint"


class TestDetectPatterns:
    """Tests for detect_patterns."""

    def test_no_patterns_with_single_review(self) -> None:
        reviews = [
            {"timeline": [{"step_id": "build", "status": "completed", "duration_seconds": 100}]}
        ]
        assert detect_patterns(reviews) == []

    def test_detects_recurring_slow_step(self) -> None:
        reviews = [
            {"timeline": [{"step_id": "research", "status": "completed", "duration_seconds": 90}]},
            {"timeline": [{"step_id": "research", "status": "completed", "duration_seconds": 80}]},
            {"timeline": [{"step_id": "research", "status": "completed", "duration_seconds": 95}]},
        ]

        patterns = detect_patterns(reviews)

        assert len(patterns) == 1
        assert patterns[0]["type"] == "recurring_slow_step"
        assert "research" in patterns[0]["detail"]

    def test_no_slow_pattern_under_threshold(self) -> None:
        reviews = [
            {"timeline": [{"step_id": "build", "status": "completed", "duration_seconds": 30}]},
            {"timeline": [{"step_id": "build", "status": "completed", "duration_seconds": 25}]},
            {"timeline": [{"step_id": "build", "status": "completed", "duration_seconds": 35}]},
        ]

        assert detect_patterns(reviews) == []

    def test_detects_common_failure(self) -> None:
        reviews = [
            {"timeline": [{"step_id": "test", "status": "failed", "duration_seconds": 5}]},
            {"timeline": [{"step_id": "test", "status": "failed", "duration_seconds": 3}]},
            {"timeline": [{"step_id": "test", "status": "completed", "duration_seconds": 5}]},
        ]

        patterns = detect_patterns(reviews)

        failure_patterns = [p for p in patterns if p["type"] == "common_failure"]
        assert len(failure_patterns) == 1
        assert "test" in failure_patterns[0]["detail"]

    def test_handles_malformed_reviews(self) -> None:
        reviews = [
            {"timeline": "not a list"},
            {"no_timeline": True},
            {"timeline": [{"no_step_id": True}]},
        ]
        # Should not raise
        assert detect_patterns(reviews) == []

    def test_empty_reviews(self) -> None:
        assert detect_patterns([]) == []
