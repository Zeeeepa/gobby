"""Shared fixtures for workflow tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from gobby.storage.database import LocalDatabase
    from gobby.workflows.loader import WorkflowLoader


@pytest.fixture
def workflow_db(temp_db: "LocalDatabase") -> "LocalDatabase":
    """Populate temp_db with bundled workflows (and rules for imports) and return it."""
    from gobby.workflows.rule_sync import sync_bundled_rules_sync
    from gobby.workflows.sync import sync_bundled_workflows

    sync_bundled_rules_sync(temp_db)
    sync_bundled_workflows(temp_db)
    return temp_db


@pytest.fixture
def db_loader(workflow_db: "LocalDatabase") -> "WorkflowLoader":
    """Return a WorkflowLoader backed by a DB with bundled workflows."""
    from gobby.workflows.loader import WorkflowLoader

    return WorkflowLoader(db=workflow_db)
