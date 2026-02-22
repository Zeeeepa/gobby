"""Tests for developer.yaml workflow structure.

Verifies: workflow loads without error, expected steps exist.
"""

from __future__ import annotations

import pytest

from gobby.workflows.loader import WorkflowLoader

pytestmark = pytest.mark.unit


EXPECTED_STEPS = [
    "claim_task",
    "red",
    "green",
    "blue",
    "reflect",
    "commit",
    "report_to_parent",
    "shutdown",
    "complete",
]


# =============================================================================
# Basic structure
# =============================================================================


class TestDeveloperWorkflowStructure:
    @pytest.mark.asyncio
    async def test_loads_without_error(self, db_loader: WorkflowLoader) -> None:
        """developer.yaml should load successfully."""
        defn = await db_loader.load_workflow("developer")
        assert defn is not None
        assert defn.name == "developer"
        assert defn.type == "step"

    @pytest.mark.asyncio
    async def test_expected_steps_exist(self, db_loader: WorkflowLoader) -> None:
        """All expected TDD steps should be present."""
        defn = await db_loader.load_workflow("developer")
        assert defn is not None
        step_names = [s.name for s in defn.steps]
        for expected in EXPECTED_STEPS:
            assert expected in step_names, f"Missing step: {expected}"

    @pytest.mark.asyncio
    async def test_step_count(self, db_loader: WorkflowLoader) -> None:
        """Workflow should have exactly the expected number of steps."""
        defn = await db_loader.load_workflow("developer")
        assert defn is not None
        assert len(defn.steps) == len(EXPECTED_STEPS)
