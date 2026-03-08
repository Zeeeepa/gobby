class Game2048 {
    constructor() {
        this.gridSize = 4;
        this.container = document.getElementById('tile-container');
        this.scoreDisplay = document.getElementById('score');
        this.gameOverDisplay = document.getElementById('game-over');
        this.setup();
        this.addEventListeners();
    }

    setup() {
        this.grid = Array(this.gridSize).fill().map(() => Array(this.gridSize).fill(0));
        this.score = 0;
        this.updateScore();
        this.container.innerHTML = '';
        this.gameOverDisplay.classList.remove('active');
        this.addRandomTile();
        this.addRandomTile();
        this.render();
    }

    addRandomTile() {
        const emptyCells = [];
        for (let r = 0; r < this.gridSize; r++) {
            for (let c = 0; c < this.gridSize; c++) {
                if (this.grid[r][c] === 0) {
                    emptyCells.push({ r, c });
                }
            }
        }

        if (emptyCells.length > 0) {
            const { r, c } = emptyCells[Math.floor(Math.random() * emptyCells.length)];
            this.grid[r][c] = Math.random() < 0.9 ? 2 : 4;
        }
    }

    render() {
        this.container.innerHTML = '';
        for (let r = 0; r < this.gridSize; r++) {
            for (let c = 0; c < this.gridSize; c++) {
                const value = this.grid[r][c];
                if (value !== 0) {
                    const tile = document.createElement('div');
                    tile.className = `tile tile-${value}`;
                    tile.textContent = value;
                    tile.style.top = `${r * 91.25}px`; // 76.25 + 15
                    tile.style.left = `${c * 91.25}px`;
                    this.container.appendChild(tile);
                }
            }
        }
    }

    updateScore() {
        this.scoreDisplay.textContent = this.score;
    }

    addEventListeners() {
        window.addEventListener('keydown', (e) => {
            let moved = false;
            switch (e.key) {
                case 'ArrowUp':
                    moved = this.moveUp();
                    break;
                case 'ArrowDown':
                    moved = this.moveDown();
                    break;
                case 'ArrowLeft':
                    moved = this.moveLeft();
                    break;
                case 'ArrowRight':
                    moved = this.moveRight();
                    break;
            }

            if (moved) {
                this.addRandomTile();
                this.render();
                if (this.checkWin()) {
                    this.gameOverDisplay.querySelector('p').textContent = 'You Win!';
                    this.gameOverDisplay.classList.add('active');
                } else if (this.isGameOver()) {
                    this.gameOverDisplay.querySelector('p').textContent = 'Game Over!';
                    this.gameOverDisplay.classList.add('active');
                }
            }
        });
    }

    checkWin() {
        for (let r = 0; r < this.gridSize; r++) {
            for (let c = 0; c < this.gridSize; c++) {
                if (this.grid[r][c] === 2048) return true;
            }
        }
        return false;
    }

    moveLeft() {
        let moved = false;
        for (let r = 0; r < this.gridSize; r++) {
            const row = this.grid[r].filter(val => val !== 0);
            for (let i = 0; i < row.length - 1; i++) {
                if (row[i] === row[i + 1]) {
                    row[i] *= 2;
                    this.score += row[i];
                    row.splice(i + 1, 1);
                    moved = true;
                }
            }
            const newRow = row.concat(Array(this.gridSize - row.length).fill(0));
            if (newRow.join(',') !== this.grid[r].join(',')) {
                moved = true;
            }
            this.grid[r] = newRow;
        }
        this.updateScore();
        return moved;
    }

    moveRight() {
        let moved = false;
        for (let r = 0; r < this.gridSize; r++) {
            const row = this.grid[r].filter(val => val !== 0).reverse();
            for (let i = 0; i < row.length - 1; i++) {
                if (row[i] === row[i + 1]) {
                    row[i] *= 2;
                    this.score += row[i];
                    row.splice(i + 1, 1);
                    moved = true;
                }
            }
            const newRow = row.concat(Array(this.gridSize - row.length).fill(0)).reverse();
            if (newRow.join(',') !== this.grid[r].join(',')) {
                moved = true;
            }
            this.grid[r] = newRow;
        }
        this.updateScore();
        return moved;
    }

    moveUp() {
        let moved = false;
        for (let c = 0; c < this.gridSize; c++) {
            let col = [];
            for (let r = 0; r < this.gridSize; r++) {
                if (this.grid[r][c] !== 0) col.push(this.grid[r][c]);
            }

            for (let i = 0; i < col.length - 1; i++) {
                if (col[i] === col[i + 1]) {
                    col[i] *= 2;
                    this.score += col[i];
                    col.splice(i + 1, 1);
                    moved = true;
                }
            }

            const newCol = col.concat(Array(this.gridSize - col.length).fill(0));
            for (let r = 0; r < this.gridSize; r++) {
                if (this.grid[r][c] !== newCol[r]) {
                    moved = true;
                }
                this.grid[r][c] = newCol[r];
            }
        }
        this.updateScore();
        return moved;
    }

    moveDown() {
        let moved = false;
        for (let c = 0; c < this.gridSize; c++) {
            let col = [];
            for (let r = 0; r < this.gridSize; r++) {
                if (this.grid[r][c] !== 0) col.push(this.grid[r][c]);
            }
            col.reverse();

            for (let i = 0; i < col.length - 1; i++) {
                if (col[i] === col[i + 1]) {
                    col[i] *= 2;
                    this.score += col[i];
                    col.splice(i + 1, 1);
                    moved = true;
                }
            }

            const newCol = col.concat(Array(this.gridSize - col.length).fill(0)).reverse();
            for (let r = 0; r < this.gridSize; r++) {
                if (this.grid[r][c] !== newCol[r]) {
                    moved = true;
                }
                this.grid[r][c] = newCol[r];
            }
        }
        this.updateScore();
        return moved;
    }

    isGameOver() {
        // Check for empty cells
        for (let r = 0; r < this.gridSize; r++) {
            for (let c = 0; c < this.gridSize; c++) {
                if (this.grid[r][c] === 0) return false;
            }
        }

        // Check for adjacent same-value cells
        for (let r = 0; r < this.gridSize; r++) {
            for (let c = 0; c < this.gridSize; c++) {
                const val = this.grid[r][c];
                if (r < this.gridSize - 1 && val === this.grid[r + 1][c]) return false;
                if (c < this.gridSize - 1 && val === this.grid[r][c + 1]) return false;
            }
        }

        return true;
    }
}

const game = new Game2048();
