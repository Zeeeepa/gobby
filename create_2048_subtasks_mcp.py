#!/usr/bin/env python3
"""
Create subtasks for 2048 game implementation using MCP tools.

This script demonstrates calling the gobby-tasks MCP server's create_task tool
to build a comprehensive task breakdown following TDD principles.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from gobby.llm.claude import ClaudeLLMProvider
from gobby.config.app import AppConfig


async def create_2048_subtasks():
    """Create all subtasks for 2048 game using MCP tools."""

    # Initialize Claude provider with MCP support
    config = AppConfig.load()
    provider = ClaudeLLMProvider(
        api_key=config.llm.anthropic_api_key,
    )

    parent_id = "gt-54b44a"

    # Track created task IDs for dependency wiring
    task_ids = {}

    print("Creating 2048 game subtasks via MCP tools...")
    print(f"Parent task: {parent_id}\n")

    # Subtask 1: Project Setup
    print("Creating Subtask 1: Project Setup...")
    result1 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Create project file structure",
            "description": "Set up the basic project directory structure and files: index.html, styles.css, game.js, README.md, and tests/ directory. Test Strategy: Verify all files and directories exist with correct names.",
            "priority": 1,
            "parent_id": parent_id,
        }
    )
    task_ids['setup'] = result1.get('id')
    print(f"  Created: {task_ids['setup']}")

    # Subtask 2: HTML Structure Test
    print("Creating Subtask 2: HTML Structure Test...")
    result2 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Write tests for HTML game board structure",
            "description": "Create tests to verify the HTML contains proper grid structure, score display, game status elements, and restart button. Test Strategy: Tests should fail initially (red phase).",
            "priority": 1,
            "parent_id": parent_id,
            "blocks": [task_ids['setup']],
        }
    )
    task_ids['html_test'] = result2.get('id')
    print(f"  Created: {task_ids['html_test']}")

    # Subtask 3: HTML Implementation
    print("Creating Subtask 3: HTML Implementation...")
    result3 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Implement HTML game board structure",
            "description": "Create the HTML markup with 4x4 grid container, score display, game status area, and restart button. Use semantic HTML5. Test Strategy: All HTML structure tests should pass (green phase).",
            "priority": 1,
            "parent_id": parent_id,
            "blocks": [task_ids['html_test']],
        }
    )
    task_ids['html_impl'] = result3.get('id')
    print(f"  Created: {task_ids['html_impl']}")

    # Subtask 4: CSS Grid Layout Test
    print("Creating Subtask 4: CSS Grid Layout Test...")
    result4 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Write tests for CSS grid layout",
            "description": "Create tests to verify the 4x4 grid layout, tile positioning, responsive design breakpoints. Test Strategy: Tests should fail initially (red phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['html_impl']],
        }
    )
    task_ids['css_test'] = result4.get('id')
    print(f"  Created: {task_ids['css_test']}")

    # Subtask 5: CSS Grid Implementation
    print("Creating Subtask 5: CSS Grid Implementation...")
    result5 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Implement CSS grid layout and base styles",
            "description": "Style the 4x4 grid using CSS Grid or Flexbox, implement responsive design for mobile and desktop, add base tile styles. Test Strategy: All CSS layout tests should pass (green phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['css_test']],
        }
    )
    task_ids['css_impl'] = result5.get('id')
    print(f"  Created: {task_ids['css_impl']}")

    # Subtask 6: Game State Test
    print("Creating Subtask 6: Game State Test...")
    result6 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Write tests for game state management",
            "description": "Create tests for game board initialization, tile data structure, game state tracking (playing/won/lost). Test Strategy: Tests should fail initially (red phase).",
            "priority": 1,
            "parent_id": parent_id,
            "blocks": [task_ids['css_impl']],
        }
    )
    task_ids['state_test'] = result6.get('id')
    print(f"  Created: {task_ids['state_test']}")

    # Subtask 7: Game State Implementation
    print("Creating Subtask 7: Game State Implementation...")
    result7 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Implement game state management",
            "description": "Create GameState class/object to manage 4x4 board array, current score, game status. Initialize empty board. Test Strategy: All game state tests should pass (green phase).",
            "priority": 1,
            "parent_id": parent_id,
            "blocks": [task_ids['state_test']],
        }
    )
    task_ids['state_impl'] = result7.get('id')
    print(f"  Created: {task_ids['state_impl']}")

    # Subtask 8: Tile Spawning Test
    print("Creating Subtask 8: Tile Spawning Test...")
    result8 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Write tests for tile spawning logic",
            "description": "Create tests for spawning tiles in random empty positions, 90% probability of 2 and 10% probability of 4, initial game start with 2 tiles. Test Strategy: Tests should fail initially (red phase).",
            "priority": 1,
            "parent_id": parent_id,
            "blocks": [task_ids['state_impl']],
        }
    )
    task_ids['spawn_test'] = result8.get('id')
    print(f"  Created: {task_ids['spawn_test']}")

    # Subtask 9: Tile Spawning Implementation
    print("Creating Subtask 9: Tile Spawning Implementation...")
    result9 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Implement tile spawning logic",
            "description": "Implement addRandomTile() function that finds empty cells, randomly selects one, and places a tile (90% chance of 2, 10% chance of 4). Test Strategy: All tile spawning tests should pass (green phase).",
            "priority": 1,
            "parent_id": parent_id,
            "blocks": [task_ids['spawn_test']],
        }
    )
    task_ids['spawn_impl'] = result9.get('id')
    print(f"  Created: {task_ids['spawn_impl']}")

    # Subtask 10: Movement Logic Test
    print("Creating Subtask 10: Movement Logic Test...")
    result10 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Write tests for tile movement and merging",
            "description": "Create comprehensive tests for moving tiles up/down/left/right, merging identical adjacent tiles, preventing invalid moves. Include edge cases. Test Strategy: Tests should fail initially (red phase).",
            "priority": 1,
            "parent_id": parent_id,
            "blocks": [task_ids['spawn_impl']],
        }
    )
    task_ids['move_test'] = result10.get('id')
    print(f"  Created: {task_ids['move_test']}")

    # Subtask 11: Movement Logic Implementation
    print("Creating Subtask 11: Movement Logic Implementation...")
    result11 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Implement tile movement and merging logic",
            "description": "Implement move() function for all 4 directions with proper tile sliding, merging logic (identical tiles combine into sum), and score updating. Test Strategy: All movement and merging tests should pass (green phase).",
            "priority": 1,
            "parent_id": parent_id,
            "blocks": [task_ids['move_test']],
        }
    )
    task_ids['move_impl'] = result11.get('id')
    print(f"  Created: {task_ids['move_impl']}")

    # Subtask 12: Input Handling Test
    print("Creating Subtask 12: Input Handling Test...")
    result12 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Write tests for keyboard and touch input",
            "description": "Create tests for arrow key detection, touch/swipe gesture recognition, input validation (prevent moves during animation). Test Strategy: Tests should fail initially (red phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['move_impl']],
        }
    )
    task_ids['input_test'] = result12.get('id')
    print(f"  Created: {task_ids['input_test']}")

    # Subtask 13: Input Handling Implementation
    print("Creating Subtask 13: Input Handling Implementation...")
    result13 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Implement keyboard and touch input handlers",
            "description": "Add event listeners for arrow keys (up/down/left/right) and touch events (touchstart/touchmove/touchend) with swipe detection. Test Strategy: All input handling tests should pass (green phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['input_test']],
        }
    )
    task_ids['input_impl'] = result13.get('id')
    print(f"  Created: {task_ids['input_impl']}")

    # Subtask 14: Score Tracking Test
    print("Creating Subtask 14: Score Tracking Test...")
    result14 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Write tests for score tracking",
            "description": "Create tests for score calculation during merges, high score tracking, localStorage persistence and retrieval. Test Strategy: Tests should fail initially (red phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['input_impl']],
        }
    )
    task_ids['score_test'] = result14.get('id')
    print(f"  Created: {task_ids['score_test']}")

    # Subtask 15: Score Tracking Implementation
    print("Creating Subtask 15: Score Tracking Implementation...")
    result15 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Implement score tracking with localStorage",
            "description": "Implement score increment on merges, maintain high score, persist both scores to localStorage, load on game start. Test Strategy: All score tracking tests should pass (green phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['score_test']],
        }
    )
    task_ids['score_impl'] = result15.get('id')
    print(f"  Created: {task_ids['score_impl']}")

    # Subtask 16: Win/Lose Detection Test
    print("Creating Subtask 16: Win/Lose Detection Test...")
    result16 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Write tests for win and lose conditions",
            "description": "Create tests for detecting 2048 tile (win), detecting no valid moves (lose), continuing after win. Test Strategy: Tests should fail initially (red phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['score_impl']],
        }
    )
    task_ids['winlose_test'] = result16.get('id')
    print(f"  Created: {task_ids['winlose_test']}")

    # Subtask 17: Win/Lose Detection Implementation
    print("Creating Subtask 17: Win/Lose Detection Implementation...")
    result17 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Implement win and lose detection",
            "description": "Implement checkWin() to detect 2048 tile, checkLose() to verify no empty cells and no valid merges, update game status accordingly. Test Strategy: All win/lose detection tests should pass (green phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['winlose_test']],
        }
    )
    task_ids['winlose_impl'] = result17.get('id')
    print(f"  Created: {task_ids['winlose_impl']}")

    # Subtask 18: Animation Test
    print("Creating Subtask 18: Animation Test...")
    result18 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Write tests for tile animations",
            "description": "Create tests for smooth tile movement transitions, merge animations, new tile appearance animation, 60fps performance verification. Test Strategy: Tests should fail initially (red phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['winlose_impl']],
        }
    )
    task_ids['anim_test'] = result18.get('id')
    print(f"  Created: {task_ids['anim_test']}")

    # Subtask 19: Animation Implementation
    print("Creating Subtask 19: Animation Implementation...")
    result19 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Implement smooth 60fps tile animations",
            "description": "Add CSS transitions for tile movement (200-250ms), merge pop effect, new tile scale-in. Use transform and opacity for GPU acceleration. Test Strategy: All animation tests should pass with 60fps performance (green phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['anim_test']],
        }
    )
    task_ids['anim_impl'] = result19.get('id')
    print(f"  Created: {task_ids['anim_impl']}")

    # Subtask 20: Tile Rendering Test
    print("Creating Subtask 20: Tile Rendering Test...")
    result20 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Write tests for tile rendering and styling",
            "description": "Create tests for rendering tiles with correct values, positions, colors (different colors for different values), tile number display. Test Strategy: Tests should fail initially (red phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['anim_impl']],
        }
    )
    task_ids['render_test'] = result20.get('id')
    print(f"  Created: {task_ids['render_test']}")

    # Subtask 21: Tile Rendering Implementation
    print("Creating Subtask 21: Tile Rendering Implementation...")
    result21 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Implement tile rendering and value-based styling",
            "description": "Create renderBoard() to update DOM with current tile positions, apply different colors/styles for each tile value (2, 4, 8... 2048), display numbers. Test Strategy: All tile rendering tests should pass (green phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['render_test']],
        }
    )
    task_ids['render_impl'] = result21.get('id')
    print(f"  Created: {task_ids['render_impl']}")

    # Subtask 22: Game Reset Test
    print("Creating Subtask 22: Game Reset Test...")
    result22 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Write tests for game reset functionality",
            "description": "Create tests for reset button, clearing board state, resetting score (keeping high score), spawning initial tiles. Test Strategy: Tests should fail initially (red phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['render_impl']],
        }
    )
    task_ids['reset_test'] = result22.get('id')
    print(f"  Created: {task_ids['reset_test']}")

    # Subtask 23: Game Reset Implementation
    print("Creating Subtask 23: Game Reset Implementation...")
    result23 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Implement game reset functionality",
            "description": "Implement reset() function to clear board, reset current score, maintain high score, spawn 2 initial tiles, reset game status. Add button click handler. Test Strategy: All game reset tests should pass (green phase).",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['reset_test']],
        }
    )
    task_ids['reset_impl'] = result23.get('id')
    print(f"  Created: {task_ids['reset_impl']}")

    # Subtask 24: Responsive Design Test
    print("Creating Subtask 24: Responsive Design Test...")
    result24 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Write tests for responsive design",
            "description": "Create tests for mobile viewport adaptation, touch-friendly button sizes, grid scaling on different screen sizes. Test Strategy: Tests should fail initially (red phase).",
            "priority": 3,
            "parent_id": parent_id,
            "blocks": [task_ids['reset_impl']],
        }
    )
    task_ids['responsive_test'] = result24.get('id')
    print(f"  Created: {task_ids['responsive_test']}")

    # Subtask 25: Responsive Design Implementation
    print("Creating Subtask 25: Responsive Design Implementation...")
    result25 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Implement responsive design for mobile and desktop",
            "description": "Add media queries for mobile/tablet/desktop breakpoints, ensure touch targets are 44x44px minimum, scale grid appropriately, test on multiple viewports. Test Strategy: All responsive design tests should pass (green phase).",
            "priority": 3,
            "parent_id": parent_id,
            "blocks": [task_ids['responsive_test']],
        }
    )
    task_ids['responsive_impl'] = result25.get('id')
    print(f"  Created: {task_ids['responsive_impl']}")

    # Subtask 26: Integration Testing
    print("Creating Subtask 26: Integration Testing...")
    result26 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Create end-to-end integration tests",
            "description": "Write comprehensive integration tests covering full game flow: start game, make moves, merge tiles, score updates, win scenario, lose scenario, reset. Test Strategy: All integration tests should pass, simulating real gameplay.",
            "priority": 2,
            "parent_id": parent_id,
            "blocks": [task_ids['responsive_impl']],
        }
    )
    task_ids['integration'] = result26.get('id')
    print(f"  Created: {task_ids['integration']}")

    # Subtask 27: Polish and Optimization
    print("Creating Subtask 27: Polish and Optimization...")
    result27 = await provider.call_mcp_tool(
        server_name="gobby-tasks",
        tool_name="create_task",
        arguments={
            "title": "Polish UI and optimize performance",
            "description": "Add final polish: game title/logo, instructions for first-time players, smooth color transitions, optimize JavaScript for performance, ensure consistent 60fps. Test Strategy: Manual testing confirms smooth UX, no visual glitches, performance profiling shows 60fps.",
            "priority": 3,
            "parent_id": parent_id,
            "blocks": [task_ids['integration']],
        }
    )
    task_ids['polish'] = result27.get('id')
    print(f"  Created: {task_ids['polish']}")

    print(f"\n✅ Created {len(task_ids)} subtasks successfully!")
    print(f"\nTask IDs created:")
    for name, task_id in task_ids.items():
        print(f"  {name}: {task_id}")

    return task_ids


if __name__ == "__main__":
    try:
        task_ids = asyncio.run(create_2048_subtasks())
        print("\n🎉 All subtasks created successfully via MCP tools!")
    except Exception as e:
        print(f"\n❌ Error creating subtasks: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
