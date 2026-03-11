---
name: playwright
description: "Browser automation via Playwright CLI. Use when asked to test, screenshot, interact with, or automate a web page."
category: tools
triggers: playwright, browser, screenshot, web test, automate browser, click element, page snapshot
metadata:
  gobby:
    audience: all
    format_overrides:
      autonomous: full
---

# /gobby:playwright - Playwright CLI Browser Automation

Token-efficient browser automation using `playwright-cli`. Runs commands via shell instead of MCP, using ~4x fewer tokens.

## Prerequisites

Playwright CLI must be installed globally:

```bash
npm install -g @playwright/cli@latest
playwright-cli install --skills
```

This is done automatically by `gobby install`.

## Quick Start

```bash
# Open a page and get a snapshot with element references
playwright-cli open https://example.com
playwright-cli snapshot

# Interact using element refs from the snapshot (e.g., e21, e35)
playwright-cli click e21
playwright-cli fill e14 "hello world"
playwright-cli screenshot
```

## Core Commands

### Navigation

| Command | Description |
|---|---|
| `open [url]` | Launch browser, optionally navigate to URL |
| `goto <url>` | Navigate to URL |
| `go-back` | Go back |
| `go-forward` | Go forward |
| `reload` | Reload page |
| `close` | Close current page |

### Snapshots & Screenshots

| Command | Description |
|---|---|
| `snapshot [ref]` | Compact YAML snapshot with element refs (e1, e2...) |
| `snapshot --filename=f` | Save snapshot to file |
| `screenshot [ref]` | Screenshot page or element |
| `screenshot --filename=f` | Save screenshot to file |
| `pdf --filename=f` | Export page as PDF |

### Interaction

| Command | Description |
|---|---|
| `click <ref> [button]` | Click element |
| `dblclick <ref> [button]` | Double-click element |
| `fill <ref> <text>` | Fill text into input |
| `type <text>` | Type into focused element |
| `hover <ref>` | Hover over element |
| `select <ref> <val>` | Select dropdown option |
| `check <ref>` | Check checkbox/radio |
| `uncheck <ref>` | Uncheck checkbox/radio |
| `upload <file>` | Upload file(s) |
| `drag <startRef> <endRef>` | Drag between elements |

### Keyboard & Mouse

| Command | Description |
|---|---|
| `press <key>` | Press key (e.g., `Enter`, `Tab`, `a`) |
| `keydown <key>` | Key down |
| `keyup <key>` | Key up |
| `mousemove <x> <y>` | Move mouse to coordinates |
| `mousewheel <dx> <dy>` | Scroll |

### Tabs

| Command | Description |
|---|---|
| `tab-list` | List open tabs |
| `tab-new [url]` | Open new tab |
| `tab-select <index>` | Switch to tab |
| `tab-close [index]` | Close tab |

### Sessions

| Command | Description |
|---|---|
| `-s=name <cmd>` | Run command in named session |
| `-s=name close` | Close named session |
| `list` | List active sessions |
| `close-all` | Close all browsers |
| `show` | Open visual monitoring dashboard |

### Storage & Cookies

| Command | Description |
|---|---|
| `state-save [filename]` | Save browser state |
| `state-load <filename>` | Load browser state |
| `cookie-list [--domain]` | List cookies |
| `cookie-set <name> <val>` | Set cookie |
| `cookie-clear` | Clear all cookies |
| `localstorage-get <key>` | Get localStorage value |
| `localstorage-set <k> <v>` | Set localStorage value |

### DevTools

| Command | Description |
|---|---|
| `console [min-level]` | List console messages |
| `network` | List network requests |
| `run-code <code>` | Execute Playwright code snippet |
| `tracing-start` / `tracing-stop` | Record trace |
| `video-start` / `video-stop` | Record video |
| `resize <w> <h>` | Resize browser window |

### Network Mocking

| Command | Description |
|---|---|
| `route <pattern> [opts]` | Mock network requests |
| `route-list` | List active routes |
| `unroute [pattern]` | Remove route(s) |

## Configuration

Default config: `.playwright/cli.config.json`

```json
{
  "browser": {
    "browserName": "chromium",
    "launchOptions": {},
    "contextOptions": {}
  },
  "outputDir": "./playwright-output",
  "network": {
    "allowedOrigins": [],
    "blockedOrigins": []
  },
  "timeouts": {
    "action": 5000,
    "navigation": 30000
  }
}
```

Use `--config path/to/config.json` to specify a custom config file.

## Flags

| Flag | Description |
|---|---|
| `--headed` | Show browser window (default is headless) |
| `--browser=<name>` | chromium, firefox, or webkit |
| `--persistent` | Persist profile to disk |
| `--profile=<path>` | Custom profile directory |

## Workflow: Test a Page

```bash
# 1. Open the page
playwright-cli open https://myapp.localhost:3000

# 2. Take a snapshot to see element refs
playwright-cli snapshot

# 3. Interact using refs from the snapshot
playwright-cli fill e14 "user@example.com"
playwright-cli fill e18 "password123"
playwright-cli click e22

# 4. Verify the result
playwright-cli snapshot
playwright-cli screenshot --filename=after-login.png
```

## Tips

- **Always snapshot first** to get element references before interacting
- **Headless by default** — add `--headed` to `open` to watch it run
- **Named sessions** (`-s=myapp`) keep browser state across commands
- **Run via Bash tool** — all commands are shell commands, not MCP calls
- Use `PLAYWRIGHT_CLI_SESSION=name` env var to set default session
