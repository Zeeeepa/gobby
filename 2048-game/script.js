document.addEventListener('DOMContentLoaded', () => {
    const gameBoard = document.getElementById('game-board');
    const scoreDisplay = document.getElementById('score');
    const gameOverDisplay = document.getElementById('game-over');
    const restartButton = document.getElementById('restart-button');
    let board = [];
    let score = 0;

    // Initialize game
    function init() {
        board = [
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0]
        ];
        score = 0;
        scoreDisplay.textContent = score;
        gameOverDisplay.classList.add('hidden');
        gameBoard.innerHTML = '';
        createBoard();
        addRandomTile();
        addRandomTile();
        render();
    }

    // Create board cells
    function createBoard() {
        for (let i = 0; i < 16; i++) {
            const cell = document.createElement('div');
            cell.classList.add('tile-cell'); // Container cell (background)
            // Note: Grid cells are actually defined by board array and rendered as tiles
        }
    }

    // Add random tile (2 or 4) to empty spot
    function addRandomTile() {
        const emptyCells = [];
        for (let r = 0; r < 4; r++) {
            for (let c = 0; c < 4; c++) {
                if (board[r][c] === 0) {
                    emptyCells.push({ r, c });
                }
            }
        }
        if (emptyCells.length > 0) {
            const randomCell = emptyCells[Math.floor(Math.random() * emptyCells.length)];
            board[randomCell.r][randomCell.c] = Math.random() < 0.9 ? 2 : 4;
        }
    }

    // Render the board
    function render() {
        gameBoard.innerHTML = '';
        for (let r = 0; r < 4; r++) {
            for (let c = 0; c < 4; c++) {
                const tileValue = board[r][c];
                const tile = document.createElement('div');
                tile.classList.add('tile');
                if (tileValue > 0) {
                    tile.textContent = tileValue;
                    tile.classList.add(`tile-${tileValue}`);
                }
                gameBoard.appendChild(tile);
            }
        }
    }

    // Slide and merge row logic
    function slide(row) {
        // Filter out zeros
        let filteredRow = row.filter(num => num !== 0);

        // Merge identical adjacent numbers
        for (let i = 0; i < filteredRow.length - 1; i++) {
            if (filteredRow[i] === filteredRow[i+1]) {
                filteredRow[i] *= 2;
                score += filteredRow[i];
                filteredRow[i+1] = 0;
            }
        }

        // Filter out zeros again and pad with zeros
        filteredRow = filteredRow.filter(num => num !== 0);
        while (filteredRow.length < 4) {
            filteredRow.push(0);
        }
        return filteredRow;
    }

    // Move Left
    function moveLeft() {
        let changed = false;
        for (let r = 0; r < 4; r++) {
            let original = [...board[r]];
            board[r] = slide(board[r]);
            if (JSON.stringify(original) !== JSON.stringify(board[r])) {
                changed = true;
            }
        }
        return changed;
    }

    // Move Right (reverse row, slide left, reverse back)
    function moveRight() {
        let changed = false;
        for (let r = 0; r < 4; r++) {
            let original = [...board[r]];
            board[r].reverse();
            board[r] = slide(board[r]);
            board[r].reverse();
            if (JSON.stringify(original) !== JSON.stringify(board[r])) {
                changed = true;
            }
        }
        return changed;
    }

    // Move Up (transpose, move left, transpose back)
    function moveUp() {
        let changed = false;
        for (let c = 0; c < 4; c++) {
            let col = [board[0][c], board[1][c], board[2][c], board[3][c]];
            let original = [...col];
            let newCol = slide(col);
            for (let r = 0; r < 4; r++) {
                board[r][c] = newCol[r];
            }
            if (JSON.stringify(original) !== JSON.stringify(newCol)) {
                changed = true;
            }
        }
        return changed;
    }

    // Move Down (transpose, move right, transpose back)
    function moveDown() {
        let changed = false;
        for (let c = 0; c < 4; c++) {
            let col = [board[0][c], board[1][c], board[2][c], board[3][c]];
            let original = [...col];
            col.reverse();
            let newCol = slide(col);
            newCol.reverse();
            for (let r = 0; r < 4; r++) {
                board[r][c] = newCol[r];
            }
            if (JSON.stringify(original) !== JSON.stringify(newCol)) {
                changed = true;
            }
        }
        return changed;
    }

    // Check if game is over
    function isGameOver() {
        // Check for empty cells
        for (let r = 0; r < 4; r++) {
            for (let c = 0; c < 4; c++) {
                if (board[r][c] === 0) return false;
            }
        }
        // Check for possible merges in rows
        for (let r = 0; r < 4; r++) {
            for (let c = 0; c < 3; c++) {
                if (board[r][c] === board[r][c+1]) return false;
            }
        }
        // Check for possible merges in columns
        for (let c = 0; c < 4; c++) {
            for (let r = 0; r < 3; r++) {
                if (board[r][c] === board[r+1][c]) return false;
            }
        }
        return true;
    }

    // Keyboard events
    document.addEventListener('keydown', (e) => {
        let moved = false;
        if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
            e.preventDefault();
        }

        if (e.key === 'ArrowLeft') moved = moveLeft();
        else if (e.key === 'ArrowRight') moved = moveRight();
        else if (e.key === 'ArrowUp') moved = moveUp();
        else if (e.key === 'ArrowDown') moved = moveDown();

        if (moved) {
            addRandomTile();
            scoreDisplay.textContent = score;
            render();
            if (isGameOver()) {
                gameOverDisplay.classList.remove('hidden');
            }
        }
    });

    restartButton.addEventListener('click', init);

    init();
});
