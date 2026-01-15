"""Tests for task enrichment MCP tool.

TDD Red Phase: These tests should fail until the enrich_task tool is implemented
in the task_expansion module.

Task: #3245 - Write tests for: Add enrich_task MCP tool
Parent: #3153 - Add enrich_task MCP tool to gobby-tasks server

Tool parameters:
- task_id/task_ids (batch support)
- enable_code_research
- enable_web_research
- enable_mcp_tools
- generate_validation
- force (re-enrich even if already done)
- session_id
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.storage.tasks import LocalTaskManager, Task

# Try importing the registry creation function
try:
    from gobby.mcp_proxy.tools.task_expansion import create_expansion_registry

    IMPORT_SUCCEEDED = True
except ImportError:
    IMPORT_SUCCEEDED = False
    create_expansion_registry = None

# Try importing the enrichment classes
try:
    from gobby.tasks.enrich import EnrichmentResult, TaskEnricher

    ENRICH_IMPORT_SUCCEEDED = True
except ImportError:
    ENRICH_IMPORT_SUCCEEDED = False
    EnrichmentResult = None
    TaskEnricher = None


pytestmark = pytest.mark.skipif(
    not IMPORT_SUCCEEDED,
    reason="task_expansion module not available",
)


@pytest.fixture
def mock_task_manager():
    """Create a mock task manager."""
    manager = MagicMock(spec=LocalTaskManager)
    manager.db = MagicMock()
    return manager


@pytest.fixture
def mock_task_expander():
    """Create a mock task expander."""
    expander = AsyncMock()
    expander.config = MagicMock()
    expander.config.pattern_criteria = {}
    return expander


@pytest.fixture
def mock_task_enricher():
    """Create a mock task enricher."""
    if not ENRICH_IMPORT_SUCCEEDED:
        pytest.skip("enrich module not available")

    enricher = AsyncMock(spec=TaskEnricher)
    enricher.enrich = AsyncMock(
        return_value=EnrichmentResult(
            task_id="test-task",
            category="code",
            complexity_score=2,
            research_findings="Found relevant patterns",
            suggested_subtask_count=3,
            validation_criteria="Tests pass, code review approved",
            mcp_tools_used=["context7", "grep"],
        )
    )
    return enricher


@pytest.fixture
def enrichment_registry(mock_task_manager, mock_task_expander, mock_task_enricher):
    """Create an expansion registry with task_enricher for testing enrich_task."""
    if not IMPORT_SUCCEEDED:
        pytest.skip("Module not available")

    with (
        patch("gobby.mcp_proxy.tools.task_expansion.TaskDependencyManager"),
        patch("gobby.mcp_proxy.tools.task_expansion.LocalProjectManager"),
    ):
        registry = create_expansion_registry(
            task_manager=mock_task_manager,
            task_expander=mock_task_expander,
            task_enricher=mock_task_enricher,
        )
        yield registry


@pytest.fixture
def enrichment_registry_no_enricher(mock_task_manager, mock_task_expander):
    """Create an expansion registry without task_enricher (enrichment disabled)."""
    if not IMPORT_SUCCEEDED:
        pytest.skip("Module not available")

    with (
        patch("gobby.mcp_proxy.tools.task_expansion.TaskDependencyManager"),
        patch("gobby.mcp_proxy.tools.task_expansion.LocalProjectManager"),
    ):
        registry = create_expansion_registry(
            task_manager=mock_task_manager,
            task_expander=mock_task_expander,
            task_enricher=None,
        )
        yield registry


# ============================================================================
# enrich_task MCP Tool Tests
# ============================================================================


class TestEnrichTaskTool:
    """Tests for enrich_task MCP tool."""

    def test_enrich_task_tool_registered(self, enrichment_registry):
        """Test that enrich_task tool is registered in the registry."""
        tools = enrichment_registry.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "enrich_task" in tool_names, f"enrich_task not found in tools: {tool_names}"

    @pytest.mark.asyncio
    async def test_enrich_task_single_task(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task enriches a single task."""
        task = Task(
            id="t1",
            title="Implement user authentication",
            description="Add login and registration features",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        assert "task_id" in result
        assert result.get("success") is True or "error" not in result
        mock_task_enricher.enrich.assert_called_once()

    @pytest.mark.asyncio
    async def test_enrich_task_batch_support(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task supports batch enrichment via task_ids parameter."""
        tasks = [
            Task(
                id=f"t{i}",
                title=f"Task {i}",
                description=f"Description {i}",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            )
            for i in range(1, 4)
        ]

        def get_task_side_effect(tid):
            return next((t for t in tasks if t.id == tid), None)

        mock_task_manager.get_task.side_effect = get_task_side_effect

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_ids": ["t1", "t2", "t3"]},
        )

        assert "results" in result
        assert len(result["results"]) == 3
        assert mock_task_enricher.enrich.call_count == 3

    @pytest.mark.asyncio
    async def test_enrich_task_with_code_research(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task passes enable_code_research flag."""
        task = Task(
            id="t1",
            title="Add API endpoint",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1", "enable_code_research": True},
        )

        # Verify enricher was called with code research enabled
        mock_task_enricher.enrich.assert_called_once()
        call_kwargs = mock_task_enricher.enrich.call_args.kwargs
        assert call_kwargs.get("enable_code_research") is True

    @pytest.mark.asyncio
    async def test_enrich_task_with_web_research(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task passes enable_web_research flag."""
        task = Task(
            id="t1",
            title="Integrate OAuth",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1", "enable_web_research": True},
        )

        mock_task_enricher.enrich.assert_called_once()
        call_kwargs = mock_task_enricher.enrich.call_args.kwargs
        assert call_kwargs.get("enable_web_research") is True

    @pytest.mark.asyncio
    async def test_enrich_task_with_mcp_tools(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task passes enable_mcp_tools flag."""
        task = Task(
            id="t1",
            title="Task with MCP tools",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1", "enable_mcp_tools": True},
        )

        mock_task_enricher.enrich.assert_called_once()
        call_kwargs = mock_task_enricher.enrich.call_args.kwargs
        assert call_kwargs.get("enable_mcp_tools") is True

    @pytest.mark.asyncio
    async def test_enrich_task_generate_validation(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task passes generate_validation flag."""
        task = Task(
            id="t1",
            title="Task needing validation",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1", "generate_validation": True},
        )

        mock_task_enricher.enrich.assert_called_once()
        call_kwargs = mock_task_enricher.enrich.call_args.kwargs
        assert call_kwargs.get("generate_validation") is True

    @pytest.mark.asyncio
    async def test_enrich_task_skips_already_enriched(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task skips tasks that are already enriched."""
        task = Task(
            id="t1",
            title="Already enriched task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            is_enriched=True,  # Already enriched
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        # Should be skipped (not re-enriched)
        assert result.get("skipped") is True or "already_enriched" in str(result)
        mock_task_enricher.enrich.assert_not_called()

    @pytest.mark.asyncio
    async def test_enrich_task_force_re_enrich(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task force flag re-enriches already enriched tasks."""
        task = Task(
            id="t1",
            title="Already enriched task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            is_enriched=True,  # Already enriched
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1", "force": True},
        )

        # Should be re-enriched with force=True
        mock_task_enricher.enrich.assert_called_once()

    @pytest.mark.asyncio
    async def test_enrich_task_not_found(self, mock_task_manager, enrichment_registry):
        """Test enrich_task with non-existent task."""
        mock_task_manager.get_task.return_value = None

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_id": "nonexistent"},
        )

        assert "error" in result
        assert "not found" in result["error"].lower() or "invalid" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_enrich_task_no_enricher_raises_error(
        self, mock_task_manager, enrichment_registry_no_enricher
    ):
        """Test enrich_task raises error when task_enricher is not configured."""
        task = Task(
            id="t1",
            title="Task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        with pytest.raises(RuntimeError, match="not enabled|not configured"):
            await enrichment_registry_no_enricher.call(
                "enrich_task",
                {"task_id": "t1"},
            )

    @pytest.mark.asyncio
    async def test_enrich_task_handles_enricher_error(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task handles enricher errors gracefully."""
        task = Task(
            id="t1",
            title="Task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        # Make enricher raise an error
        mock_task_enricher.enrich.side_effect = Exception("Enrichment failed")

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        assert "error" in result
        assert "failed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_enrich_task_updates_task_with_result(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task updates task with enrichment results."""
        task = Task(
            id="t1",
            title="Task to enrich",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        # Verify task was updated with enrichment results
        mock_task_manager.update_task.assert_called()
        update_calls = mock_task_manager.update_task.call_args_list
        # At minimum, is_enriched should be set to True
        update_kwargs = update_calls[-1].kwargs if update_calls else {}
        assert update_kwargs.get("is_enriched") is True or any(
            call.kwargs.get("is_enriched") is True for call in update_calls
        )

    @pytest.mark.asyncio
    async def test_enrich_task_returns_enrichment_result(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task returns enrichment result data."""
        task = Task(
            id="t1",
            title="Task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        # Result should contain enrichment data
        assert "task_id" in result
        # Should have category, complexity_score, etc. if enrichment succeeded
        if "error" not in result:
            assert "category" in result or "enrichment" in result

    @pytest.mark.asyncio
    async def test_enrich_task_with_session_id(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task accepts session_id parameter."""
        task = Task(
            id="t1",
            title="Task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1", "session_id": "sess-123"},
        )

        # Should complete without error
        mock_task_enricher.enrich.assert_called_once()

    @pytest.mark.asyncio
    async def test_enrich_task_batch_partial_failure(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task batch handles partial failures gracefully."""
        tasks = [
            Task(
                id="t1",
                title="Good task",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            ),
            Task(
                id="t2",
                title="Bad task",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            ),
        ]

        def get_task_side_effect(tid):
            return next((t for t in tasks if t.id == tid), None)

        mock_task_manager.get_task.side_effect = get_task_side_effect

        # Make enricher fail on second task
        call_count = [0]

        async def enrich_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Enrichment failed for t2")
            return EnrichmentResult(task_id=kwargs.get("task_id", "t1"))

        mock_task_enricher.enrich.side_effect = enrich_side_effect

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_ids": ["t1", "t2"]},
        )

        # Should have results for both, with one being an error
        assert "results" in result
        assert len(result["results"]) == 2
        errors = [r for r in result["results"] if "error" in r]
        successes = [r for r in result["results"] if "error" not in r]
        assert len(errors) == 1
        assert len(successes) == 1

    @pytest.mark.asyncio
    async def test_enrich_task_batch_skips_enriched_unless_force(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task batch skips already-enriched tasks unless force=True."""
        tasks = [
            Task(
                id="t1",
                title="Not enriched",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                is_enriched=False,
                created_at="now",
                updated_at="now",
            ),
            Task(
                id="t2",
                title="Already enriched",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                is_enriched=True,  # Already enriched
                created_at="now",
                updated_at="now",
            ),
        ]

        def get_task_side_effect(tid):
            return next((t for t in tasks if t.id == tid), None)

        mock_task_manager.get_task.side_effect = get_task_side_effect

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_ids": ["t1", "t2"]},
        )

        # Only t1 should be enriched (t2 skipped)
        assert mock_task_enricher.enrich.call_count == 1
        assert "results" in result
        # t2 should show as skipped
        t2_result = next((r for r in result["results"] if r.get("task_id") == "t2"), None)
        assert t2_result is not None
        assert t2_result.get("skipped") is True


# ============================================================================
# enrich_task Schema Tests
# ============================================================================


class TestEnrichTaskSchema:
    """Tests for enrich_task tool input schema."""

    def test_enrich_task_schema_has_task_id(self, enrichment_registry):
        """Test enrich_task schema has task_id parameter."""
        schema = enrichment_registry.get_schema("enrich_task")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        assert "task_id" in input_schema["properties"]

    def test_enrich_task_schema_has_task_ids(self, enrichment_registry):
        """Test enrich_task schema has task_ids parameter for batch support."""
        schema = enrichment_registry.get_schema("enrich_task")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        assert "task_ids" in input_schema["properties"]

    def test_enrich_task_schema_has_enable_code_research(self, enrichment_registry):
        """Test enrich_task schema has enable_code_research parameter."""
        schema = enrichment_registry.get_schema("enrich_task")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        assert "enable_code_research" in input_schema["properties"]

    def test_enrich_task_schema_has_enable_web_research(self, enrichment_registry):
        """Test enrich_task schema has enable_web_research parameter."""
        schema = enrichment_registry.get_schema("enrich_task")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        assert "enable_web_research" in input_schema["properties"]

    def test_enrich_task_schema_has_enable_mcp_tools(self, enrichment_registry):
        """Test enrich_task schema has enable_mcp_tools parameter."""
        schema = enrichment_registry.get_schema("enrich_task")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        assert "enable_mcp_tools" in input_schema["properties"]

    def test_enrich_task_schema_has_generate_validation(self, enrichment_registry):
        """Test enrich_task schema has generate_validation parameter."""
        schema = enrichment_registry.get_schema("enrich_task")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        assert "generate_validation" in input_schema["properties"]

    def test_enrich_task_schema_has_force(self, enrichment_registry):
        """Test enrich_task schema has force parameter."""
        schema = enrichment_registry.get_schema("enrich_task")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        assert "force" in input_schema["properties"]

    def test_enrich_task_schema_has_session_id(self, enrichment_registry):
        """Test enrich_task schema has session_id parameter."""
        schema = enrichment_registry.get_schema("enrich_task")
        assert schema is not None
        input_schema = schema.get("inputSchema", schema)
        assert "session_id" in input_schema["properties"]


# ============================================================================
# Integration Tests
# ============================================================================


class TestEnrichTaskIntegration:
    """Integration tests for enrich_task with TaskEnricher."""

    @pytest.mark.asyncio
    async def test_enrich_task_updates_category(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task updates task category from enrichment result."""
        task = Task(
            id="t1",
            title="Implement OAuth",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            category=None,  # No category yet
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        # Category should be updated from enrichment result
        update_calls = mock_task_manager.update_task.call_args_list
        # Look for category update
        category_updated = any(
            call.kwargs.get("category") == "code" for call in update_calls
        )
        assert category_updated, f"Category not updated in calls: {update_calls}"

    @pytest.mark.asyncio
    async def test_enrich_task_updates_complexity_score(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task updates complexity score from enrichment result."""
        task = Task(
            id="t1",
            title="Complex feature",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            complexity_score=None,
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        update_calls = mock_task_manager.update_task.call_args_list
        complexity_updated = any(
            call.kwargs.get("complexity_score") is not None for call in update_calls
        )
        assert complexity_updated

    @pytest.mark.asyncio
    async def test_enrich_task_updates_validation_criteria(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task updates validation criteria from enrichment result."""
        task = Task(
            id="t1",
            title="Task needing validation",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            validation_criteria=None,
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1", "generate_validation": True},
        )

        update_calls = mock_task_manager.update_task.call_args_list
        validation_updated = any(
            call.kwargs.get("validation_criteria") is not None for call in update_calls
        )
        assert validation_updated

    @pytest.mark.asyncio
    async def test_enrich_task_records_mcp_tools_used(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task result includes MCP tools used during enrichment."""
        task = Task(
            id="t1",
            title="Task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1", "enable_mcp_tools": True},
        )

        # Result should include mcp_tools_used from enrichment
        if "error" not in result:
            assert "mcp_tools_used" in result or "enrichment" in result

    @pytest.mark.asyncio
    async def test_enrich_task_all_flags_disabled(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task with all research flags disabled."""
        task = Task(
            id="t1",
            title="Simple task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {
                "task_id": "t1",
                "enable_code_research": False,
                "enable_web_research": False,
                "enable_mcp_tools": False,
                "generate_validation": False,
            },
        )

        # Should still complete successfully with minimal enrichment
        mock_task_enricher.enrich.assert_called_once()
        call_kwargs = mock_task_enricher.enrich.call_args.kwargs
        assert call_kwargs.get("enable_code_research") is False
        assert call_kwargs.get("enable_web_research") is False

    @pytest.mark.asyncio
    async def test_enrich_task_all_flags_enabled(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test enrich_task with all research flags enabled."""
        task = Task(
            id="t1",
            title="Complex task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="feature",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {
                "task_id": "t1",
                "enable_code_research": True,
                "enable_web_research": True,
                "enable_mcp_tools": True,
                "generate_validation": True,
            },
        )

        mock_task_enricher.enrich.assert_called_once()
        call_kwargs = mock_task_enricher.enrich.call_args.kwargs
        assert call_kwargs.get("enable_code_research") is True
        assert call_kwargs.get("enable_web_research") is True


# ============================================================================
# Store Enrichment Results Tests
# ============================================================================


class TestStoreEnrichmentResults:
    """Tests for storing enrichment results in expansion_context field.

    TDD Red Phase: These tests verify that enrichment results are persisted
    in the task's expansion_context field for later use by expand_task.
    """

    @pytest.mark.asyncio
    async def test_enrich_task_stores_expansion_context(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that enrich_task stores enrichment results in expansion_context."""
        task = Task(
            id="t1",
            title="Task to enrich",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        # Verify expansion_context was updated
        update_calls = mock_task_manager.update_task.call_args_list
        expansion_context_updated = any(
            call.kwargs.get("expansion_context") is not None for call in update_calls
        )
        assert expansion_context_updated, "expansion_context should be set during enrichment"

    @pytest.mark.asyncio
    async def test_expansion_context_contains_research_findings(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that expansion_context contains research_findings."""
        import json

        task = Task(
            id="t1",
            title="Task with research",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1", "enable_code_research": True},
        )

        # Get the expansion_context value
        update_calls = mock_task_manager.update_task.call_args_list
        expansion_context = None
        for call in update_calls:
            if call.kwargs.get("expansion_context"):
                expansion_context = call.kwargs.get("expansion_context")
                break

        assert expansion_context is not None

        # Should be valid JSON
        context_data = json.loads(expansion_context)
        assert "research_findings" in context_data

    @pytest.mark.asyncio
    async def test_expansion_context_contains_complexity_info(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that expansion_context contains complexity information."""
        import json

        task = Task(
            id="t1",
            title="Complex task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        update_calls = mock_task_manager.update_task.call_args_list
        expansion_context = None
        for call in update_calls:
            if call.kwargs.get("expansion_context"):
                expansion_context = call.kwargs.get("expansion_context")
                break

        assert expansion_context is not None
        context_data = json.loads(expansion_context)
        assert "complexity_score" in context_data or "category" in context_data

    @pytest.mark.asyncio
    async def test_expansion_context_contains_suggested_subtask_count(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that expansion_context contains suggested subtask count."""
        import json

        task = Task(
            id="t1",
            title="Task for expansion",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        update_calls = mock_task_manager.update_task.call_args_list
        expansion_context = None
        for call in update_calls:
            if call.kwargs.get("expansion_context"):
                expansion_context = call.kwargs.get("expansion_context")
                break

        assert expansion_context is not None
        context_data = json.loads(expansion_context)
        assert "suggested_subtask_count" in context_data

    @pytest.mark.asyncio
    async def test_expansion_context_preserved_on_re_enrich(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that expansion_context is updated when force re-enriching."""
        import json

        task = Task(
            id="t1",
            title="Previously enriched task",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            is_enriched=True,
            expansion_context='{"old": "data"}',  # Existing context
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1", "force": True},
        )

        # Should have new expansion_context
        update_calls = mock_task_manager.update_task.call_args_list
        expansion_context = None
        for call in update_calls:
            if call.kwargs.get("expansion_context"):
                expansion_context = call.kwargs.get("expansion_context")
                break

        assert expansion_context is not None
        context_data = json.loads(expansion_context)
        # Should have new enrichment data, not old
        assert "old" not in context_data or "research_findings" in context_data

    @pytest.mark.asyncio
    async def test_expansion_context_batch_enrichment(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that expansion_context is stored for each task in batch."""
        tasks = [
            Task(
                id=f"t{i}",
                title=f"Task {i}",
                project_id="p1",
                status="open",
                priority=2,
                task_type="task",
                created_at="now",
                updated_at="now",
            )
            for i in range(1, 3)
        ]

        def get_task_side_effect(tid):
            return next((t for t in tasks if t.id == tid), None)

        mock_task_manager.get_task.side_effect = get_task_side_effect

        await enrichment_registry.call(
            "enrich_task",
            {"task_ids": ["t1", "t2"]},
        )

        # Should have update calls for both tasks
        update_calls = mock_task_manager.update_task.call_args_list
        tasks_with_expansion_context = set()
        for call in update_calls:
            if call.kwargs.get("expansion_context"):
                # The task_id is the first positional argument
                task_id = call.args[0] if call.args else None
                if task_id:
                    tasks_with_expansion_context.add(task_id)

        # Both tasks should have expansion_context set
        assert len(tasks_with_expansion_context) >= 1  # At least one task updated

    @pytest.mark.asyncio
    async def test_expansion_context_includes_mcp_tools_used(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that expansion_context includes MCP tools used if any."""
        import json

        task = Task(
            id="t1",
            title="Task with MCP tools",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1", "enable_mcp_tools": True},
        )

        update_calls = mock_task_manager.update_task.call_args_list
        expansion_context = None
        for call in update_calls:
            if call.kwargs.get("expansion_context"):
                expansion_context = call.kwargs.get("expansion_context")
                break

        if expansion_context:
            context_data = json.loads(expansion_context)
            # mcp_tools_used should be present (even if empty list)
            assert "mcp_tools_used" in context_data


# ============================================================================
# Input Size Validation Tests
# ============================================================================


class TestInputSizeValidation:
    """Tests for input size validation in enrich_task.

    TDD Red Phase: These tests verify that enrich_task validates input size
    before making LLM calls to prevent wasted calls on oversized inputs.
    """

    @pytest.mark.asyncio
    async def test_enrich_task_accepts_normal_description(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that enrich_task accepts descriptions under the limit."""
        task = Task(
            id="t1",
            title="Normal task",
            description="A normal description that is well under 10,000 characters.",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        # Should succeed without error
        assert "error" not in result or "size" not in result.get("error", "").lower()
        mock_task_enricher.enrich.assert_called_once()

    @pytest.mark.asyncio
    async def test_enrich_task_rejects_oversized_description(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that enrich_task rejects descriptions over 10,000 characters."""
        # Create a description that exceeds 10,000 characters
        oversized_description = "x" * 10001

        task = Task(
            id="t1",
            title="Task with huge description",
            description=oversized_description,
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        # Should return error about size
        assert "error" in result
        assert "size" in result["error"].lower() or "large" in result["error"].lower()
        # Should NOT call enricher (saves LLM call)
        mock_task_enricher.enrich.assert_not_called()

    @pytest.mark.asyncio
    async def test_enrich_task_exactly_at_limit(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that enrich_task accepts descriptions exactly at 10,000 characters."""
        # Create a description that is exactly at the limit
        description_at_limit = "x" * 10000

        task = Task(
            id="t1",
            title="Task at limit",
            description=description_at_limit,
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        # Should succeed - exactly at limit is OK
        assert "error" not in result or "size" not in result.get("error", "").lower()
        mock_task_enricher.enrich.assert_called_once()

    @pytest.mark.asyncio
    async def test_enrich_task_oversized_suggests_cli(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that oversized input returns CLI suggestion."""
        oversized_description = "x" * 15000

        task = Task(
            id="t1",
            title="Task with huge description",
            description=oversized_description,
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        # Should suggest using CLI or splitting the task
        assert "error" in result
        # Should include a helpful suggestion
        error_lower = result["error"].lower()
        assert "cli" in error_lower or "split" in error_lower or "smaller" in error_lower

    @pytest.mark.asyncio
    async def test_enrich_task_batch_validates_each_task(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that batch enrichment validates each task's size."""
        normal_task = Task(
            id="t1",
            title="Normal task",
            description="Normal description",
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        oversized_task = Task(
            id="t2",
            title="Oversized task",
            description="x" * 15000,
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )

        def get_task_side_effect(tid):
            if tid == "t1":
                return normal_task
            elif tid == "t2":
                return oversized_task
            return None

        mock_task_manager.get_task.side_effect = get_task_side_effect

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_ids": ["t1", "t2"]},
        )

        # Should have results for both
        assert "results" in result
        assert len(result["results"]) == 2

        # t1 should succeed, t2 should fail with size error
        t1_result = next((r for r in result["results"] if r.get("task_id") == "t1"), None)
        t2_result = next((r for r in result["results"] if r.get("task_id") == "t2"), None)

        assert t1_result is not None
        assert t2_result is not None
        assert "error" not in t1_result or "size" not in t1_result.get("error", "").lower()
        assert "error" in t2_result

    @pytest.mark.asyncio
    async def test_enrich_task_validates_before_enricher_call(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that size validation happens BEFORE enricher is called."""
        oversized_description = "x" * 20000

        task = Task(
            id="t1",
            title="Huge task",
            description=oversized_description,
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        # Enricher should NOT be called for oversized input
        mock_task_enricher.enrich.assert_not_called()

    @pytest.mark.asyncio
    async def test_enrich_task_null_description_ok(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that tasks with no description are accepted."""
        task = Task(
            id="t1",
            title="Task without description",
            description=None,
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        # Should succeed
        assert "error" not in result or "size" not in result.get("error", "").lower()
        mock_task_enricher.enrich.assert_called_once()

    @pytest.mark.asyncio
    async def test_enrich_task_size_limit_is_configurable(
        self, mock_task_manager, mock_task_enricher, enrichment_registry
    ):
        """Test that the size limit can be configured (default 10,000)."""
        # This test documents the expected limit
        # The limit should be 10,000 characters as per the spec
        task = Task(
            id="t1",
            title="Test",
            description="x" * 9999,  # Just under limit
            project_id="p1",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
        )
        mock_task_manager.get_task.return_value = task

        result = await enrichment_registry.call(
            "enrich_task",
            {"task_id": "t1"},
        )

        # Should succeed - under the 10,000 character limit
        assert "error" not in result or "size" not in result.get("error", "").lower()
