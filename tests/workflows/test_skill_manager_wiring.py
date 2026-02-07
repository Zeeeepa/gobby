"""Regression tests: skill_manager must be wired in all ActionContext instantiation sites.

This module ensures that every place in the codebase that constructs an
ActionContext from an ActionExecutor passes skill_manager through. It uses
source-level inspection as a "never again" guard against future omissions.
"""

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from gobby.workflows.actions import ActionContext

pytestmark = pytest.mark.unit

# Paths to the files that construct ActionContext from ActionExecutor
SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "gobby" / "workflows"
ACTION_CONTEXT_SITES = [
    SRC_ROOT / "engine.py",
    SRC_ROOT / "lifecycle_evaluator.py",
]


class TestSkillManagerSourceInspection:
    """Inspect source files to ensure skill_manager is always passed."""

    @pytest.mark.parametrize("filepath", ACTION_CONTEXT_SITES, ids=lambda p: p.name)
    def test_action_context_calls_include_skill_manager(self, filepath: Path):
        """Every ActionContext(...) call in the file must include skill_manager."""
        source = filepath.read_text()
        tree = ast.parse(source, filename=str(filepath))

        action_context_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Match ActionContext(...) calls
                func = node.func
                if isinstance(func, ast.Name) and func.id == "ActionContext":
                    action_context_calls.append(node)

        assert action_context_calls, f"No ActionContext(...) calls found in {filepath.name}"

        for call_node in action_context_calls:
            kwarg_names = [kw.arg for kw in call_node.keywords]
            assert "skill_manager" in kwarg_names, (
                f"ActionContext(...) at {filepath.name}:{call_node.lineno} "
                f"is missing skill_manager keyword argument. "
                f"Found kwargs: {kwarg_names}"
            )


class TestSkillManagerPropagation:
    """Integration tests verifying skill_manager flows through construction."""

    @pytest.mark.asyncio
    async def test_engine_execute_actions_propagates_skill_manager(self):
        """WorkflowEngine._execute_actions passes skill_manager to ActionContext."""
        from gobby.workflows.engine import WorkflowEngine

        mock_executor = AsyncMock()
        mock_executor.db = Mock()
        mock_executor.session_manager = Mock()
        mock_executor.template_engine = Mock()
        mock_executor.llm_service = Mock()
        mock_executor.transcript_processor = Mock()
        mock_executor.config = Mock()
        mock_executor.mcp_manager = Mock()
        mock_executor.memory_manager = Mock()
        mock_executor.memory_sync_manager = Mock()
        mock_executor.task_sync_manager = Mock()
        mock_executor.session_task_manager = Mock()
        mock_executor.pipeline_executor = Mock()
        mock_executor.workflow_loader = Mock()
        mock_executor.skill_manager = Mock(name="the-skill-manager")
        mock_executor.execute = AsyncMock(return_value=None)

        engine = WorkflowEngine(
            loader=Mock(),
            state_manager=Mock(),
            action_executor=mock_executor,
        )

        state = MagicMock()
        state.session_id = "test-session"
        actions = [{"action": "inject_context", "source": "skills"}]

        await engine._execute_actions(actions, state)

        context_arg = mock_executor.execute.call_args[0][1]
        assert isinstance(context_arg, ActionContext)
        assert context_arg.skill_manager is mock_executor.skill_manager

    def test_lifecycle_evaluator_sites_have_skill_manager(self):
        """Both ActionContext sites in lifecycle_evaluator.py include skill_manager.

        This is covered by the AST inspection test above, but we include it
        as a readable regression marker.
        """
        source = (SRC_ROOT / "lifecycle_evaluator.py").read_text()

        # Count ActionContext(...) blocks and skill_manager occurrences within them
        # Simple heuristic: every "ActionContext(" should be followed by "skill_manager="
        # before the next closing ")  # end of ActionContext"
        import re

        # Find all ActionContext constructor blocks
        pattern = r"ActionContext\((.*?)\)"
        matches = re.findall(pattern, source, re.DOTALL)

        assert len(matches) >= 2, (
            f"Expected at least 2 ActionContext(...) calls in lifecycle_evaluator.py, "
            f"found {len(matches)}"
        )

        for i, match in enumerate(matches):
            assert "skill_manager=" in match, (
                f"ActionContext call #{i + 1} in lifecycle_evaluator.py "
                f"is missing skill_manager parameter"
            )
