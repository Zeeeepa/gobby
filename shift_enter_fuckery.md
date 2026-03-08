# Shift+Enter Fuckery — RESOLVED

## Problem
Shift+Enter was not producing a newline in Claude Code CLI. Instead it inserted a space.

## Environment
- Terminal: Antigravity built-in terminal (xterm.js based, like VS Code)
- Multiplexer: tmux
- Shell: zsh
- Platform: macOS (Darwin 25.3.0)

## Root Cause
Antigravity's `keybindings.json` had a shift+enter binding that sent `" \n"` (space + newline)
to the terminal via `workbench.action.terminal.sendSequence`. This was intercepting the keypress
before it ever reached tmux or Claude Code.

## Fix Applied

### 1. Antigravity keybindings (the actual fix)
In `~/Library/Application Support/Antigravity/User/keybindings.json`, changed the
`sendSequence` text from `" \n"` to `"\u001b[13;2u"` (CSI u encoded Shift+Enter):

```json
{
    "key": "shift+enter",
    "command": "workbench.action.terminal.sendSequence",
    "args": {
        "text": "\u001b[13;2u"
    },
    "when": "terminalFocus"
}
```

### 2. Claude Code keybindings (belt and suspenders)
Created `~/.claude/keybindings.json` with explicit shift+enter → newline:

```json
{
    "bindings": [{
        "context": "Chat",
        "bindings": { "shift+enter": "chat:newline" }
    }]
}
```

### 3. tmux config (already had extended-keys, removed broken S-Enter bind)
- `extended-keys on` and `xterm*:extkeys` were already present
- Removed a `bind-key -n S-Enter` that was sending a bad escape sequence

## What DIDN'T work
- tmux `bind-key -n S-Enter send-keys Escape "[13;2u"` — caused a space character
- Claude Code keybindings alone — tmux/Antigravity ate the keypress before CC saw it
- tmux extended-keys alone — Antigravity was intercepting before tmux

## Status: FIXED
