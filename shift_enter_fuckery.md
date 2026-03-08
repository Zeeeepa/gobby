# Shift+Enter Fuckery

Tracking the saga of getting shift+enter to work properly.

## Problem
Shift+Enter is not producing a newline in Claude Code CLI. Instead it submits/interrupts.

## Environment
- Terminal: Antigravity built-in terminal (xterm.js based, like VS Code)
- Multiplexer: tmux
- Shell: zsh
- Platform: macOS (Darwin 25.3.0)

## Root Cause
Two layers are fighting you:

1. **tmux eats the escape sequence.** xterm.js sends Shift+Enter as `\x1b[13;2u` (CSI u encoding), but tmux doesn't pass it through — it just sees Enter and submits.
2. **xterm.js may not even send it.** VS Code/Antigravity's integrated terminal uses xterm.js which may send Shift+Enter as plain `\r` unless configured otherwise.

## Fix — Apply ALL of these

### Step 1: tmux extended keys
Add to `~/.tmux.conf`:
```tmux
# Enable CSI u / kitty keyboard protocol passthrough
set -s extended-keys on
set -as terminal-features 'xterm*:extkeys'
```

### Step 2: tmux Shift+Enter passthrough
Add to `~/.tmux.conf`:
```tmux
# Explicitly pass Shift+Enter through to the application
bind-key -n S-Enter send-keys Escape "[13;2u"
```

### Step 3: Reload tmux
```bash
tmux source-file ~/.tmux.conf
```

### Step 4: If still broken — Claude Code keybindings workaround
Create `~/.claude/keybindings.json`:
```json
[
  {
    "key": "ctrl+j",
    "command": "newline",
    "when": "inputFocused"
  }
]
```
This gives you Ctrl+J as a reliable newline fallback.

## Log
1. Identified problem: shift+enter submits instead of newline
2. Confirmed environment: Antigravity terminal (xterm.js) + tmux
3. Root cause: tmux doesn't pass CSI u sequences by default
4. Fix: extended-keys + explicit S-Enter bind in tmux.conf

## Status
- [x] Identified terminal emulator (Antigravity/xterm.js)
- [ ] Apply tmux.conf changes (Steps 1-3)
- [ ] Verify shift+enter works
- [ ] If not, apply Claude Code keybindings fallback (Step 4)
