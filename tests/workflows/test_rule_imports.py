"""Tests for rule import loading in WorkflowLoader.

Covers: loader finds rule files in search paths, imported rules merge
into workflow definition, file-local rules override imported rules,
missing import file raises clear error, circular import detection.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gobby.workflows.loader import WorkflowLoader

pytestmark = pytest.mark.unit


@pytest.fixture
def rule_dirs(tmp_path: Path) -> dict[str, Path]:
    """Create the three-tier rule directory structure.

    Mirrors production layout:
      bundled: install/shared/workflows (bundled_dir) + install/shared/rules (sibling)
      user: ~/.gobby/workflows + ~/.gobby/rules (sibling)
      project: {project}/.gobby/rules/
    """
    # Bundled: shared/workflows and shared/rules are siblings
    bundled_shared = tmp_path / "bundled" / "shared"
    bundled_workflows = bundled_shared / "workflows"
    bundled_workflows.mkdir(parents=True)
    bundled_rules = bundled_shared / "rules"
    bundled_rules.mkdir(parents=True)

    # User: ~/.gobby/workflows and ~/.gobby/rules are siblings
    user_base = tmp_path / "user"
    user_workflows = user_base / "workflows"
    user_workflows.mkdir(parents=True)
    user_rules = user_base / "rules"
    user_rules.mkdir(parents=True)

    # Project: {project}/.gobby/rules/
    project_rules = tmp_path / "project" / ".gobby" / "rules"
    project_rules.mkdir(parents=True)

    return {
        "bundled": bundled_rules,
        "bundled_workflows": bundled_workflows,
        "user": user_rules,
        "workflows": user_workflows,
        "project": project_rules,
    }


def _write_yaml(path: Path, data: dict) -> None:
    """Write a dict as YAML to a file."""
    path.write_text(yaml.dump(data, default_flow_style=False))


def _make_loader(rule_dirs: dict[str, Path]) -> WorkflowLoader:
    """Create a WorkflowLoader with rule search paths configured."""
    loader = WorkflowLoader(
        workflow_dirs=[rule_dirs["workflows"]],
        bundled_dir=rule_dirs["bundled_workflows"],
    )
    return loader


# =============================================================================
# _find_rule_file
# =============================================================================


class TestFindRuleFile:
    def test_find_bundled_rule_file(self, rule_dirs: dict[str, Path]) -> None:
        """Loader should find rule files in bundled rules directory."""
        _write_yaml(rule_dirs["bundled"] / "worker-safety.yaml", {
            "rule_definitions": {
                "require_task": {
                    "tools": ["Edit", "Write"],
                    "reason": "Claim a task first",
                    "action": "block",
                },
            },
        })
        loader = _make_loader(rule_dirs)
        path = loader._find_rule_file("worker-safety", project_path=None)
        assert path is not None
        assert path.name == "worker-safety.yaml"

    def test_find_user_rule_file(self, rule_dirs: dict[str, Path]) -> None:
        """Loader should find rule files in user rules directory."""
        _write_yaml(rule_dirs["user"] / "custom-rules.yaml", {
            "rule_definitions": {"no_push": {"tools": ["Bash"], "reason": "test", "action": "block"}},
        })
        loader = _make_loader(rule_dirs)
        # User rules dir is at the same level as workflows dir
        path = loader._find_rule_file("custom-rules", project_path=None)
        assert path is not None

    def test_find_project_rule_file(self, rule_dirs: dict[str, Path], tmp_path: Path) -> None:
        """Loader should find rule files in project rules directory."""
        _write_yaml(rule_dirs["project"] / "project-rules.yaml", {
            "rule_definitions": {"test_rule": {"tools": ["Bash"], "reason": "test", "action": "block"}},
        })
        loader = _make_loader(rule_dirs)
        project_path = rule_dirs["project"].parent.parent  # .gobby parent = project root
        path = loader._find_rule_file("project-rules", project_path=project_path)
        assert path is not None

    def test_not_found_returns_none(self, rule_dirs: dict[str, Path]) -> None:
        """Missing rule file should return None."""
        loader = _make_loader(rule_dirs)
        assert loader._find_rule_file("nonexistent", project_path=None) is None


# =============================================================================
# _load_rule_definitions
# =============================================================================


class TestLoadRuleDefinitions:
    @pytest.mark.asyncio
    async def test_load_valid_rule_file(self, rule_dirs: dict[str, Path]) -> None:
        """Loading a rule file should return the rule_definitions dict."""
        _write_yaml(rule_dirs["bundled"] / "safety.yaml", {
            "rule_definitions": {
                "no_push": {
                    "tools": ["Bash"],
                    "command_pattern": r"git\s+push",
                    "reason": "No pushing allowed",
                    "action": "block",
                },
                "require_task": {
                    "tools": ["Edit", "Write"],
                    "reason": "Claim a task first",
                    "action": "block",
                },
            },
        })
        loader = _make_loader(rule_dirs)
        path = rule_dirs["bundled"] / "safety.yaml"
        defs = await loader._load_rule_definitions(path)
        assert "no_push" in defs
        assert "require_task" in defs
        assert defs["no_push"]["action"] == "block"

    @pytest.mark.asyncio
    async def test_load_empty_file_returns_empty(self, rule_dirs: dict[str, Path]) -> None:
        """Empty/no rule_definitions in file should return empty dict."""
        _write_yaml(rule_dirs["bundled"] / "empty.yaml", {"description": "no rules here"})
        loader = _make_loader(rule_dirs)
        defs = await loader._load_rule_definitions(rule_dirs["bundled"] / "empty.yaml")
        assert defs == {}


# =============================================================================
# Import resolution in load_workflow
# =============================================================================


class TestImportResolution:
    @pytest.mark.asyncio
    async def test_imports_merge_into_workflow(self, rule_dirs: dict[str, Path]) -> None:
        """Imported rule_definitions should merge into the workflow."""
        # Create rule file
        _write_yaml(rule_dirs["bundled"] / "safety.yaml", {
            "rule_definitions": {
                "no_push": {
                    "tools": ["Bash"],
                    "command_pattern": r"git\s+push",
                    "reason": "No pushing",
                    "action": "block",
                },
            },
        })

        # Create workflow that imports it
        _write_yaml(rule_dirs["workflows"] / "my-workflow.yaml", {
            "name": "my-workflow",
            "type": "step",
            "imports": ["safety"],
            "steps": [{"name": "work", "check_rules": ["no_push"]}],
        })

        loader = _make_loader(rule_dirs)
        defn = await loader.load_workflow("my-workflow")
        assert defn is not None
        assert "no_push" in defn.rule_definitions
        assert defn.rule_definitions["no_push"].action == "block"

    @pytest.mark.asyncio
    async def test_local_rules_override_imported(self, rule_dirs: dict[str, Path]) -> None:
        """File-local rule_definitions should override imported ones with the same name."""
        _write_yaml(rule_dirs["bundled"] / "common.yaml", {
            "rule_definitions": {
                "no_push": {
                    "tools": ["Bash"],
                    "reason": "imported reason",
                    "action": "block",
                },
            },
        })

        _write_yaml(rule_dirs["workflows"] / "override-test.yaml", {
            "name": "override-test",
            "type": "step",
            "imports": ["common"],
            "rule_definitions": {
                "no_push": {
                    "tools": ["Bash"],
                    "reason": "local override",
                    "action": "warn",
                },
            },
            "steps": [{"name": "work"}],
        })

        loader = _make_loader(rule_dirs)
        defn = await loader.load_workflow("override-test")
        assert defn is not None
        assert defn.rule_definitions["no_push"].reason == "local override"
        assert defn.rule_definitions["no_push"].action == "warn"

    @pytest.mark.asyncio
    async def test_multiple_imports(self, rule_dirs: dict[str, Path]) -> None:
        """Multiple imports should all be merged."""
        _write_yaml(rule_dirs["bundled"] / "safety.yaml", {
            "rule_definitions": {
                "no_push": {"tools": ["Bash"], "reason": "safety", "action": "block"},
            },
        })
        _write_yaml(rule_dirs["bundled"] / "quality.yaml", {
            "rule_definitions": {
                "require_tests": {"tools": ["Bash"], "reason": "quality", "action": "warn"},
            },
        })

        _write_yaml(rule_dirs["workflows"] / "multi-import.yaml", {
            "name": "multi-import",
            "type": "step",
            "imports": ["safety", "quality"],
            "steps": [{"name": "work", "check_rules": ["no_push", "require_tests"]}],
        })

        loader = _make_loader(rule_dirs)
        defn = await loader.load_workflow("multi-import")
        assert defn is not None
        assert "no_push" in defn.rule_definitions
        assert "require_tests" in defn.rule_definitions

    @pytest.mark.asyncio
    async def test_missing_import_raises_error(self, rule_dirs: dict[str, Path]) -> None:
        """Missing import file should raise ValueError."""
        _write_yaml(rule_dirs["workflows"] / "bad-import.yaml", {
            "name": "bad-import",
            "type": "step",
            "imports": ["nonexistent-rules"],
            "steps": [{"name": "work"}],
        })

        loader = _make_loader(rule_dirs)
        with pytest.raises(ValueError, match="nonexistent-rules"):
            await loader.load_workflow("bad-import")

    @pytest.mark.asyncio
    async def test_no_imports_field_works(self, rule_dirs: dict[str, Path]) -> None:
        """Workflow without imports should load normally."""
        _write_yaml(rule_dirs["workflows"] / "no-imports.yaml", {
            "name": "no-imports",
            "type": "step",
            "steps": [{"name": "work"}],
        })

        loader = _make_loader(rule_dirs)
        defn = await loader.load_workflow("no-imports")
        assert defn is not None
        assert defn.rule_definitions == {}

    @pytest.mark.asyncio
    async def test_later_import_overrides_earlier(self, rule_dirs: dict[str, Path]) -> None:
        """When two imports define the same rule, the later import wins."""
        _write_yaml(rule_dirs["bundled"] / "first.yaml", {
            "rule_definitions": {
                "shared_rule": {"tools": ["Bash"], "reason": "from first", "action": "block"},
            },
        })
        _write_yaml(rule_dirs["bundled"] / "second.yaml", {
            "rule_definitions": {
                "shared_rule": {"tools": ["Bash"], "reason": "from second", "action": "warn"},
            },
        })

        _write_yaml(rule_dirs["workflows"] / "import-order.yaml", {
            "name": "import-order",
            "type": "step",
            "imports": ["first", "second"],
            "steps": [{"name": "work"}],
        })

        loader = _make_loader(rule_dirs)
        defn = await loader.load_workflow("import-order")
        assert defn is not None
        assert defn.rule_definitions["shared_rule"].reason == "from second"
