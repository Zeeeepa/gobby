#!/usr/bin/env python3
"""
Create a single task using MCP tools.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from gobby.llm.claude import ClaudeLLMProvider
from gobby.config.app import AppConfig


async def create_task():
    """Create a task using MCP tools."""

    # Initialize Claude provider with MCP support
    config = AppConfig.load()
    provider = ClaudeLLMProvider(
        api_key=config.llm.anthropic_api_key,
    )

    print("Creating task via MCP tools...")

    result = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Create project directory structure and files",
            "description": "Set up the basic project structure for the 2048 game:\n\n- Create index.html with basic HTML5 boilerplate\n- Create styles.css for game styling\n- Create game.js for game logic\n- Create README.md with project overview\n- Ensure files are in appropriate directories\n\n**Test Strategy:** Verify all files exist with proper structure using ls commands and basic file content checks",
            "parent_task_id": "gt-d8f9fc",
            "priority": 1,
            "task_type": "task"
        }
    )

    print(f"\n✅ Task created successfully!")
    print(f"\nResult:")
    print(json.dumps(result, indent=2))

    return result


if __name__ == "__main__":
    try:
        result = asyncio.run(create_task())
        print("\n🎉 Task creation complete!")
    except Exception as e:
        print(f"\n❌ Error creating task: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
