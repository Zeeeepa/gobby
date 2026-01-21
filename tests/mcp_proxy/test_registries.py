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


def test_setup_with_config_none():
    """Test setup with config=None disables tasks registry."""
    manager = setup_internal_registries(_config=None)

    registries = manager.get_all_registries()
    # Tasks registry should NOT be present when config is None
    assert not any(r.name == "gobby-tasks" for r in registries)
    # Workflows registry is always present
    assert any(r.name == "gobby-workflows" for r in registries)


def test_setup_with_all_managers_none():
    """Test setup with all optional managers as None."""
    mock_config = MagicMock()
    mock_config.get_gobby_tasks_config.return_value.enabled = False

    manager = setup_internal_registries(
        _config=mock_config,
        memory_manager=None,
        task_manager=None,
        sync_manager=None,
        message_manager=None,
        local_session_manager=None,
        metrics_manager=None,
        agent_runner=None,
        worktree_storage=None,
        merge_storage=None,
        merge_resolver=None,
    )

    registries = manager.get_all_registries()
    # Only workflows should be present (always enabled)
    registry_names = [r.name for r in registries]
    assert "gobby-workflows" in registry_names
    # These should NOT be present when their managers are None
    assert "gobby-memory" not in registry_names
    assert "gobby-metrics" not in registry_names
    assert "gobby-agents" not in registry_names
    assert "gobby-worktrees" not in registry_names
    assert "gobby-merge" not in registry_names


def test_setup_with_memory_manager_only():
    """Test setup with only memory manager enabled."""
    mock_config = MagicMock()
    mock_config.get_gobby_tasks_config.return_value.enabled = False
    memory_manager = MagicMock()

    manager = setup_internal_registries(
        _config=mock_config,
        memory_manager=memory_manager,
    )

    registries = manager.get_all_registries()
    registry_names = [r.name for r in registries]
    assert "gobby-memory" in registry_names
    assert "gobby-workflows" in registry_names


def test_setup_with_metrics_manager_only():
    """Test setup with only metrics manager enabled."""
    mock_config = MagicMock()
    mock_config.get_gobby_tasks_config.return_value.enabled = False
    metrics_manager = MagicMock()

    manager = setup_internal_registries(
        _config=mock_config,
        metrics_manager=metrics_manager,
    )

    registries = manager.get_all_registries()
    registry_names = [r.name for r in registries]
    assert "gobby-metrics" in registry_names


def test_setup_with_agent_runner_only():
    """Test setup with only agent runner enabled."""
    mock_config = MagicMock()
    mock_config.get_gobby_tasks_config.return_value.enabled = False
    agent_runner = MagicMock()

    manager = setup_internal_registries(
        _config=mock_config,
        agent_runner=agent_runner,
    )

    registries = manager.get_all_registries()
    registry_names = [r.name for r in registries]
    assert "gobby-agents" in registry_names


def test_setup_with_worktree_storage_only():
    """Test setup with only worktree storage enabled."""
    mock_config = MagicMock()
    mock_config.get_gobby_tasks_config.return_value.enabled = False
    worktree_storage = MagicMock()

    manager = setup_internal_registries(
        _config=mock_config,
        worktree_storage=worktree_storage,
    )

    registries = manager.get_all_registries()
    registry_names = [r.name for r in registries]
    assert "gobby-worktrees" in registry_names


def test_setup_sessions_with_message_manager():
    """Test sessions registry is created with message_manager."""
    mock_config = MagicMock()
    mock_config.get_gobby_tasks_config.return_value.enabled = False
    message_manager = MagicMock()

    manager = setup_internal_registries(
        _config=mock_config,
        message_manager=message_manager,
    )

    registries = manager.get_all_registries()
    registry_names = [r.name for r in registries]
    assert "gobby-sessions" in registry_names


def test_setup_sessions_with_local_session_manager():
    """Test sessions registry is created with local_session_manager."""
    mock_config = MagicMock()
    mock_config.get_gobby_tasks_config.return_value.enabled = False
    local_session_manager = MagicMock()

    manager = setup_internal_registries(
        _config=mock_config,
        local_session_manager=local_session_manager,
    )

    registries = manager.get_all_registries()
    registry_names = [r.name for r in registries]
    assert "gobby-sessions" in registry_names


def test_setup_hub_registry_with_database_path():
    """Test hub registry is created when config has database_path."""
    mock_config = MagicMock()
    mock_config.get_gobby_tasks_config.return_value.enabled = False
    mock_config.database_path = "/tmp/test.db"

    manager = setup_internal_registries(_config=mock_config)

    registries = manager.get_all_registries()
    registry_names = [r.name for r in registries]
    assert "gobby-hub" in registry_names


def test_setup_tasks_disabled_by_config():
    """Test tasks registry is not created when disabled in config."""
    mock_config = MagicMock()
    mock_config.get_gobby_tasks_config.return_value.enabled = False
    task_manager = MagicMock()
    sync_manager = MagicMock()

    manager = setup_internal_registries(
        _config=mock_config,
        task_manager=task_manager,
        sync_manager=sync_manager,
    )

    registries = manager.get_all_registries()
    registry_names = [r.name for r in registries]
    # Tasks should NOT be present when disabled in config
    assert "gobby-tasks" not in registry_names


def test_setup_tasks_missing_task_manager():
    """Test tasks registry is not created when task_manager is None."""
    mock_config = MagicMock()
    mock_config.get_gobby_tasks_config.return_value.enabled = True
    sync_manager = MagicMock()

    manager = setup_internal_registries(
        _config=mock_config,
        task_manager=None,
        sync_manager=sync_manager,
    )

    registries = manager.get_all_registries()
    registry_names = [r.name for r in registries]
    # Tasks should NOT be present when task_manager is None
    assert "gobby-tasks" not in registry_names


def test_setup_tasks_missing_sync_manager():
    """Test tasks registry is not created when sync_manager is None."""
    mock_config = MagicMock()
    mock_config.get_gobby_tasks_config.return_value.enabled = True
    task_manager = MagicMock()

    manager = setup_internal_registries(
        _config=mock_config,
        task_manager=task_manager,
        sync_manager=None,
    )

    registries = manager.get_all_registries()
    registry_names = [r.name for r in registries]
    # Tasks should NOT be present when sync_manager is None
    assert "gobby-tasks" not in registry_names


def test_setup_merge_requires_both_storage_and_resolver():
    """Test merge registry requires both merge_storage and merge_resolver."""
    mock_config = MagicMock()
    mock_config.get_gobby_tasks_config.return_value.enabled = False

    # Test with only storage
    manager1 = setup_internal_registries(
        _config=mock_config,
        merge_storage=MagicMock(),
        merge_resolver=None,
    )
    registries1 = [r.name for r in manager1.get_all_registries()]
    assert "gobby-merge" not in registries1

    # Test with only resolver
    manager2 = setup_internal_registries(
        _config=mock_config,
        merge_storage=None,
        merge_resolver=MagicMock(),
    )
    registries2 = [r.name for r in manager2.get_all_registries()]
    assert "gobby-merge" not in registries2
