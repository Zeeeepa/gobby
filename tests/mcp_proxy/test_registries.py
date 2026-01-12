from unittest.mock import MagicMock

from gobby.mcp_proxy.registries import setup_internal_registries


def test_setup_internal_registries_with_merge():
    merge_storage = MagicMock()
    merge_resolver = MagicMock()
    git_manager = MagicMock()
    worktree_manager = MagicMock()

    manager = setup_internal_registries(
        _config=MagicMock(),
        merge_storage=merge_storage,
        merge_resolver=merge_resolver,
        git_manager=git_manager,
        worktree_storage=worktree_manager,
    )

    registries = manager.get_all_registries()
    assert any(r.name == "gobby-merge" for r in registries)
