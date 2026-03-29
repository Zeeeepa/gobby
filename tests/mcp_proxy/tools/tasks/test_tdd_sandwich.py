"""Tests for TDD sandwich pattern in task expansion."""

from gobby.mcp_proxy.tools.tasks._expansion import (
    _apply_tdd_sandwich,
    _extract_phase_number,
)


class TestExtractPhaseNumber:
    def test_extracts_phase_from_plan_section(self) -> None:
        subtask = {"description": "## TDD: Do thing\n\n### Plan Section: 3.2\n\nDetails..."}
        assert _extract_phase_number(subtask) == 3

    def test_extracts_single_digit_phase(self) -> None:
        subtask = {"description": "### Plan Section: 1.1\n\nStuff"}
        assert _extract_phase_number(subtask) == 1

    def test_returns_none_for_no_plan_section(self) -> None:
        subtask = {"description": "Just a plain description"}
        assert _extract_phase_number(subtask) is None

    def test_returns_none_for_empty_description(self) -> None:
        subtask = {"description": ""}
        assert _extract_phase_number(subtask) is None

    def test_returns_none_for_missing_description(self) -> None:
        subtask = {}
        assert _extract_phase_number(subtask) is None


class TestApplyTddSandwich:
    """Test the TDD sandwich transformation."""

    def _make_subtask(
        self,
        title: str,
        phase: int,
        category: str = "code",
        depends_on: list[int] | None = None,
        priority: int = 2,
    ) -> dict:
        return {
            "title": title,
            "category": category,
            "description": f"### Plan Section: {phase}.1\n\nDo {title}",
            "validation": f"{title} works",
            "priority": priority,
            "depends_on": depends_on or [],
        }

    def test_single_phase_gets_test_and_ref(self) -> None:
        """A single phase with code tasks gets wrapped with TEST and REF."""
        subtasks = [
            self._make_subtask("Task A", phase=1),
            self._make_subtask("Task B", phase=1, depends_on=[0]),
        ]

        result = _apply_tdd_sandwich(subtasks)

        assert len(result) == 4  # TEST + 2 IMPL + REF
        assert result[0]["title"] == "[TEST] Phase 1: Write failing tests"
        assert result[0]["category"] == "test"
        assert result[1]["title"] == "Task A"
        assert result[2]["title"] == "Task B"
        assert result[3]["title"] == "[REF] Phase 1: Refactor with green tests"
        assert result[3]["category"] == "refactor"

    def test_impl_tasks_depend_on_test(self) -> None:
        """IMPL tasks should depend on their phase's TEST task."""
        subtasks = [
            self._make_subtask("Task A", phase=1),
            self._make_subtask("Task B", phase=1),
        ]

        result = _apply_tdd_sandwich(subtasks)

        # Both IMPLs (index 1, 2) depend on TEST (index 0)
        assert 0 in result[1]["depends_on"]
        assert 0 in result[2]["depends_on"]

    def test_ref_depends_on_all_impls(self) -> None:
        """REF task should depend on all IMPL tasks in the phase."""
        subtasks = [
            self._make_subtask("Task A", phase=1),
            self._make_subtask("Task B", phase=1),
            self._make_subtask("Task C", phase=1),
        ]

        result = _apply_tdd_sandwich(subtasks)

        # REF is last (index 4), depends on IMPLs (indices 1, 2, 3)
        ref = result[4]
        assert ref["title"].startswith("[REF]")
        assert set(ref["depends_on"]) == {1, 2, 3}

    def test_intra_phase_deps_preserved(self) -> None:
        """Dependencies between tasks within the same phase are preserved."""
        subtasks = [
            self._make_subtask("Task A", phase=1),
            self._make_subtask("Task B", phase=1, depends_on=[0]),
        ]

        result = _apply_tdd_sandwich(subtasks)

        # Task B (index 2) depends on TEST (0) AND Task A (1)
        assert set(result[2]["depends_on"]) == {0, 1}

    def test_multi_phase_chaining(self) -> None:
        """Phase N+1's TEST depends on Phase N's REF."""
        subtasks = [
            self._make_subtask("P1 Task", phase=1),
            self._make_subtask("P2 Task", phase=2, depends_on=[0]),
        ]

        result = _apply_tdd_sandwich(subtasks)

        # Phase 1: TEST(0), IMPL(1), REF(2)
        # Phase 2: TEST(3), IMPL(4), REF(5)
        assert len(result) == 6

        assert result[0]["title"] == "[TEST] Phase 1: Write failing tests"
        assert result[2]["title"] == "[REF] Phase 1: Refactor with green tests"
        assert result[3]["title"] == "[TEST] Phase 2: Write failing tests"
        assert result[5]["title"] == "[REF] Phase 2: Refactor with green tests"

        # Phase 2 TEST depends on Phase 1 REF
        assert 2 in result[3]["depends_on"]

    def test_non_tdd_category_skips_sandwich(self) -> None:
        """Docs/research phases don't get TEST/REF wrappers."""
        subtasks = [
            self._make_subtask("Write docs", phase=1, category="docs"),
        ]

        result = _apply_tdd_sandwich(subtasks)

        assert len(result) == 1  # No wrapping
        assert result[0]["title"] == "Write docs"

    def test_mixed_phase_with_tdd_and_non_tdd(self) -> None:
        """A TDD phase followed by a non-TDD phase."""
        subtasks = [
            self._make_subtask("Implement feature", phase=1, category="code"),
            self._make_subtask("Write user guide", phase=2, category="docs", depends_on=[0]),
        ]

        result = _apply_tdd_sandwich(subtasks)

        # Phase 1: TEST(0), IMPL(1), REF(2)
        # Phase 2: docs task(3) — no wrapping
        assert len(result) == 4
        assert result[0]["title"].startswith("[TEST]")
        assert result[2]["title"].startswith("[REF]")
        assert result[3]["title"] == "Write user guide"

    def test_config_category_gets_tdd(self) -> None:
        """Config tasks are TDD-eligible too."""
        subtasks = [
            self._make_subtask("Update config schema", phase=1, category="config"),
        ]

        result = _apply_tdd_sandwich(subtasks)

        assert len(result) == 3  # TEST + IMPL + REF

    def test_no_plan_sections_treats_as_single_phase(self) -> None:
        """Subtasks without plan sections are grouped as one phase."""
        subtasks = [
            {"title": "Task A", "category": "code", "description": "Do A", "depends_on": []},
            {"title": "Task B", "category": "code", "description": "Do B", "depends_on": [0]},
        ]

        result = _apply_tdd_sandwich(subtasks)

        assert len(result) == 4  # TEST + 2 IMPL + REF
        assert result[0]["title"] == "[TEST] Phase 1: Write failing tests"

    def test_test_description_lists_impl_titles(self) -> None:
        """The TEST task description should list all IMPL task titles."""
        subtasks = [
            self._make_subtask("Add user model", phase=1),
            self._make_subtask("Add auth endpoint", phase=1),
        ]

        result = _apply_tdd_sandwich(subtasks)

        test_desc = result[0]["description"]
        assert "Add user model" in test_desc
        assert "Add auth endpoint" in test_desc

    def test_priority_inherited_from_first_task(self) -> None:
        """TEST and REF inherit priority from first task in phase."""
        subtasks = [
            self._make_subtask("High pri task", phase=1, priority=1),
            self._make_subtask("Low pri task", phase=1, priority=3),
        ]

        result = _apply_tdd_sandwich(subtasks)

        assert result[0]["priority"] == 1  # TEST
        assert result[3]["priority"] == 1  # REF

    def test_realistic_multi_phase_expansion(self) -> None:
        """Realistic scenario matching the comm-integrations plan structure."""
        subtasks = [
            # Phase 1: Backend fixes (3 code tasks)
            self._make_subtask("Rename web_chat", phase=1, priority=1),
            self._make_subtask("Fix secrets", phase=1, priority=1, depends_on=[0]),
            self._make_subtask("CLI prompts", phase=1, priority=1, depends_on=[1]),
            # Phase 2: Data layer (1 code task)
            self._make_subtask("useIntegrations hook", phase=2, priority=2, depends_on=[2]),
            # Phase 3: Page shell (1 code task)
            self._make_subtask("IntegrationsPage", phase=3, priority=2, depends_on=[3]),
            # Phase 6: Docs (non-TDD)
            self._make_subtask("User guide", phase=6, category="docs", depends_on=[4]),
        ]

        result = _apply_tdd_sandwich(subtasks)

        # Phase 1: TEST + 3 IMPL + REF = 5
        # Phase 2: TEST + 1 IMPL + REF = 3
        # Phase 3: TEST + 1 IMPL + REF = 3
        # Phase 6: 1 docs task = 1
        # Total = 12
        assert len(result) == 12

        # Verify structure
        titles = [r["title"] for r in result]
        assert titles[0] == "[TEST] Phase 1: Write failing tests"
        assert titles[4] == "[REF] Phase 1: Refactor with green tests"
        assert titles[5] == "[TEST] Phase 2: Write failing tests"
        assert titles[7] == "[REF] Phase 2: Refactor with green tests"
        assert titles[8] == "[TEST] Phase 3: Write failing tests"
        assert titles[10] == "[REF] Phase 3: Refactor with green tests"
        assert titles[11] == "User guide"

        # Phase 2 TEST depends on Phase 1 REF (index 4)
        assert 4 in result[5]["depends_on"]
        # Phase 3 TEST depends on Phase 2 REF (index 7)
        assert 7 in result[8]["depends_on"]
