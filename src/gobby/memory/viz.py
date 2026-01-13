"""
Memory Knowledge Graph Visualization.

Exports memory data as an interactive HTML graph using vis.js.
"""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.storage.memories import Memory, MemoryCrossRef


# Color palette for memory types
MEMORY_TYPE_COLORS = {
    "fact": "#4CAF50",  # Green
    "preference": "#2196F3",  # Blue
    "pattern": "#FF9800",  # Orange
    "context": "#9C27B0",  # Purple
}

DEFAULT_COLOR = "#607D8B"  # Grey for unknown types


def export_memory_graph(
    memories: list[Memory],
    crossrefs: list[MemoryCrossRef],
    title: str = "Memory Knowledge Graph",
) -> str:
    """
    Export memories and their cross-references as an interactive HTML graph.

    Uses vis.js for rendering. The output is a standalone HTML file that can
    be opened in any browser without additional dependencies.

    Args:
        memories: List of Memory objects to visualize
        crossrefs: List of cross-references defining edges between memories
        title: Title to display on the HTML page

    Returns:
        Complete HTML document as a string
    """
    # Build nodes data
    nodes = []
    for memory in memories:
        # Size based on importance (15-40 range)
        size = 15 + (memory.importance * 25)

        # Color based on type
        color = MEMORY_TYPE_COLORS.get(memory.memory_type, DEFAULT_COLOR)

        # Truncate content for label
        label = memory.content[:50] + "..." if len(memory.content) > 50 else memory.content

        nodes.append(
            {
                "id": memory.id,
                "label": label,
                "title": _build_tooltip(memory),
                "color": color,
                "size": size,
                "font": {"size": 10},
            }
        )

    # Build edges data
    edges = []
    memory_ids = {m.id for m in memories}
    for ref in crossrefs:
        # Only include edges where both nodes exist
        if ref.source_id in memory_ids and ref.target_id in memory_ids:
            # Edge width based on similarity (1-5 range)
            width = 1 + (ref.similarity * 4)
            edges.append(
                {
                    "from": ref.source_id,
                    "to": ref.target_id,
                    "width": width,
                    "title": f"Similarity: {ref.similarity:.2f}",
                }
            )

    # Generate HTML
    return _generate_html(nodes, edges, title)


def _build_tooltip(memory: Memory) -> str:
    """Build HTML tooltip for a memory node."""
    tags_str = ", ".join(memory.tags) if memory.tags else "none"
    return f"""
        <div style="max-width: 300px; padding: 8px;">
            <strong>Type:</strong> {html.escape(memory.memory_type)}<br>
            <strong>Importance:</strong> {memory.importance:.2f}<br>
            <strong>Tags:</strong> {html.escape(tags_str)}<br>
            <strong>ID:</strong> {html.escape(memory.id[:12])}...<br>
            <hr style="margin: 4px 0;">
            <div style="white-space: pre-wrap; word-wrap: break-word;">
                {html.escape(memory.content)}
            </div>
        </div>
    """.strip()


def _generate_html(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], title: str) -> str:
    """Generate the complete HTML document with vis.js."""
    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #1a1a2e;
            color: #eee;
        }}
        #header {{
            padding: 16px 24px;
            background: #16213e;
            border-bottom: 1px solid #0f3460;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        #header h1 {{
            font-size: 1.25rem;
            font-weight: 500;
        }}
        #legend {{
            display: flex;
            gap: 16px;
            font-size: 0.85rem;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
        #graph {{
            width: 100%;
            height: calc(100vh - 60px);
        }}
        #stats {{
            position: absolute;
            bottom: 16px;
            left: 16px;
            background: rgba(22, 33, 62, 0.9);
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 0.85rem;
        }}
    </style>
</head>
<body>
    <div id="header">
        <h1>{html.escape(title)}</h1>
        <div id="legend">
            <div class="legend-item">
                <div class="legend-dot" style="background: #4CAF50;"></div>
                <span>Fact</span>
            </div>
            <div class="legend-item">
                <div class="legend-dot" style="background: #2196F3;"></div>
                <span>Preference</span>
            </div>
            <div class="legend-item">
                <div class="legend-dot" style="background: #FF9800;"></div>
                <span>Pattern</span>
            </div>
            <div class="legend-item">
                <div class="legend-dot" style="background: #9C27B0;"></div>
                <span>Context</span>
            </div>
        </div>
    </div>
    <div id="graph"></div>
    <div id="stats">
        Nodes: {len(nodes)} | Edges: {len(edges)}
    </div>
    <script>
        const nodes = new vis.DataSet({nodes_json});
        const edges = new vis.DataSet({edges_json});

        const container = document.getElementById('graph');
        const data = {{ nodes, edges }};

        const options = {{
            nodes: {{
                shape: 'dot',
                borderWidth: 2,
                shadow: true,
                font: {{
                    color: '#eee'
                }}
            }},
            edges: {{
                color: {{
                    color: '#4a4a6a',
                    highlight: '#7a7aaa',
                    hover: '#6a6a8a'
                }},
                smooth: {{
                    type: 'continuous'
                }}
            }},
            physics: {{
                stabilization: {{
                    iterations: 100
                }},
                barnesHut: {{
                    gravitationalConstant: -2000,
                    springConstant: 0.04,
                    springLength: 150
                }}
            }},
            interaction: {{
                hover: true,
                tooltipDelay: 200,
                hideEdgesOnDrag: true
            }}
        }};

        const network = new vis.Network(container, data, options);

        // Double-click to focus on node
        network.on('doubleClick', function(params) {{
            if (params.nodes.length > 0) {{
                network.focus(params.nodes[0], {{
                    scale: 1.5,
                    animation: {{
                        duration: 500,
                        easingFunction: 'easeInOutQuad'
                    }}
                }});
            }}
        }});
    </script>
</body>
</html>"""
