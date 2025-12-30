#!/usr/bin/env python3
"""
Create subtasks for 2048 game implementation using direct database access.

This script creates all 27 subtasks for the 2048 game following TDD principles.
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from gobby.storage.database import LocalDatabase
from gobby.storage.tasks import LocalTaskManager
from gobby.storage.task_dependencies import TaskDependencyManager


def create_2048_subtasks():
    """Create all subtasks for the 2048 game."""

    # Initialize managers
    db = LocalDatabase()
    task_manager = LocalTaskManager(db)
    dep_manager = TaskDependencyManager(db)

    parent_id = "gt-54b44a"

    # Get the project_id from the parent task
    parent_task = task_manager.get_task(parent_id)
    if not parent_task:
        print(f"Error: Parent task {parent_id} not found!")
        return {}

    project_id = parent_task.project_id

    # Track created task IDs for dependency wiring
    task_ids = {}

    print("Creating 2048 game subtasks...")
    print(f"Parent task: {parent_id}")
    print(f"Project ID: {project_id}\n")

    # Subtask 1: Project Setup
    print("Creating Subtask 1: Project Setup...")
    t1 = task_manager.create_task(
        project_id=project_id,
        title="Create project file structure",
        description="Set up the basic project directory structure and files: index.html, styles.css, game.js, README.md, and tests/ directory. Test Strategy: Verify all files and directories exist with correct names.",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
    )
    task_ids['setup'] = t1.id
    print(f"  Created: {t1.id} - {t1.title}")

    # Subtask 2: HTML Structure Test
    print("Creating Subtask 2: HTML Structure Test...")
    t2 = task_manager.create_task(
        project_id=project_id,
        title="Write tests for HTML game board structure",
        description="Create tests to verify the HTML contains proper grid structure, score display, game status elements, and restart button. Test Strategy: Tests should fail initially (red phase).",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
    )
    task_ids['html_test'] = t2.id
    dep_manager.add_dependency(t2.id, t1.id, "blocks")
    print(f"  Created: {t2.id} - {t2.title}")

    # Subtask 3: HTML Implementation
    print("Creating Subtask 3: HTML Implementation...")
    t3 = task_manager.create_task(
        project_id=project_id,
        title="Implement HTML game board structure",
        description="Create the HTML markup with 4x4 grid container, score display, game status area, and restart button. Use semantic HTML5. Test Strategy: All HTML structure tests should pass (green phase).",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
    )
    task_ids['html_impl'] = t3.id
    dep_manager.add_dependency(t3.id, t2.id, "blocks")
    print(f"  Created: {t3.id} - {t3.title}")

    # Subtask 4: CSS Grid Layout Test
    print("Creating Subtask 4: CSS Grid Layout Test...")
    t4 = task_manager.create_task(
        project_id=project_id,
        title="Write tests for CSS grid layout",
        description="Create tests to verify the 4x4 grid layout, tile positioning, responsive design breakpoints. Test Strategy: Tests should fail initially (red phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['css_test'] = t4.id
    dep_manager.add_dependency(t4.id, t3.id, "blocks")
    print(f"  Created: {t4.id} - {t4.title}")

    # Subtask 5: CSS Grid Implementation
    print("Creating Subtask 5: CSS Grid Implementation...")
    t5 = task_manager.create_task(
        project_id=project_id,
        title="Implement CSS grid layout and base styles",
        description="Style the 4x4 grid using CSS Grid or Flexbox, implement responsive design for mobile and desktop, add base tile styles. Test Strategy: All CSS layout tests should pass (green phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['css_impl'] = t5.id
    dep_manager.add_dependency(t5.id, t4.id, "blocks")
    print(f"  Created: {t5.id} - {t5.title}")

    # Subtask 6: Game State Test
    print("Creating Subtask 6: Game State Test...")
    t6 = task_manager.create_task(
        project_id=project_id,
        title="Write tests for game state management",
        description="Create tests for game board initialization, tile data structure, game state tracking (playing/won/lost). Test Strategy: Tests should fail initially (red phase).",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
    )
    task_ids['state_test'] = t6.id
    dep_manager.add_dependency(t6.id, t5.id, "blocks")
    print(f"  Created: {t6.id} - {t6.title}")

    # Subtask 7: Game State Implementation
    print("Creating Subtask 7: Game State Implementation...")
    t7 = task_manager.create_task(
        project_id=project_id,
        title="Implement game state management",
        description="Create GameState class/object to manage 4x4 board array, current score, game status. Initialize empty board. Test Strategy: All game state tests should pass (green phase).",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
    )
    task_ids['state_impl'] = t7.id
    dep_manager.add_dependency(t7.id, t6.id, "blocks")
    print(f"  Created: {t7.id} - {t7.title}")

    # Subtask 8: Tile Spawning Test
    print("Creating Subtask 8: Tile Spawning Test...")
    t8 = task_manager.create_task(
        project_id=project_id,
        title="Write tests for tile spawning logic",
        description="Create tests for spawning tiles in random empty positions, 90% probability of 2 and 10% probability of 4, initial game start with 2 tiles. Test Strategy: Tests should fail initially (red phase).",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
    )
    task_ids['spawn_test'] = t8.id
    dep_manager.add_dependency(t8.id, t7.id, "blocks")
    print(f"  Created: {t8.id} - {t8.title}")

    # Subtask 9: Tile Spawning Implementation
    print("Creating Subtask 9: Tile Spawning Implementation...")
    t9 = task_manager.create_task(
        project_id=project_id,
        title="Implement tile spawning logic",
        description="Implement addRandomTile() function that finds empty cells, randomly selects one, and places a tile (90% chance of 2, 10% chance of 4). Test Strategy: All tile spawning tests should pass (green phase).",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
    )
    task_ids['spawn_impl'] = t9.id
    dep_manager.add_dependency(t9.id, t8.id, "blocks")
    print(f"  Created: {t9.id} - {t9.title}")

    # Subtask 10: Movement Logic Test
    print("Creating Subtask 10: Movement Logic Test...")
    t10 = task_manager.create_task(
        project_id=project_id,
        title="Write tests for tile movement and merging",
        description="Create comprehensive tests for moving tiles up/down/left/right, merging identical adjacent tiles, preventing invalid moves. Include edge cases. Test Strategy: Tests should fail initially (red phase).",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
    )
    task_ids['move_test'] = t10.id
    dep_manager.add_dependency(t10.id, t9.id, "blocks")
    print(f"  Created: {t10.id} - {t10.title}")

    # Subtask 11: Movement Logic Implementation
    print("Creating Subtask 11: Movement Logic Implementation...")
    t11 = task_manager.create_task(
        project_id=project_id,
        title="Implement tile movement and merging logic",
        description="Implement move() function for all 4 directions with proper tile sliding, merging logic (identical tiles combine into sum), and score updating. Test Strategy: All movement and merging tests should pass (green phase).",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
    )
    task_ids['move_impl'] = t11.id
    dep_manager.add_dependency(t11.id, t10.id, "blocks")
    print(f"  Created: {t11.id} - {t11.title}")

    # Subtask 12: Input Handling Test
    print("Creating Subtask 12: Input Handling Test...")
    t12 = task_manager.create_task(
        project_id=project_id,
        title="Write tests for keyboard and touch input",
        description="Create tests for arrow key detection, touch/swipe gesture recognition, input validation (prevent moves during animation). Test Strategy: Tests should fail initially (red phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['input_test'] = t12.id
    dep_manager.add_dependency(t12.id, t11.id, "blocks")
    print(f"  Created: {t12.id} - {t12.title}")

    # Subtask 13: Input Handling Implementation
    print("Creating Subtask 13: Input Handling Implementation...")
    t13 = task_manager.create_task(
        project_id=project_id,
        title="Implement keyboard and touch input handlers",
        description="Add event listeners for arrow keys (up/down/left/right) and touch events (touchstart/touchmove/touchend) with swipe detection. Test Strategy: All input handling tests should pass (green phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['input_impl'] = t13.id
    dep_manager.add_dependency(t13.id, t12.id, "blocks")
    print(f"  Created: {t13.id} - {t13.title}")

    # Subtask 14: Score Tracking Test
    print("Creating Subtask 14: Score Tracking Test...")
    t14 = task_manager.create_task(
        project_id=project_id,
        title="Write tests for score tracking",
        description="Create tests for score calculation during merges, high score tracking, localStorage persistence and retrieval. Test Strategy: Tests should fail initially (red phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['score_test'] = t14.id
    dep_manager.add_dependency(t14.id, t13.id, "blocks")
    print(f"  Created: {t14.id} - {t14.title}")

    # Subtask 15: Score Tracking Implementation
    print("Creating Subtask 15: Score Tracking Implementation...")
    t15 = task_manager.create_task(
        project_id=project_id,
        title="Implement score tracking with localStorage",
        description="Implement score increment on merges, maintain high score, persist both scores to localStorage, load on game start. Test Strategy: All score tracking tests should pass (green phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['score_impl'] = t15.id
    dep_manager.add_dependency(t15.id, t14.id, "blocks")
    print(f"  Created: {t15.id} - {t15.title}")

    # Subtask 16: Win/Lose Detection Test
    print("Creating Subtask 16: Win/Lose Detection Test...")
    t16 = task_manager.create_task(
        project_id=project_id,
        title="Write tests for win and lose conditions",
        description="Create tests for detecting 2048 tile (win), detecting no valid moves (lose), continuing after win. Test Strategy: Tests should fail initially (red phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['winlose_test'] = t16.id
    dep_manager.add_dependency(t16.id, t15.id, "blocks")
    print(f"  Created: {t16.id} - {t16.title}")

    # Subtask 17: Win/Lose Detection Implementation
    print("Creating Subtask 17: Win/Lose Detection Implementation...")
    t17 = task_manager.create_task(
        project_id=project_id,
        title="Implement win and lose detection",
        description="Implement checkWin() to detect 2048 tile, checkLose() to verify no empty cells and no valid merges, update game status accordingly. Test Strategy: All win/lose detection tests should pass (green phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['winlose_impl'] = t17.id
    dep_manager.add_dependency(t17.id, t16.id, "blocks")
    print(f"  Created: {t17.id} - {t17.title}")

    # Subtask 18: Animation Test
    print("Creating Subtask 18: Animation Test...")
    t18 = task_manager.create_task(
        project_id=project_id,
        title="Write tests for tile animations",
        description="Create tests for smooth tile movement transitions, merge animations, new tile appearance animation, 60fps performance verification. Test Strategy: Tests should fail initially (red phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['anim_test'] = t18.id
    dep_manager.add_dependency(t18.id, t17.id, "blocks")
    print(f"  Created: {t18.id} - {t18.title}")

    # Subtask 19: Animation Implementation
    print("Creating Subtask 19: Animation Implementation...")
    t19 = task_manager.create_task(
        project_id=project_id,
        title="Implement smooth 60fps tile animations",
        description="Add CSS transitions for tile movement (200-250ms), merge pop effect, new tile scale-in. Use transform and opacity for GPU acceleration. Test Strategy: All animation tests should pass with 60fps performance (green phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['anim_impl'] = t19.id
    dep_manager.add_dependency(t19.id, t18.id, "blocks")
    print(f"  Created: {t19.id} - {t19.title}")

    # Subtask 20: Tile Rendering Test
    print("Creating Subtask 20: Tile Rendering Test...")
    t20 = task_manager.create_task(
        project_id=project_id,
        title="Write tests for tile rendering and styling",
        description="Create tests for rendering tiles with correct values, positions, colors (different colors for different values), tile number display. Test Strategy: Tests should fail initially (red phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['render_test'] = t20.id
    dep_manager.add_dependency(t20.id, t19.id, "blocks")
    print(f"  Created: {t20.id} - {t20.title}")

    # Subtask 21: Tile Rendering Implementation
    print("Creating Subtask 21: Tile Rendering Implementation...")
    t21 = task_manager.create_task(
        project_id=project_id,
        title="Implement tile rendering and value-based styling",
        description="Create renderBoard() to update DOM with current tile positions, apply different colors/styles for each tile value (2, 4, 8... 2048), display numbers. Test Strategy: All tile rendering tests should pass (green phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['render_impl'] = t21.id
    dep_manager.add_dependency(t21.id, t20.id, "blocks")
    print(f"  Created: {t21.id} - {t21.title}")

    # Subtask 22: Game Reset Test
    print("Creating Subtask 22: Game Reset Test...")
    t22 = task_manager.create_task(
        project_id=project_id,
        title="Write tests for game reset functionality",
        description="Create tests for reset button, clearing board state, resetting score (keeping high score), spawning initial tiles. Test Strategy: Tests should fail initially (red phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['reset_test'] = t22.id
    dep_manager.add_dependency(t22.id, t21.id, "blocks")
    print(f"  Created: {t22.id} - {t22.title}")

    # Subtask 23: Game Reset Implementation
    print("Creating Subtask 23: Game Reset Implementation...")
    t23 = task_manager.create_task(
        project_id=project_id,
        title="Implement game reset functionality",
        description="Implement reset() function to clear board, reset current score, maintain high score, spawn 2 initial tiles, reset game status. Add button click handler. Test Strategy: All game reset tests should pass (green phase).",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['reset_impl'] = t23.id
    dep_manager.add_dependency(t23.id, t22.id, "blocks")
    print(f"  Created: {t23.id} - {t23.title}")

    # Subtask 24: Responsive Design Test
    print("Creating Subtask 24: Responsive Design Test...")
    t24 = task_manager.create_task(
        project_id=project_id,
        title="Write tests for responsive design",
        description="Create tests for mobile viewport adaptation, touch-friendly button sizes, grid scaling on different screen sizes. Test Strategy: Tests should fail initially (red phase).",
        parent_task_id=parent_id,
        priority=3,
        task_type="task",
    )
    task_ids['responsive_test'] = t24.id
    dep_manager.add_dependency(t24.id, t23.id, "blocks")
    print(f"  Created: {t24.id} - {t24.title}")

    # Subtask 25: Responsive Design Implementation
    print("Creating Subtask 25: Responsive Design Implementation...")
    t25 = task_manager.create_task(
        project_id=project_id,
        title="Implement responsive design for mobile and desktop",
        description="Add media queries for mobile/tablet/desktop breakpoints, ensure touch targets are 44x44px minimum, scale grid appropriately, test on multiple viewports. Test Strategy: All responsive design tests should pass (green phase).",
        parent_task_id=parent_id,
        priority=3,
        task_type="task",
    )
    task_ids['responsive_impl'] = t25.id
    dep_manager.add_dependency(t25.id, t24.id, "blocks")
    print(f"  Created: {t25.id} - {t25.title}")

    # Subtask 26: Integration Testing
    print("Creating Subtask 26: Integration Testing...")
    t26 = task_manager.create_task(
        project_id=project_id,
        title="Create end-to-end integration tests",
        description="Write comprehensive integration tests covering full game flow: start game, make moves, merge tiles, score updates, win scenario, lose scenario, reset. Test Strategy: All integration tests should pass, simulating real gameplay.",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['integration'] = t26.id
    dep_manager.add_dependency(t26.id, t25.id, "blocks")
    print(f"  Created: {t26.id} - {t26.title}")

    # Subtask 27: Polish and Optimization
    print("Creating Subtask 27: Polish and Optimization...")
    t27 = task_manager.create_task(
        project_id=project_id,
        title="Polish UI and optimize performance",
        description="Add final polish: game title/logo, instructions for first-time players, smooth color transitions, optimize JavaScript for performance, ensure consistent 60fps. Test Strategy: Manual testing confirms smooth UX, no visual glitches, performance profiling shows 60fps.",
        parent_task_id=parent_id,
        priority=3,
        task_type="task",
    )
    task_ids['polish'] = t27.id
    dep_manager.add_dependency(t27.id, t26.id, "blocks")
    print(f"  Created: {t27.id} - {t27.title}")

    print(f"\n✅ Created {len(task_ids)} subtasks successfully!")
    print(f"\nTask IDs created:")
    for name, task_id in task_ids.items():
        print(f"  {name}: {task_id}")

    return task_ids


if __name__ == "__main__":
    try:
        task_ids = create_2048_subtasks()
        print("\n🎉 All subtasks created successfully!")
    except Exception as e:
        print(f"\n❌ Error creating subtasks: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
