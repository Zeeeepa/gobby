#!/usr/bin/env python3
"""Script to create subtasks for 2048 game implementation."""

import asyncio
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from gobby.storage.tasks import LocalTaskManager
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.config.db import get_db_connection


async def create_subtasks():
    """Create all subtasks for the 2048 game."""
    # Initialize managers
    db = get_db_connection()
    task_manager = LocalTaskManager(db)
    dep_manager = TaskDependencyManager(db)

    parent_id = "gt-54b44a"

    # Track created task IDs for dependency wiring
    task_ids = {}

    # Phase 1: Project Setup and Structure (non-coding tasks)
    print("Creating Phase 1: Project Setup...")

    t1 = task_manager.create_task(
        project_id="default",
        title="Create project structure and HTML skeleton",
        description="""Create index.html with semantic HTML structure including:
- Viewport meta tag for responsive design
- Game container div
- 4x4 grid container structure
- Score display elements (current score and best score)
- New Game button
- Basic semantic structure ready for styling

**Test Strategy:** Open index.html in browser and verify all elements are present in DOM. Validate HTML with W3C validator.""",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
    )
    task_ids['html'] = t1.id
    print(f"  Created: {t1.id} - {t1.title}")

    t2 = task_manager.create_task(
        project_id="default",
        title="Create base CSS structure and grid layout",
        description="""Create styles.css with:
- CSS reset/normalization
- Responsive grid layout (4x4) using CSS Grid or Flexbox
- Tile positioning system
- Color scheme and typography
- Mobile-first responsive breakpoints
- Smooth transitions setup for animations

**Test Strategy:** Verify grid renders correctly at multiple screen sizes (mobile, tablet, desktop). Check that CSS validates.""",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
    )
    task_ids['css_base'] = t2.id
    dep_manager.add_dependency(t2.id, t1.id, "blocks")
    print(f"  Created: {t2.id} - {t2.title}")

    # Phase 2: Core Game Logic (TDD)
    print("\nCreating Phase 2: Core Game Logic (TDD)...")

    # Test for game state
    t3 = task_manager.create_task(
        project_id="default",
        title="Write tests for game state management",
        description="""Create tests/game-state.test.js with tests for:
- Initial 4x4 grid creation
- Spawning tiles in random empty positions
- Getting/setting tile values
- Checking for empty cells
- Grid state serialization

Use vanilla JavaScript with a simple test runner (or manual console assertions).

**Test Strategy:** Tests should fail initially (red phase) - no implementation exists yet.""",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
        test_strategy="Tests should fail initially (red phase)",
    )
    task_ids['test_state'] = t3.id
    dep_manager.add_dependency(t3.id, t1.id, "blocks")
    print(f"  Created: {t3.id} - {t3.title}")

    # Implement game state
    t4 = task_manager.create_task(
        project_id="default",
        title="Implement game state management",
        description="""Create game.js with GameState class:
- Initialize empty 4x4 grid (2D array or flat array)
- addRandomTile() - spawn 2 or 4 in random empty cell
- getCellValue(row, col) / setCellValue(row, col, value)
- getEmptyCells() - return array of empty positions
- clone() - create deep copy of state

**Test Strategy:** All tests from previous subtask should pass (green phase).""",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
        test_strategy="All game state tests should pass (green phase)",
    )
    task_ids['impl_state'] = t4.id
    dep_manager.add_dependency(t4.id, t3.id, "blocks")
    print(f"  Created: {t4.id} - {t4.title}")

    # Test for tile movement
    t5 = task_manager.create_task(
        project_id="default",
        title="Write tests for tile movement logic",
        description="""Create tests/movement.test.js with tests for:
- Moving tiles up/down/left/right
- Merging adjacent identical tiles (2+2=4, 4+4=8, etc.)
- Multiple merges in single move
- Score calculation from merges
- No movement when grid is stuck in that direction

Test edge cases like:
- Full row merges
- Cascading slides after merge
- No duplicate merges in single move

**Test Strategy:** Tests should fail initially (red phase).""",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
        test_strategy="Tests should fail initially (red phase)",
    )
    task_ids['test_movement'] = t5.id
    dep_manager.add_dependency(t5.id, t4.id, "blocks")
    print(f"  Created: {t5.id} - {t5.title}")

    # Implement tile movement
    t6 = task_manager.create_task(
        project_id="default",
        title="Implement tile movement and merge logic",
        description="""Add to game.js:
- move(direction) - slide all tiles in direction ('up', 'down', 'left', 'right')
- Merge logic: combine adjacent identical tiles
- Track score changes from merges
- Return movement metadata (moved: boolean, score: number)

Algorithm:
1. For each row/column (depending on direction)
2. Filter out zeros, slide tiles together
3. Merge adjacent matching values
4. Add zeros back to fill grid

**Test Strategy:** All movement tests should pass (green phase).""",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
        test_strategy="All movement tests should pass (green phase)",
    )
    task_ids['impl_movement'] = t6.id
    dep_manager.add_dependency(t6.id, t5.id, "blocks")
    print(f"  Created: {t6.id} - {t6.title}")

    # Test for win/lose detection
    t7 = task_manager.create_task(
        project_id="default",
        title="Write tests for win/lose detection",
        description="""Create tests/win-lose.test.js with tests for:
- Win condition: grid contains 2048 tile
- Lose condition: no empty cells AND no valid moves in any direction
- canMove() - check if any direction has valid moves
- Game continues after win (reach 4096, etc.)

**Test Strategy:** Tests should fail initially (red phase).""",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
        test_strategy="Tests should fail initially (red phase)",
    )
    task_ids['test_winlose'] = t7.id
    dep_manager.add_dependency(t7.id, t6.id, "blocks")
    print(f"  Created: {t7.id} - {t7.title}")

    # Implement win/lose detection
    t8 = task_manager.create_task(
        project_id="default",
        title="Implement win/lose detection logic",
        description="""Add to game.js:
- hasWon() - check for 2048 tile
- hasLost() - check if no moves available
- canMove(direction) - simulate move without changing state
- isGameOver() - combine won/lost logic

**Test Strategy:** All win/lose tests should pass (green phase).""",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
        test_strategy="All win/lose tests should pass (green phase)",
    )
    task_ids['impl_winlose'] = t8.id
    dep_manager.add_dependency(t8.id, t7.id, "blocks")
    print(f"  Created: {t8.id} - {t8.title}")

    # Phase 3: UI Integration (TDD)
    print("\nCreating Phase 3: UI Integration...")

    # Test for DOM rendering
    t9 = task_manager.create_task(
        project_id="default",
        title="Write tests for DOM rendering",
        description="""Create tests/renderer.test.js with tests for:
- Render grid state to DOM
- Update tile positions and values
- Clear and re-render entire grid
- Update score display
- Handle tile creation animations

Mock DOM or use jsdom for testing.

**Test Strategy:** Tests should fail initially (red phase).""",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
        test_strategy="Tests should fail initially (red phase)",
    )
    task_ids['test_render'] = t9.id
    dep_manager.add_dependency(t9.id, t8.id, "blocks")
    print(f"  Created: {t9.id} - {t9.title}")

    # Implement DOM rendering
    t10 = task_manager.create_task(
        project_id="default",
        title="Implement DOM rendering and updates",
        description="""Create renderer.js:
- renderGrid(gameState) - create/update tile divs
- Assign CSS classes based on tile value (tile-2, tile-4, etc.)
- Position tiles using CSS Grid or absolute positioning
- updateScore(score, bestScore)
- Add CSS transition hooks for animations

**Test Strategy:** All rendering tests should pass (green phase).""",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
        test_strategy="All rendering tests should pass (green phase)",
    )
    task_ids['impl_render'] = t10.id
    dep_manager.add_dependency(t10.id, t9.id, "blocks")
    print(f"  Created: {t10.id} - {t10.title}")

    # Test for input handling
    t11 = task_manager.create_task(
        project_id="default",
        title="Write tests for input handling",
        description="""Create tests/input.test.js with tests for:
- Arrow key detection (up, down, left, right)
- Touch/swipe gesture detection (start, move, end)
- Prevent default browser scrolling on arrow keys
- Debounce rapid inputs
- Map gestures to directions

**Test Strategy:** Tests should fail initially (red phase).""",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
        test_strategy="Tests should fail initially (red phase)",
    )
    task_ids['test_input'] = t11.id
    dep_manager.add_dependency(t11.id, t10.id, "blocks")
    print(f"  Created: {t11.id} - {t11.title}")

    # Implement input handling
    t12 = task_manager.create_task(
        project_id="default",
        title="Implement keyboard and touch input handlers",
        description="""Create input.js:
- Arrow key event listeners (KeyboardEvent)
- Touch event handlers (touchstart, touchmove, touchend)
- Calculate swipe direction from touch delta
- Prevent default scrolling on game container
- Call game.move(direction) on valid input
- Simple debouncing to prevent double-moves

**Test Strategy:** All input tests should pass (green phase).""",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
        test_strategy="All input tests should pass (green phase)",
    )
    task_ids['impl_input'] = t12.id
    dep_manager.add_dependency(t12.id, t11.id, "blocks")
    print(f"  Created: {t12.id} - {t12.title}")

    # Test for game controller
    t13 = task_manager.create_task(
        project_id="default",
        title="Write tests for game controller logic",
        description="""Create tests/controller.test.js with tests for:
- Initialize new game
- Handle move command (check state change, render update)
- New Game button resets state
- Game loop: move -> add tile -> check win/lose -> render
- No action on invalid moves (no state change)

**Test Strategy:** Tests should fail initially (red phase).""",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
        test_strategy="Tests should fail initially (red phase)",
    )
    task_ids['test_controller'] = t13.id
    dep_manager.add_dependency(t13.id, t12.id, "blocks")
    print(f"  Created: {t13.id} - {t13.title}")

    # Implement game controller
    t14 = task_manager.create_task(
        project_id="default",
        title="Implement game controller and main loop",
        description="""Create controller.js to tie everything together:
- initGame() - create GameState, spawn 2 initial tiles
- onMove(direction) handler:
  1. Attempt move
  2. If valid, add random tile
  3. Check win/lose conditions
  4. Update renderer
  5. Update score display
- resetGame() - clear state and restart
- Wire up input handlers
- Main init() function to start game on page load

**Test Strategy:** All controller tests should pass (green phase).""",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
        test_strategy="All controller tests should pass (green phase)",
    )
    task_ids['impl_controller'] = t14.id
    dep_manager.add_dependency(t14.id, t13.id, "blocks")
    print(f"  Created: {t14.id} - {t14.title}")

    # Phase 4: Animations and Polish
    print("\nCreating Phase 4: Animations and Polish...")

    t15 = task_manager.create_task(
        project_id="default",
        title="Implement tile animations",
        description="""Add CSS animations to styles.css:
- Tile spawn animation (scale from 0 to 1)
- Tile merge animation (pulse/bounce effect)
- Tile slide transitions (smooth movement between cells)
- Use CSS transforms for 60fps performance
- Add appropriate timing functions (ease-out, etc.)

Update renderer.js to trigger animations:
- Add/remove animation classes at appropriate times
- Use requestAnimationFrame for smooth updates

**Test Strategy:** Manually test tile movements, spawns, and merges have smooth animations at 60fps. Check performance in Chrome DevTools.""",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['animations'] = t15.id
    dep_manager.add_dependency(t15.id, t14.id, "blocks")
    print(f"  Created: {t15.id} - {t15.title}")

    t16 = task_manager.create_task(
        project_id="default",
        title="Implement local storage for best score",
        description="""Create storage.js:
- saveBestScore(score) - save to localStorage
- loadBestScore() - retrieve from localStorage, default to 0
- Update on game over if current score > best score
- Display best score in UI alongside current score

Update controller to:
- Load best score on init
- Update and save best score when game ends

**Test Strategy:** Verify best score persists across page refreshes. Test in incognito mode (should start at 0). Clear localStorage and verify reset.""",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['storage'] = t16.id
    dep_manager.add_dependency(t16.id, t14.id, "blocks")
    print(f"  Created: {t16.id} - {t16.title}")

    t17 = task_manager.create_task(
        project_id="default",
        title="Add game over and win overlays",
        description="""Create overlays in HTML and CSS:
- Win overlay: "You Win!" message with continue/restart options
- Lose overlay: "Game Over" message with final score and restart button
- Semi-transparent backdrop
- Smooth fade-in animation

Update controller.js:
- Show win overlay when 2048 reached (allow continue playing)
- Show lose overlay when no moves available
- Wire restart buttons

**Test Strategy:** Manually trigger win condition (set 2048 tile via console) and lose condition (fill board with no matches). Verify overlays appear and restart works.""",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['overlays'] = t17.id
    dep_manager.add_dependency(t17.id, t14.id, "blocks")
    print(f"  Created: {t17.id} - {t17.title}")

    t18 = task_manager.create_task(
        project_id="default",
        title="Add responsive design polish",
        description="""Enhance CSS for better mobile/desktop experience:
- Responsive font sizes (use clamp() or media queries)
- Touch-friendly button sizes (44px minimum)
- Proper spacing for small screens
- Landscape mode optimizations
- Add meta theme-color for mobile browsers
- Ensure game fits in viewport without scrolling

**Test Strategy:** Test on multiple devices and screen sizes (use Chrome DevTools device emulation). Verify responsive breakpoints work correctly at 320px, 768px, 1024px widths.""",
        parent_task_id=parent_id,
        priority=3,
        task_type="task",
    )
    task_ids['responsive'] = t18.id
    dep_manager.add_dependency(t18.id, t2.id, "blocks")
    print(f"  Created: {t18.id} - {t18.title}")

    # Phase 5: Testing and Deployment
    print("\nCreating Phase 5: Testing and Deployment...")

    t19 = task_manager.create_task(
        project_id="default",
        title="Run all tests and verify game functionality",
        description="""Comprehensive testing checklist:
- Run all unit tests (game-state, movement, win-lose, renderer, input, controller)
- Manual gameplay testing: play full games to completion
- Test all input methods: keyboard arrows, touch swipes
- Verify animations are smooth (60fps)
- Test score tracking and best score persistence
- Verify win/lose overlays trigger correctly
- Check responsive design on multiple devices

Document any bugs found and fix them.

**Test Strategy:** All automated tests must pass. Complete at least 3 full games manually without errors. No console errors or warnings.""",
        parent_task_id=parent_id,
        priority=1,
        task_type="task",
    )
    task_ids['testing'] = t19.id
    # This depends on all major features being complete
    dep_manager.add_dependency(t19.id, t15.id, "blocks")
    dep_manager.add_dependency(t19.id, t16.id, "blocks")
    dep_manager.add_dependency(t19.id, t17.id, "blocks")
    dep_manager.add_dependency(t19.id, t18.id, "blocks")
    print(f"  Created: {t19.id} - {t19.title}")

    t20 = task_manager.create_task(
        project_id="default",
        title="Cross-browser compatibility testing",
        description="""Test game in multiple browsers:
- Chrome/Chromium (latest)
- Firefox (latest)
- Safari (desktop and iOS)
- Edge (latest)

Verify:
- All features work identically
- No CSS rendering issues
- Touch events work on mobile Safari
- localStorage works in all browsers
- No JavaScript errors in console

Fix any browser-specific issues found.

**Test Strategy:** Game must work identically in all major browsers. No console errors. All features functional on iOS Safari and Android Chrome.""",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
    )
    task_ids['cross_browser'] = t20.id
    dep_manager.add_dependency(t20.id, t19.id, "blocks")
    print(f"  Created: {t20.id} - {t20.title}")

    t21 = task_manager.create_task(
        project_id="default",
        title="Create README and deployment documentation",
        description="""Create README.md with:
- Project description and features
- How to play instructions
- Local development setup (just open index.html)
- File structure explanation
- Technology stack (vanilla HTML/CSS/JS)
- Browser compatibility list
- Credits and license

Add deployment notes:
- How to deploy to GitHub Pages
- Or any static hosting service

**Test Strategy:** Review README for clarity and completeness. Verify instructions work for a new user.""",
        parent_task_id=parent_id,
        priority=3,
        task_type="task",
    )
    task_ids['docs'] = t21.id
    dep_manager.add_dependency(t21.id, t20.id, "blocks")
    print(f"  Created: {t21.id} - {t21.title}")

    print(f"\n✅ Created {len(task_ids)} subtasks successfully!")
    print(f"Parent task: {parent_id}")

    return task_ids


if __name__ == "__main__":
    asyncio.run(create_subtasks())
