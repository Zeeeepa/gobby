import pytest
from gobby.memory.viz import export_memory_graph, MEMORY_TYPE_COLORS, DEFAULT_COLOR
from gobby.storage.memories import Memory, MemoryCrossRef


class TestExportMemoryGraph:
    def test_export_empty_graph(self):
        html_out = export_memory_graph([], [], title="Empty Graph")
        assert "<!DOCTYPE html>" in html_out
        assert "Empty Graph" in html_out
        assert "Nodes: 0 | Edges: 0" in html_out

    def test_export_simple_graph(self):
        m1 = Memory(
            id="m1",
            content="Fact 1",
            memory_type="fact",
            importance=0.8,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        m2 = Memory(
            id="m2",
            content="Preference 1",
            memory_type="preference",
            importance=0.5,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        crossref = MemoryCrossRef(
            source_id="m1", target_id="m2", similarity=0.9, created_at="2024-01-01T00:00:00Z"
        )

        html_out = export_memory_graph([m1, m2], [crossref], title="Test Graph")

        assert "<!DOCTYPE html>" in html_out
        assert "Test Graph" in html_out
        assert "Nodes: 2 | Edges: 1" in html_out

        # Check for node content
        assert "Fact 1" in html_out
        assert "Preference 1" in html_out

        # Check for colors
        assert MEMORY_TYPE_COLORS["fact"] in html_out
        assert MEMORY_TYPE_COLORS["preference"] in html_out

    def test_export_unknown_memory_type(self):
        m1 = Memory(
            id="m1",
            content="Unknown",
            memory_type="unknown_type",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        html_out = export_memory_graph([m1], [])

        assert "Unknown" in html_out
        assert DEFAULT_COLOR in html_out

    def test_tooltip_content(self):
        m1 = Memory(
            id="m1",
            content="Detailed content with special chars < & >",
            tags=["tag1", "tag2"],
            memory_type="fact",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        html_out = export_memory_graph([m1], [])

        # detailed content should be escaped
        assert "Detailed content with special chars &lt; &amp; &gt;" in html_out
        assert "tag1, tag2" in html_out

    def test_edge_filtering(self):
        # Crossref refers to missing node 'm2'
        m1 = Memory(
            id="m1",
            content="Fact 1",
            memory_type="fact",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        crossref = MemoryCrossRef(
            source_id="m1", target_id="m2", similarity=0.9, created_at="2024-01-01T00:00:00Z"
        )

        html_out = export_memory_graph([m1], [crossref])

        # Should contain node but NO edges
        assert "Nodes: 1 | Edges: 0" in html_out
