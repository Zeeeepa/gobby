"""
E2E tests for gobby-worktrees MCP tools.

Tests verify:
1. Worktree creation with real git repositories
2. Worktree listing and retrieval
3. Worktree claim/release lifecycle
4. Worktree sync and deletion
5. Stats and stale worktree detection
"""

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.conftest import DaemonInstance, MCPTestClient

# Skip all worktree E2E tests - foreign key constraint failures due to race condition
# between daemon database initialization and test fixture project creation.
# The project created in git_repo_with_origin fixture may not be visible to
# the daemon's database connection when create_worktree is called.
# TODO: Fix by adding project existence verification or using daemon HTTP API
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skip(reason="E2E worktree tests have race condition - daemon/fixture db sync issue"),
]


def extract_result(response: dict[str, Any]) -> dict[str, Any]:
    """Extract the actual tool result from MCP response wrapper.

    MCP responses are wrapped: {'success': True, 'result': {...}, 'response_time_ms': ...}
    This extracts the inner 'result' dict.
    """
    if "result" in response:
        return response["result"]
    return response


@pytest.fixture
def git_repo_with_origin(
    e2e_project_dir: Path, tmp_path_factory, cli_events, daemon_instance
) -> Path:
    """Initialize a git repository with a local origin for worktree tests.

    WorktreeGitManager.create_worktree fetches from origin, so we need
    to set up a bare repo as origin for the test.
    """
    # Remove the pre-existing project.json created by e2e_project_dir
    # This allows the daemon to auto-initialize the project properly
    # (creating it in the database, not just the file)
    gobby_dir = e2e_project_dir / ".gobby"
    project_json = gobby_dir / "project.json"
    if project_json.exists():
        project_json.unlink()

    # Create a bare repo to serve as "origin"
    origin_path = tmp_path_factory.mktemp("origin")
    subprocess.run(
        ["git", "init", "--bare"],
        cwd=str(origin_path),
        check=True,
        capture_output=True,
    )

    # Initialize the main repo
    subprocess.run(
        ["git", "init"],
        cwd=str(e2e_project_dir),
        check=True,
        capture_output=True,
    )

    # Configure git user for commits
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(e2e_project_dir),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(e2e_project_dir),
        check=True,
        capture_output=True,
    )

    # Ensure default branch is 'main'
    subprocess.run(
        ["git", "config", "init.defaultBranch", "main"],
        cwd=str(e2e_project_dir),
        check=True,
        capture_output=True,
    )

    # Create initial commit with .gitignore for .gobby/
    readme = e2e_project_dir / "README.md"
    readme.write_text("# Test Project\n")
    gitignore = e2e_project_dir / ".gitignore"
    gitignore.write_text(".gobby/\n")
    subprocess.run(
        ["git", "add", "."],
        cwd=str(e2e_project_dir),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=str(e2e_project_dir),
        check=True,
        capture_output=True,
    )

    # Ensure we're on main branch (in case default was master)
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(e2e_project_dir),
        capture_output=True,
        text=True,
    )
    if current_branch.stdout.strip() != "main":
        subprocess.run(
            ["git", "branch", "-m", current_branch.stdout.strip(), "main"],
            cwd=str(e2e_project_dir),
            check=True,
            capture_output=True,
        )

    # Add origin remote
    subprocess.run(
        ["git", "remote", "add", "origin", str(origin_path)],
        cwd=str(e2e_project_dir),
        check=True,
        capture_output=True,
    )

    # Push main to origin
    subprocess.run(
        ["git", "push", "-u", "origin", "main"],
        cwd=str(e2e_project_dir),
        check=True,
        capture_output=True,
    )

    # Create the project in the daemon's database directly.
    # The daemon uses its own database (from config), so we need to connect
    # to that specific database to create the project.
    import json

    from gobby.storage.database import LocalDatabase
    from gobby.storage.migrations import run_migrations
    from gobby.storage.projects import LocalProjectManager

    # Connect to the daemon's database
    db = LocalDatabase(daemon_instance.db_path)
    run_migrations(db)

    # Create the project
    project_manager = LocalProjectManager(db)
    project_name = e2e_project_dir.name
    project = project_manager.get_or_create(
        name=project_name,
        repo_path=str(e2e_project_dir),
    )

    # Write project.json with the created project's ID
    project_json = gobby_dir / "project.json"
    project_json.write_text(
        json.dumps(
            {
                "id": project.id,
                "name": project.name,
                "repo_path": str(e2e_project_dir),
            }
        )
    )

    db.close()

    return e2e_project_dir


class TestWorktreeCreation:
    """Tests for worktree creation via MCP tools."""

    def test_create_worktree_success(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        git_repo_with_origin: Path,
    ):
        """Create a worktree and verify it exists on disk."""
        import httpx

        # Make direct call to capture error response
        with httpx.Client(base_url=daemon_instance.http_url, timeout=30.0) as client:
            resp = client.post(
                "/mcp/tools/call",
                json={
                    "server_name": "gobby-worktrees",
                    "tool_name": "create_worktree",
                    "arguments": {
                        "branch_name": "feature/test-worktree",
                        "base_branch": "main",
                        "project_path": str(git_repo_with_origin),
                    },
                },
            )
            print(f"Response status: {resp.status_code}")
            print(f"Response body: {resp.text}")
            resp.raise_for_status()
            response = resp.json()

        result = extract_result(response)

        assert result.get("success") is True, f"Expected success, got: {result}"
        assert "worktree_id" in result
        assert "worktree_path" in result

        # Verify worktree exists on disk
        worktree_path = Path(result["worktree_path"])
        assert worktree_path.exists(), f"Worktree path should exist: {worktree_path}"

        # Verify it's a git worktree (has .git file, not directory)
        git_indicator = worktree_path / ".git"
        assert git_indicator.exists(), "Worktree should have .git file"

    def test_create_worktree_duplicate_branch_fails(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        git_repo_with_origin: Path,
    ):
        """Creating a worktree with existing branch name should fail."""
        branch_name = "feature/duplicate-test"

        # Create first worktree
        response1 = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="create_worktree",
            arguments={
                "branch_name": branch_name,
                "project_path": str(git_repo_with_origin),
            },
        )
        result1 = extract_result(response1)
        assert result1.get("success") is True

        # Try to create duplicate
        response2 = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="create_worktree",
            arguments={
                "branch_name": branch_name,
                "project_path": str(git_repo_with_origin),
            },
        )
        result2 = extract_result(response2)

        assert result2.get("success") is False
        assert "already exists" in result2.get("error", "").lower()


class TestWorktreeRetrieval:
    """Tests for worktree listing and retrieval."""

    def test_list_worktrees_returns_created_worktrees(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        git_repo_with_origin: Path,
    ):
        """List worktrees should return created worktrees."""
        # Create a couple worktrees
        branches = ["feature/list-test-1", "feature/list-test-2"]
        created_ids = []

        for branch in branches:
            response = mcp_client.call_tool(
                server_name="gobby-worktrees",
                tool_name="create_worktree",
                arguments={
                    "branch_name": branch,
                    "project_path": str(git_repo_with_origin),
                },
            )
            result = extract_result(response)
            assert result.get("success") is True, f"Failed to create worktree: {result}"
            created_ids.append(result["worktree_id"])

        # List worktrees
        list_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="list_worktrees",
            arguments={},
        )
        list_result = extract_result(list_response)

        assert list_result.get("success") is True
        assert "worktrees" in list_result
        assert list_result["count"] >= 2

        # Verify our worktrees are in the list
        listed_ids = [wt["id"] for wt in list_result["worktrees"]]
        for wt_id in created_ids:
            assert wt_id in listed_ids, f"Worktree {wt_id} should be in list"

    def test_get_worktree_by_id(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        git_repo_with_origin: Path,
    ):
        """Get worktree by ID returns correct details."""
        # Create worktree
        create_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="create_worktree",
            arguments={
                "branch_name": "feature/get-test",
                "project_path": str(git_repo_with_origin),
            },
        )
        create_result = extract_result(create_response)
        assert create_result.get("success") is True
        worktree_id = create_result["worktree_id"]

        # Get worktree
        get_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="get_worktree",
            arguments={"worktree_id": worktree_id},
        )
        get_result = extract_result(get_response)

        assert get_result.get("success") is True
        assert "worktree" in get_result
        wt = get_result["worktree"]
        assert wt["id"] == worktree_id
        assert wt["branch_name"] == "feature/get-test"
        assert wt["status"] == "active"

    def test_get_nonexistent_worktree_returns_error(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Getting a nonexistent worktree returns error."""
        response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="get_worktree",
            arguments={"worktree_id": "wt-nonexistent-12345"},
        )
        result = extract_result(response)

        assert result.get("success") is False
        assert "not found" in result.get("error", "").lower()


class TestWorktreeClaimRelease:
    """Tests for worktree claim and release lifecycle."""

    def test_claim_worktree(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        git_repo_with_origin: Path,
        cli_events,
    ):
        """Claiming a worktree assigns session ownership."""
        import json as json_lib

        # Create worktree
        create_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="create_worktree",
            arguments={
                "branch_name": "feature/claim-test",
                "project_path": str(git_repo_with_origin),
            },
        )
        create_result = extract_result(create_response)
        assert create_result.get("success") is True, f"Create failed: {create_result}"
        worktree_id = create_result["worktree_id"]

        # Read project_id from project.json
        project_json = git_repo_with_origin / ".gobby" / "project.json"
        project_data = json_lib.loads(project_json.read_text())
        project_id = project_data["id"]

        # Register a session via hook
        session_result = cli_events.session_start(
            session_id="claim-test-session",
            project_id=project_id,
        )

        # Parse session_id from additionalContext
        additional_context = session_result.get("hookSpecificOutput", {}).get(
            "additionalContext", ""
        )
        session_id = None
        for line in additional_context.split("\n"):
            if line.startswith("session_id:"):
                session_id = line.split(":", 1)[1].strip()
                break
        assert session_id, f"Could not find session_id in response: {session_result}"

        # Claim worktree
        claim_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="claim_worktree",
            arguments={
                "worktree_id": worktree_id,
                "session_id": session_id,
            },
        )
        claim_result = extract_result(claim_response)
        assert claim_result.get("success") is True, f"Claim failed: {claim_result}"

        # Verify claim
        get_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="get_worktree",
            arguments={"worktree_id": worktree_id},
        )
        get_result = extract_result(get_response)
        assert get_result["worktree"]["agent_session_id"] == session_id

    def test_release_worktree(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        git_repo_with_origin: Path,
        cli_events,
    ):
        """Releasing a worktree removes session ownership."""
        # Create worktree
        create_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="create_worktree",
            arguments={
                "branch_name": "feature/release-test",
                "project_path": str(git_repo_with_origin),
            },
        )
        create_result = extract_result(create_response)
        worktree_id = create_result["worktree_id"]

        # Register a session first (agent_session_id has FK to sessions)
        # Read project_id from project.json created by git_repo_with_origin fixture
        import json as json_lib

        project_json = git_repo_with_origin / ".gobby" / "project.json"
        project_data = json_lib.loads(project_json.read_text())
        project_id = project_data["id"]

        session_result = cli_events.session_start(
            session_id="release-test-session",
            project_id=project_id,
        )
        # Parse session_id from additionalContext
        additional_context = session_result.get("hookSpecificOutput", {}).get(
            "additionalContext", ""
        )
        session_id = None
        for line in additional_context.split("\n"):
            if line.startswith("session_id:"):
                session_id = line.split(":", 1)[1].strip()
                break
        assert session_id, f"Could not find session_id in response: {session_result}"

        # Claim worktree
        mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="claim_worktree",
            arguments={
                "worktree_id": worktree_id,
                "session_id": session_id,
            },
        )

        # Release worktree
        release_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="release_worktree",
            arguments={"worktree_id": worktree_id},
        )
        release_result = extract_result(release_response)
        assert release_result.get("success") is True

        # Verify release
        get_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="get_worktree",
            arguments={"worktree_id": worktree_id},
        )
        get_result = extract_result(get_response)
        assert get_result["worktree"]["agent_session_id"] is None


class TestWorktreeStatusTransitions:
    """Tests for worktree status transitions."""

    def test_mark_worktree_merged(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        git_repo_with_origin: Path,
    ):
        """Marking a worktree as merged updates status."""
        # Create worktree
        create_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="create_worktree",
            arguments={
                "branch_name": "feature/merge-test",
                "project_path": str(git_repo_with_origin),
            },
        )
        create_result = extract_result(create_response)
        worktree_id = create_result["worktree_id"]

        # Mark merged
        merge_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="mark_worktree_merged",
            arguments={"worktree_id": worktree_id},
        )
        merge_result = extract_result(merge_response)
        assert merge_result.get("success") is True

        # Verify status
        get_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="get_worktree",
            arguments={"worktree_id": worktree_id},
        )
        get_result = extract_result(get_response)
        assert get_result["worktree"]["status"] == "merged"


class TestWorktreeDeletion:
    """Tests for worktree deletion."""

    def test_delete_worktree_removes_from_database(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        git_repo_with_origin: Path,
    ):
        """Deleting a worktree removes it from database.

        Note: Without git_manager configured in daemon, only the database
        record is deleted. The actual git worktree on disk remains.
        """
        # Create worktree
        create_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="create_worktree",
            arguments={
                "branch_name": "feature/delete-test",
                "project_path": str(git_repo_with_origin),
            },
        )
        create_result = extract_result(create_response)
        worktree_id = create_result["worktree_id"]
        worktree_path = Path(create_result["worktree_path"])

        # Verify worktree was created
        assert worktree_path.exists()

        # Delete worktree
        delete_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="delete_worktree",
            arguments={
                "worktree_id": worktree_id,
                "force": True,
            },
        )
        delete_result = extract_result(delete_response)
        assert delete_result.get("success") is True

        # Verify removed from database
        get_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="get_worktree",
            arguments={"worktree_id": worktree_id},
        )
        get_result = extract_result(get_response)
        assert get_result.get("success") is False

    def test_delete_worktree_removes_branch(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        git_repo_with_origin: Path,
    ):
        """Deleting a worktree should also delete the git branch."""
        try:
            branch_name = "feature/delete-branch-test"

            # Create worktree
            create_response = mcp_client.call_tool(
                server_name="gobby-worktrees",
                tool_name="create_worktree",
                arguments={
                    "branch_name": branch_name,
                    "project_path": str(git_repo_with_origin),
                },
            )
            result = extract_result(create_response)
            assert result.get("success") is True
            worktree_id = result["worktree_id"]

            # Verify branch exists
            branch_check = subprocess.run(
                ["git", "rev-parse", "--verify", branch_name],
                cwd=str(git_repo_with_origin),
                capture_output=True,
            )
            assert branch_check.returncode == 0, "Branch should exist before deletion"

            # Delete worktree
            delete_response = mcp_client.call_tool(
                server_name="gobby-worktrees",
                tool_name="delete_worktree",
                arguments={
                    "worktree_id": worktree_id,
                    "force": True,
                    "project_path": str(git_repo_with_origin),
                },
            )
            delete_result = extract_result(delete_response)
            assert delete_result.get("success") is True

            # Verify branch is gone
            branch_check_after = subprocess.run(
                ["git", "rev-parse", "--verify", branch_name],
                cwd=str(git_repo_with_origin),
                capture_output=True,
            )
            assert branch_check_after.returncode != 0, "Branch should be deleted"
        except Exception:
            print("\n=== DAEMON STDOUT ===")
            print(daemon_instance.read_logs())
            print("\n=== DAEMON STDERR ===")
            print(daemon_instance.read_error_logs())
            raise


class TestWorktreeStats:
    """Tests for worktree statistics."""

    def test_get_worktree_stats(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        git_repo_with_origin: Path,
    ):
        """Get worktree stats returns counts by status."""
        # Create some worktrees
        for i in range(3):
            response = mcp_client.call_tool(
                server_name="gobby-worktrees",
                tool_name="create_worktree",
                arguments={
                    "branch_name": f"feature/stats-test-{i}",
                    "project_path": str(git_repo_with_origin),
                },
            )
            result = extract_result(response)
            assert result.get("success") is True, f"Failed to create worktree: {result}"

        # Get stats
        stats_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="get_worktree_stats",
            arguments={"project_path": str(git_repo_with_origin)},
        )
        stats_result = extract_result(stats_response)

        assert stats_result.get("success") is True
        assert "counts" in stats_result
        assert "total" in stats_result
        assert stats_result["total"] >= 3
        assert stats_result["counts"].get("active", 0) >= 3


class TestWorktreeSync:
    """Tests for worktree sync functionality."""

    def test_sync_worktree(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        git_repo_with_origin: Path,
    ):
        """Sync worktree updates from main branch."""
        # Create worktree
        create_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="create_worktree",
            arguments={
                "branch_name": "feature/sync-test",
                "project_path": str(git_repo_with_origin),
            },
        )
        create_result = extract_result(create_response)
        assert create_result.get("success") is True
        worktree_id = create_result["worktree_id"]

        # Make a commit on main
        test_file = git_repo_with_origin / "new_file.txt"
        test_file.write_text("New content from main")
        subprocess.run(
            ["git", "add", "."],
            cwd=str(git_repo_with_origin),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add new file on main"],
            cwd=str(git_repo_with_origin),
            check=True,
            capture_output=True,
        )
        # Push to origin so fetch works
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=str(git_repo_with_origin),
            check=True,
            capture_output=True,
        )

        # Sync worktree
        sync_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="sync_worktree",
            arguments={
                "worktree_id": worktree_id,
                "strategy": "merge",
                "project_path": str(git_repo_with_origin),
            },
        )
        sync_result = extract_result(sync_response)
        assert sync_result.get("success") is True, f"Sync failed: {sync_result}"


class TestWorktreeToolSchema:
    """Tests for tool schema discovery."""

    def test_list_worktree_tools(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """List tools returns gobby-worktrees tools."""
        tools = mcp_client.list_tools(server="gobby-worktrees")

        assert len(tools) > 0

        tool_names = [t["name"] for t in tools]

        # Verify expected tools exist
        expected_tools = [
            "create_worktree",
            "get_worktree",
            "list_worktrees",
            "claim_worktree",
            "release_worktree",
            "delete_worktree",
            "sync_worktree",
            "mark_worktree_merged",
            "get_worktree_stats",
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Tool {expected} should be available"

    def test_get_create_worktree_schema(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Get schema for create_worktree tool."""
        response = mcp_client.get_tool_schema(
            server_name="gobby-worktrees",
            tool_name="create_worktree",
        )

        assert response is not None
        assert response["name"] == "create_worktree"
        assert "inputSchema" in response

        # The endpoint returns {name, server, inputSchema: {name, description, inputSchema}}
        # due to double-wrapping. Access the inner inputSchema.
        inner_schema = response["inputSchema"]
        assert "inputSchema" in inner_schema
        input_schema = inner_schema["inputSchema"]
        assert "properties" in input_schema
        assert "branch_name" in input_schema["properties"]


class TestWorktreeTaskLinking:
    """Tests for linking tasks to worktrees."""

    def test_create_worktree_with_task_id(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        git_repo_with_origin: Path,
    ):
        """Create worktree with task ID links them."""
        # Create a task first
        task_response = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="create_task",
            arguments={
                "title": "Test task for worktree",
                "description": "Testing task-worktree linking",
            },
        )
        task_result = extract_result(task_response)
        task_id = task_result.get("id")

        # Create worktree with task_id
        create_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="create_worktree",
            arguments={
                "branch_name": "feature/task-link-test",
                "project_path": str(git_repo_with_origin),
                "task_id": task_id,
            },
        )
        create_result = extract_result(create_response)
        assert create_result.get("success") is True
        worktree_id = create_result["worktree_id"]

        # Verify task is linked
        get_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="get_worktree",
            arguments={"worktree_id": worktree_id},
        )
        get_result = extract_result(get_response)
        assert get_result["worktree"]["task_id"] == task_id

    def test_get_worktree_by_task(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        git_repo_with_origin: Path,
    ):
        """Get worktree by task ID."""
        # Create task and worktree
        task_response = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="create_task",
            arguments={"title": "Task for lookup test"},
        )
        task_result = extract_result(task_response)
        task_id = task_result.get("id")

        create_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="create_worktree",
            arguments={
                "branch_name": "feature/task-lookup-test",
                "project_path": str(git_repo_with_origin),
                "task_id": task_id,
            },
        )
        create_result = extract_result(create_response)
        worktree_id = create_result["worktree_id"]

        # Look up by task
        lookup_response = mcp_client.call_tool(
            server_name="gobby-worktrees",
            tool_name="get_worktree_by_task",
            arguments={"task_id": task_id},
        )
        lookup_result = extract_result(lookup_response)

        assert lookup_result.get("success") is True
        assert lookup_result["worktree"]["id"] == worktree_id
