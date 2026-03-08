# Shift+Enter Fuckery

Tracking the saga of getting shift+enter to work properly.

## Problem
Shift+Enter is not producing a newline in Claude Code CLI. Instead it submits/interrupts.

## Environment
- Terminal: tmux
- Shell: zsh
- Platform: macOS (Darwin 25.3.0)
- App: Antigravity (VS Code fork)

## Root Cause (likely)
tmux eats the Shift+Enter escape sequence. It just sees Enter and submits.

## Fix Options

### Option 1: tmux keybind passthrough
Add to `~/.tmux.conf`:
```
bind-key -n S-Enter send-keys Escape "[13;2u"
```
Then: `tmux source-file ~/.tmux.conf`

### Option 2: Extended keys (modern terminals)
Add to `~/.tmux.conf`:
```
set -s extended-keys on
set -as terminal-features 'xterm*:extkeys'
```

### Option 3: Claude Code keybindings
Create `~/.claude/keybindings.json` to remap newline to a different key combo.

## Status
- [ ] Waiting to confirm which terminal emulator is in use
- [ ] Apply fix
- [ ] Verify shift+enter works
