#!/usr/bin/env python3
"""
Create a task using the gobby-tasks MCP server.
"""

import asyncio
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from gobby.llm.claude import ClaudeLLMProvider
from gobby.config.app import AppConfig


async def create_task():
    """Create a task for Grid data structure tests."""

    # Initialize Claude provider with MCP support
    config = AppConfig.load()
    provider = ClaudeLLMProvider(
        api_key=config.llm.anthropic_api_key,
    )

    # Call the MCP tool
    result = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Write tests for Grid data structure",
            "description": """Create comprehensive tests for the Grid class that will manage the 2048 game board:

- Test grid initialization (4x4 grid)
- Test cell value getting/setting
- Test available cells detection
- Test random empty cell selection
- Test grid cloning for state comparison

**Test Strategy:** Tests should fail initially (red phase). Run tests and verify they fail with appropriate error messages.""",
            "parent_task_id": "gt-d8f9fc",
            "priority": 1,
            "task_type": "task"
        }
    )

    print(f"Task created successfully!")
    print(f"Result: {result}")

    return result


if __name__ == "__main__":
    try:
        result = asyncio.run(create_task())
        print(f"\n✅ Task created: {result.get('id', result)}")
    except Exception as e:
        print(f"\n❌ Error creating task: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
