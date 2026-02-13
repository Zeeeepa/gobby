"""Tests for coordinator pipeline and developer/QA workflow YAML definitions.

Tests that YAML files load correctly, steps are properly ordered,
and workflow definitions have valid structure.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

SHARED_DIR = Path(__file__).parent.parent.parent / "src" / "gobby" / "install" / "shared"
WORKFLOWS_DIR = SHARED_DIR / "workflows"
AGENTS_DIR = SHARED_DIR / "agents"


# =============================================================================
# Coordinator pipeline tests
# =============================================================================


class TestCoordinatorPipeline:
    """Tests for coordinator.yaml pipeline definition."""

    @pytest.fixture
    def coordinator_yaml(self) -> dict:
        """Load coordinator pipeline YAML."""
        path = WORKFLOWS_DIR / "coordinator.yaml"
        assert path.exists(), f"coordinator.yaml not found at {path}"
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_loads_as_valid_yaml(self, coordinator_yaml: dict) -> None:
        """Test that coordinator.yaml loads without errors."""
        assert coordinator_yaml is not None
        assert "name" in coordinator_yaml

    def test_is_pipeline_type(self, coordinator_yaml: dict) -> None:
        """Test that coordinator is a pipeline type workflow."""
        assert coordinator_yaml.get("type") == "pipeline"

    def test_has_required_steps(self, coordinator_yaml: dict) -> None:
        """Test that coordinator has all expected orchestration steps."""
        step_ids = [s["id"] for s in coordinator_yaml["steps"]]
        expected = [
            "find_work",
            "create_clone",
            "spawn_developer",
            "wait_developer",
            "spawn_qa",
            "wait_qa",
        ]
        for expected_id in expected:
            assert expected_id in step_ids, f"Missing step: {expected_id}"

    def test_steps_use_mcp_type(self, coordinator_yaml: dict) -> None:
        """Test that orchestration steps use MCP tool calls."""
        mcp_steps = [s for s in coordinator_yaml["steps"] if "mcp" in s]
        assert len(mcp_steps) >= 6, "Expected at least 6 MCP steps"

    def test_find_work_uses_suggest_next_task(self, coordinator_yaml: dict) -> None:
        """Test that find_work step calls suggest_next_task."""
        find_work = next(s for s in coordinator_yaml["steps"] if s["id"] == "find_work")
        assert find_work["mcp"]["server"] == "gobby-tasks"
        assert find_work["mcp"]["tool"] == "suggest_next_task"

    def test_spawn_developer_uses_spawn_agent(self, coordinator_yaml: dict) -> None:
        """Test that spawn_developer step calls spawn_agent."""
        spawn_dev = next(s for s in coordinator_yaml["steps"] if s["id"] == "spawn_developer")
        assert spawn_dev["mcp"]["server"] == "gobby-agents"
        assert spawn_dev["mcp"]["tool"] == "spawn_agent"

    def test_spawn_qa_uses_spawn_agent(self, coordinator_yaml: dict) -> None:
        """Test that spawn_qa step calls spawn_agent."""
        spawn_qa = next(s for s in coordinator_yaml["steps"] if s["id"] == "spawn_qa")
        assert spawn_qa["mcp"]["server"] == "gobby-agents"
        assert spawn_qa["mcp"]["tool"] == "spawn_agent"

    def test_wait_steps_use_wait_for_agent(self, coordinator_yaml: dict) -> None:
        """Test that wait steps call wait_for_agent."""
        wait_steps = [s for s in coordinator_yaml["steps"] if s["id"].startswith("wait_")]
        assert len(wait_steps) >= 2
        for ws in wait_steps:
            assert ws["mcp"]["tool"] == "wait_for_agent"

    def test_has_inputs(self, coordinator_yaml: dict) -> None:
        """Test that coordinator defines expected inputs."""
        inputs = coordinator_yaml.get("inputs", {})
        assert "session_task" in inputs or "developer_agent" in inputs

    def test_conditional_steps_have_conditions(self, coordinator_yaml: dict) -> None:
        """Test that dependent steps have condition fields."""
        spawn_dev = next(s for s in coordinator_yaml["steps"] if s["id"] == "spawn_developer")
        assert "condition" in spawn_dev, "spawn_developer should have a condition"

    def test_loads_as_pipeline_definition(self, coordinator_yaml: dict) -> None:
        """Test that coordinator YAML can be parsed into PipelineDefinition."""
        from gobby.workflows.definitions import PipelineDefinition

        # PipelineDefinition expects list of PipelineStep dicts
        pipeline = PipelineDefinition(**coordinator_yaml)
        assert pipeline.name == "coordinator"
        assert pipeline.type == "pipeline"
        assert len(pipeline.steps) >= 6


# =============================================================================
# Developer workflow tests
# =============================================================================


class TestDeveloperWorkflow:
    """Tests for developer.yaml step workflow."""

    @pytest.fixture
    def developer_yaml(self) -> dict:
        """Load developer workflow YAML."""
        path = WORKFLOWS_DIR / "developer.yaml"
        assert path.exists(), f"developer.yaml not found at {path}"
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_loads_as_valid_yaml(self, developer_yaml: dict) -> None:
        """Test that developer.yaml loads without errors."""
        assert developer_yaml is not None

    def test_is_step_type(self, developer_yaml: dict) -> None:
        """Test that developer workflow is step type (explicit or default)."""
        # If 'type' is declared, it must be 'step'; if omitted, the parser defaults to 'step'
        wf_type = developer_yaml.get("type")
        assert wf_type is None or wf_type == "step", (
            f"Expected type to be 'step' or omitted, got '{wf_type}'"
        )

    def test_has_tdd_phases(self, developer_yaml: dict) -> None:
        """Test that developer workflow has TDD red/green/blue phases."""
        step_names = [s["name"] for s in developer_yaml["steps"]]
        assert "red" in step_names, "Missing red phase"
        assert "green" in step_names, "Missing green phase"
        assert "blue" in step_names, "Missing blue phase"

    def test_step_order(self, developer_yaml: dict) -> None:
        """Test that steps are in correct TDD order."""
        step_names = [s["name"] for s in developer_yaml["steps"]]
        # claim_task must come before red
        assert step_names.index("claim_task") < step_names.index("red")
        # red → green → blue → reflect → commit
        assert step_names.index("red") < step_names.index("green")
        assert step_names.index("green") < step_names.index("blue")
        assert step_names.index("blue") < step_names.index("reflect")
        assert step_names.index("reflect") < step_names.index("commit")

    def test_has_shutdown_step(self, developer_yaml: dict) -> None:
        """Test that workflow has shutdown step."""
        step_names = [s["name"] for s in developer_yaml["steps"]]
        assert "shutdown" in step_names

    def test_has_complete_step(self, developer_yaml: dict) -> None:
        """Test that workflow has complete step."""
        step_names = [s["name"] for s in developer_yaml["steps"]]
        assert "complete" in step_names

    def test_has_exit_condition(self, developer_yaml: dict) -> None:
        """Test that workflow defines an exit condition."""
        assert "exit_condition" in developer_yaml

    def test_has_premature_stop_handler(self, developer_yaml: dict) -> None:
        """Test that workflow blocks premature stops."""
        assert "on_premature_stop" in developer_yaml
        assert developer_yaml["on_premature_stop"]["action"] == "block"

    def test_variables_defined(self, developer_yaml: dict) -> None:
        """Test that workflow defines expected variables."""
        variables = developer_yaml.get("variables", {})
        assert "assigned_task_id" in variables
        assert "task_claimed" in variables
        assert "tests_written" in variables
        assert "tests_passing" in variables

    def test_git_push_blocked(self, developer_yaml: dict) -> None:
        """Test that git push is blocked in all relevant steps."""
        for step in developer_yaml["steps"]:
            blocked = step.get("blocked_commands", [])
            if blocked:
                patterns = [b["pattern"] for b in blocked]
                assert "git push" in patterns or "git push *" in patterns

    def test_red_phase_has_rules(self, developer_yaml: dict) -> None:
        """Test that red phase has rules for test-only editing."""
        red_step = next(s for s in developer_yaml["steps"] if s["name"] == "red")
        assert "rules" in red_step, "Red phase should have rules"

    def test_claim_task_has_on_enter(self, developer_yaml: dict) -> None:
        """Test that claim_task step has on_enter actions."""
        claim = next(s for s in developer_yaml["steps"] if s["name"] == "claim_task")
        assert len(claim.get("on_enter", [])) > 0


# =============================================================================
# QA reviewer workflow tests
# =============================================================================


class TestQAReviewerWorkflow:
    """Tests for qa-reviewer.yaml step workflow."""

    @pytest.fixture
    def qa_yaml(self) -> dict:
        """Load QA reviewer workflow YAML."""
        path = WORKFLOWS_DIR / "qa-reviewer.yaml"
        assert path.exists(), f"qa-reviewer.yaml not found at {path}"
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_loads_as_valid_yaml(self, qa_yaml: dict) -> None:
        """Test that qa-reviewer.yaml loads without errors."""
        assert qa_yaml is not None

    def test_is_step_type(self, qa_yaml: dict) -> None:
        """Test that QA workflow is step type (explicit or default)."""
        # If 'type' is declared, it must be 'step'; if omitted, the parser defaults to 'step'
        wf_type = qa_yaml.get("type")
        assert wf_type is None or wf_type == "step", (
            f"Expected type to be 'step' or omitted, got '{wf_type}'"
        )

    def test_has_review_phases(self, qa_yaml: dict) -> None:
        """Test that QA workflow has review/fix/verify/approve phases."""
        step_names = [s["name"] for s in qa_yaml["steps"]]
        assert "review" in step_names
        assert "fix" in step_names
        assert "verify" in step_names
        assert "approve" in step_names

    def test_step_order(self, qa_yaml: dict) -> None:
        """Test that steps are in correct review order."""
        step_names = [s["name"] for s in qa_yaml["steps"]]
        assert step_names.index("claim_task") < step_names.index("review")
        assert step_names.index("review") < step_names.index("approve")

    def test_review_blocks_edit_write(self, qa_yaml: dict) -> None:
        """Test that review phase blocks Edit/Write tools (read-only)."""
        review = next(s for s in qa_yaml["steps"] if s["name"] == "review")
        blocked = review.get("blocked_tools", [])
        assert "Edit" in blocked, "Review phase should block Edit"
        assert "Write" in blocked, "Review phase should block Write"

    def test_claim_with_force(self, qa_yaml: dict) -> None:
        """Test that QA claim_task uses force=true (re-claim from developer)."""
        claim = next(s for s in qa_yaml["steps"] if s["name"] == "claim_task")
        on_enter = claim.get("on_enter", [])
        # Find the call_mcp_tool action for claim_task
        claim_action = next(
            (a for a in on_enter if a.get("tool_name") == "claim_task"),
            None,
        )
        assert claim_action is not None, "Should have claim_task MCP action"
        assert claim_action.get("arguments", {}).get("force") is True

    def test_approve_step_uses_mark_task_review_approved(self, qa_yaml: dict) -> None:
        """Test that approve step uses mark_task_review_approved MCP tool."""
        approve = next(s for s in qa_yaml["steps"] if s["name"] == "approve")
        allowed_mcp = approve.get("allowed_mcp_tools", [])
        assert "gobby-tasks:mark_task_review_approved" in allowed_mcp

    def test_has_shutdown_and_complete(self, qa_yaml: dict) -> None:
        """Test that workflow has shutdown and complete steps."""
        step_names = [s["name"] for s in qa_yaml["steps"]]
        assert "shutdown" in step_names
        assert "complete" in step_names

    def test_has_exit_condition(self, qa_yaml: dict) -> None:
        """Test that workflow defines exit condition."""
        assert "exit_condition" in qa_yaml

    def test_variables_defined(self, qa_yaml: dict) -> None:
        """Test that expected variables are defined."""
        variables = qa_yaml.get("variables", {})
        assert "assigned_task_id" in variables
        assert "task_claimed" in variables
        assert "review_approved" in variables
        assert "issues_found" in variables
        assert "task_approved" in variables

    def test_git_push_blocked(self, qa_yaml: dict) -> None:
        """Test that git push is blocked."""
        for step in qa_yaml["steps"]:
            blocked = step.get("blocked_commands", [])
            if blocked:
                patterns = [b["pattern"] for b in blocked]
                assert "git push" in patterns or "git push *" in patterns


# =============================================================================
# Agent definition tests
# =============================================================================


class TestAgentDefinitions:
    """Tests for agent YAML definitions."""

    def test_coordinator_agent_exists(self) -> None:
        """Test that coordinator agent definition exists."""
        path = AGENTS_DIR / "coordinator.yaml"
        assert path.exists()

    def test_coordinator_agent_valid(self) -> None:
        """Test coordinator agent structure."""
        path = AGENTS_DIR / "coordinator.yaml"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data["name"] == "coordinator"
        assert data["provider"] == "claude"
        assert "workflows" in data
        assert "coordinator" in data["workflows"]

    def test_developer_gemini_agent_exists(self) -> None:
        """Test that developer-gemini agent definition exists."""
        path = AGENTS_DIR / "developer-gemini.yaml"
        assert path.exists()

    def test_developer_gemini_agent_valid(self) -> None:
        """Test developer-gemini agent structure."""
        path = AGENTS_DIR / "developer-gemini.yaml"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data["name"] == "developer-gemini"
        assert data["provider"] == "gemini"
        assert data["isolation"] == "clone"
        assert "workflows" in data
        assert "developer" in data["workflows"]
        assert "worker" in data["workflows"]

    def test_qa_claude_agent_exists(self) -> None:
        """Test that qa-claude agent definition exists."""
        path = AGENTS_DIR / "qa-claude.yaml"
        assert path.exists()

    def test_qa_claude_agent_valid(self) -> None:
        """Test qa-claude agent structure."""
        path = AGENTS_DIR / "qa-claude.yaml"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data["name"] == "qa-claude"
        assert data["provider"] == "claude"
        assert data["isolation"] == "clone"
        assert "workflows" in data
        assert "qa-reviewer" in data["workflows"]
        assert "worker" in data["workflows"]

    def test_developer_has_sandbox_config(self) -> None:
        """Test developer agent has sandbox configuration."""
        path = AGENTS_DIR / "developer-gemini.yaml"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "sandbox" in data
        assert data["sandbox"]["enabled"] is True

    def test_qa_has_sandbox_config(self) -> None:
        """Test QA agent has sandbox configuration."""
        path = AGENTS_DIR / "qa-claude.yaml"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "sandbox" in data
        assert data["sandbox"]["enabled"] is True

    def test_agent_timeout_and_max_turns(self) -> None:
        """Test that agents define timeout and max_turns."""
        for name in ["developer-gemini.yaml", "qa-claude.yaml"]:
            path = AGENTS_DIR / name
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            assert "timeout" in data, f"{name} missing timeout"
            assert "max_turns" in data, f"{name} missing max_turns"
            assert data["timeout"] > 0
            assert data["max_turns"] > 0
