# 2048 Game - Product Requirements Document

## Overview
Build a browser-based implementation of the popular 2048 puzzle game using vanilla HTML, CSS, and JavaScript. No external frameworks or libraries.

## Game Rules
- 4x4 grid of tiles
- Tiles contain powers of 2 (2, 4, 8, 16, ... 2048)
- Player swipes/uses arrow keys to move all tiles in one direction
- When two tiles with the same number collide, they merge into one tile with double the value
- After each move, a new tile (2 or 4) appears in a random empty cell
- Game ends when no moves are possible (grid full, no adjacent matching tiles)
- Player wins when a 2048 tile is created

## Technical Requirements

### File Structure
```
index.html    - Main HTML page
styles.css    - Game styling
game.js       - Core game logic
```

### Core Features

1. **Game Board Rendering**
   - Render 4x4 grid with CSS Grid
   - Each tile shows its value with distinct background color
   - Smooth animations for tile movement and merging

2. **Input Handling**
   - Arrow key support (Up, Down, Left, Right)
   - Touch/swipe support for mobile
   - Prevent default scroll behavior during gameplay

3. **Game State Management**
   - Track 4x4 grid state as 2D array
   - Track current score (sum of all merged tile values)
   - Track best score (persisted in localStorage)
   - Detect win condition (2048 tile created)
   - Detect lose condition (no valid moves)

4. **Tile Movement Logic**
   - Move all tiles in specified direction
   - Merge adjacent tiles with same value (once per move)
   - Calculate score from merges
   - Spawn new tile after valid move

5. **UI Elements**
   - Current score display
   - Best score display
   - New Game button
   - Game over overlay with final score
   - Win overlay with option to continue

### Visual Design
- Clean, modern look inspired by original 2048
- Tile colors: gradient from light (2) to dark (2048)
- Responsive design for mobile and desktop
- Minimum touch target size of 44x44px

### Performance
- 60fps animations
- No visible lag on tile movements
- Works on mobile devices (iOS Safari, Chrome Android)

## Acceptance Criteria
- [ ] Game loads without errors
- [ ] All four directional moves work correctly
- [ ] Tiles merge correctly (same values only, once per move)
- [ ] Score updates after each merge
- [ ] New tile spawns after each valid move
- [ ] Game detects win at 2048
- [ ] Game detects loss when no moves available
- [ ] New Game button resets the board
- [ ] Best score persists across page reloads
- [ ] Works on mobile with touch/swipe
