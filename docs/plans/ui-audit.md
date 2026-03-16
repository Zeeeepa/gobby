# UI Design Audit

Prepared for Alex (UI design consultant) — 2026-03-12

---

## 1. Page Screenshots (Dark / Light)

All screenshots captured at 1440x900 viewport. Files in `docs/plans/ui-audit-screenshots/`.

| Page | Dark | Light |
|------|------|-------|
| Chat (main) | [chat-dark.png](ui-audit-screenshots/chat-dark.png) | [chat-light.png](ui-audit-screenshots/chat-light.png) |
| Dashboard | [dashboard-dark.png](ui-audit-screenshots/dashboard-dark.png) | [dashboard-light.png](ui-audit-screenshots/dashboard-light.png) |
| Tasks | [tasks-dark.png](ui-audit-screenshots/tasks-dark.png) | [tasks-light.png](ui-audit-screenshots/tasks-light.png) |
| Sessions | [sessions-dark.png](ui-audit-screenshots/sessions-dark.png) | [sessions-light.png](ui-audit-screenshots/sessions-light.png) |
| Source Control | [source-control-dark.png](ui-audit-screenshots/source-control-dark.png) | [source-control-light.png](ui-audit-screenshots/source-control-light.png) |
| Terminals | [terminals-dark.png](ui-audit-screenshots/terminals-dark.png) | [terminals-light.png](ui-audit-screenshots/terminals-light.png) |
| Workflows | [workflows-dark.png](ui-audit-screenshots/workflows-dark.png) | [workflows-light.png](ui-audit-screenshots/workflows-light.png) |
| MCP Servers | [mcp-dark.png](ui-audit-screenshots/mcp-dark.png) | [mcp-light.png](ui-audit-screenshots/mcp-light.png) |
| Configuration | [configuration-dark.png](ui-audit-screenshots/configuration-dark.png) | [configuration-light.png](ui-audit-screenshots/configuration-light.png) |

---

## 2. Color Inventory

### Theme System

The app uses CSS custom properties on `:root` (dark, default) and `[data-theme="light"]`. Theme is toggled via a `data-theme` attribute on `<html>` and persisted to localStorage + backend API. Supports `dark`, `light`, and `system` (auto-detect via `prefers-color-scheme`).

### Core Theme Variables

| Token | Dark Mode | Light Mode | Role |
|-------|-----------|------------|------|
| `--bg-primary` | `#0a0a0a` | `#ffffff` | Page background |
| `--bg-secondary` | `#141414` | `#f5f5f5` | Card/panel background |
| `--bg-tertiary` | `#1a1a1a` | `#e5e5e5` | Sidebar, header, hover states |
| `--text-primary` | `#e5e5e5` | `#171717` | Body text |
| `--text-secondary` | `#a3a3a3` | `#525252` | Secondary text, labels |
| `--text-muted` | `#737373` | `#a3a3a3` | Muted/disabled text |
| `--accent` | `#3b82f6` | `#2563eb` | Primary accent (blue) |
| `--accent-hover` | `#2563eb` | `#1d4ed8` | Accent hover state |
| `--accent-foreground` | `#ffffff` | `#ffffff` | Text on accent |
| `--border` | `#262626` | `#d4d4d4` | Borders, dividers |
| `--user-bg` | `#1e3a5f` | `#dbeafe` | User message bubble |
| `--assistant-bg` | `#1a1a1a` | `#f5f5f5` | Assistant message bubble |
| `--system-bg` | `#2d1f1f` | `#fef2f2` | System message bubble |
| `--code-bg` | `#0d0d0d` | `#f0f0f0` | Code block background |

### Semantic Colors

| Token | Dark Mode | Light Mode | Role |
|-------|-----------|------------|------|
| `--color-destructive` | `#7f1d1d` | `#fecaca` | Destructive action bg |
| `--color-destructive-foreground` | `#f87171` | `#dc2626` | Destructive action text |
| `--color-error` | `#f87171` | `#dc2626` | Error text |
| `--color-warning` | `#78350f` | `#fef3c7` | Warning bg |
| `--color-warning-foreground` | `#f59e0b` | `#d97706` | Warning text |
| `--color-success` | `#14532d` | `#dcfce7` | Success bg |
| `--color-success-foreground` | `#22c55e` | `#16a34a` | Success text |

### Status Indicator Colors (Hardcoded)

**Connection status:**
| State | Dark BG | Dark FG | Light BG | Light FG |
|-------|---------|---------|----------|----------|
| Connected | `#052e16` | `#4ade80` | `rgba(34,197,94,0.12)` | `#16a34a` |
| Disconnected | `#450a0a` | `#f87171` | `rgba(239,68,68,0.12)` | `#dc2626` |
| Connected (mobile) | `#22c55e` | `#fff` | `#22c55e` | `#fff` |
| Disconnected (mobile) | `#ef4444` | `#fff` | `#ef4444` | `#fff` |

**Session dots:**
| Type | Color |
|------|-------|
| User | `#4ade80` (green) |
| Agent | `#c084fc` (purple) |
| Dead | `#737373` (gray) |

**Session badges:**
| Type | BG | FG |
|------|----|----|
| Agent | `#2e1065` | `#c084fc` |
| Dead | `#292524` | `#737373` |

**Task priority badges:**
| Priority | Dark | Light |
|----------|------|-------|
| P0 (Critical) | `#f87171` | `#dc2626` |
| P1 (High) | `#fbbf24` | `#b45309` |
| P2 (Medium) | `#60a5fa` | `#2563eb` |
| P3 (Low) | `#4ade80` | `#16a34a` |

**MCP server status:**
| State | Color |
|-------|-------|
| Healthy / Connected | `#22c55e` |
| Degraded / Pending | `#f59e0b` |
| Unhealthy / Failed | `#ef4444` |
| Unknown | `#737373` |

**MCP transport badges:**
| Transport | Color |
|-----------|-------|
| Internal | `#8b5cf6` |
| HTTP | `#60a5fa` |
| stdio | `#fbbf24` |
| WebSocket | `#a78bfa` |
| SSE | `#f472b6` |

**Source control badges:**
| Type | BG | FG |
|------|----|----|
| Branch/Worktree (purple) | `#1e1b4b` | `#a78bfa` |
| Added/Ahead (green) | `#052e16` | `#4ade80` |
| Deleted/Behind (red) | `#450a0a` | `#f87171` |
| Modified (amber) | `#451a03` | `#fbbf24` |
| Info (blue) | `#0c4a6e` | `#38bdf8` |
| Muted/default | `#1a1a2e` | `#a3a3a3` |

**Diff viewer:**
| Change | Color |
|--------|-------|
| Added lines | `#4ade80` / `rgba(74,222,128,0.1)` bg |
| Deleted lines | `#f87171` / `rgba(248,113,113,0.1)` bg |
| Renamed files | `#a78bfa` |

### Semi-Transparent Overlays

Widely used rgba variants (selected):
- **Blue** (`#3b82f6`): 0.04, 0.05, 0.06, 0.08, 0.1, 0.12, 0.15, 0.2, 0.22, 0.3, 0.4
- **Red** (`#ef4444`): 0.04, 0.08, 0.1, 0.15, 0.25
- **Green** (`#22c55e`): 0.08, 0.1, 0.12, 0.15, 0.2
- **Amber** (`#f59e0b`): 0.06, 0.08, 0.1, 0.15, 0.3
- **Purple** (`#a855f7`): 0.06, 0.08, 0.1, 0.12
- **Black**: 0.02, 0.1, 0.2, 0.4, 0.5, 0.65
- **White**: 0.02, 0.05, 0.1

### Tailwind Config

`web/tailwind.config.ts` maps all custom colors to CSS variables:
```typescript
colors: {
  background: 'var(--bg-primary)',
  foreground: 'var(--text-primary)',
  muted: { DEFAULT: 'var(--bg-tertiary)', foreground: 'var(--text-secondary)' },
  accent: { DEFAULT: 'var(--accent)', foreground: 'var(--accent-foreground)', hover: 'var(--accent-hover)' },
  border: 'var(--border)',
  destructive: { DEFAULT: 'var(--color-destructive)', foreground: 'var(--color-destructive-foreground)' },
  warning: { DEFAULT: 'var(--color-warning)', foreground: 'var(--color-warning-foreground)' },
  success: { DEFAULT: 'var(--color-success)', foreground: 'var(--color-success-foreground)' },
}
```

### Color Statistics

- **Theme variables**: 22 per theme (44 total)
- **Unique hex colors**: ~80+ distinct values
- **RGBA color families**: 12+ base colors with multiple opacity variants
- **No design token library** — all inline CSS variables

---

## 3. Typography Inventory

### Font Stacks

**Sans-serif (body/UI)** — `--font-sans`:
```
-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif
```

**Monospace (code/terminal)** — `--font-mono`:
```
"SF Mono", "Fira Code", "JetBrains Mono", monospace
```

No custom fonts are loaded — system fonts only. No `@font-face` or Google Fonts imports.

### Base Font Size

`--font-size-base: 16px` (configurable 12–24px in Settings via `useSettings.ts`).

All component sizes are expressed as `calc(var(--font-size-base) * <multiplier>)`, making the entire UI scale with the user's preference.

### Font Size Scale (multipliers of `--font-size-base`)

| Multiplier | Actual (16px base) | Usage | Occurrences |
|------------|-------------------|-------|-------------|
| 0.55–0.6 | 8.8–9.6px | Micro badges, counters | 36 |
| 0.625–0.65 | 10–10.4px | Small badges, PIDs | 61 |
| 0.68–0.7 | 10.9–11.2px | Toggle labels, compact text | 98 |
| 0.75 | 12px | Status pills, timestamps, small labels | **163** |
| 0.8 | 12.8px | Secondary body text, selects | **103** |
| 0.85 | 13.6px | Session names, item text | 78 |
| 0.875–0.9 | 14–14.4px | Sidebar items, descriptions | 50 |
| 1.0 | 16px | Base body text | — |
| 1.05–1.1 | 16.8–17.6px | Section headers | 15 |
| 1.125–1.25 | 18–20px | Page titles, headings | 12 |
| 1.5 | 24px | Large display numbers (dashboard) | rare |

**Observation:** The most heavily used sizes are 0.75 (12px) and 0.8 (12.8px), meaning most UI text is smaller than the 16px base. The text-heavy pages lean small.

### Tailwind Typography Classes (in TSX files)

| Class | Count | Equivalent |
|-------|-------|------------|
| `text-xs` | 61 | 12px |
| `text-sm` | 51 | 14px |
| `text-lg` | 5 | 18px |
| `text-xl` | 1 | 20px |
| `font-mono` | 20 | Monospace stack |
| `font-medium` | 23 | weight 500 |
| `font-semibold` | 12 | weight 600 |
| `font-bold` | 2 | weight 700 |

### Font Weights

| Weight | CSS Occurrences | Usage |
|--------|----------------|-------|
| 600 (semibold) | **151** | Headings, labels, section titles |
| 500 (medium) | **148** | Subheadings, interactive controls |
| 400 (normal) | 5 | Body text (rarely explicit) |
| 700 (bold) | 4 | Rare emphasis |

**Observation:** The 600/500 split dominates. Very little use of 400 (normal) — most text carries visual weight.

### Line Height

| Value | Occurrences | Usage |
|-------|-------------|-------|
| 1.0 | 17 | Compact elements (badges, labels) |
| 1.2–1.3 | 6 | Dashboard numbers, modals |
| 1.4 | **18** | Primary readable content |
| 1.5 | 13 | Form controls, spacious text |
| 1.6 | 4 | Body text (set on `<body>`) |

### Letter Spacing

| Value | Occurrences | Usage |
|-------|-------------|-------|
| 0.03em | 15 | Subtle expansion (body) |
| 0.04em | 10 | Moderate expansion |
| 0.05em | **21** | Most common — labels, status pills |
| 0.5px | 14 | Headings, section titles |

### Inconsistencies Found

1. **Multiple monospace stacks** — Some files use `"SF Mono", "Fira Code", "Cascadia Code", monospace` (with Cascadia Code), others use `"SF Mono", "Fira Code", "JetBrains Mono", monospace` (the `--font-mono` variable). Should be unified.
2. **Mixed units for letter-spacing** — Some use `em` units, others use `px`. Should standardize on one.
3. **Hardcoded px sizes alongside calc-based sizes** — ~200+ direct `px` font-size declarations exist alongside the `calc(var(--font-size-base) * N)` system, meaning those elements won't scale with the user's font-size preference.

---

## 4. Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Framework | React 18.3 + TypeScript 5.6 |
| Build | Vite 6 |
| Styling | Tailwind CSS v4.1 + CSS custom properties + component CSS files |
| Components | Radix UI (Dialog, Select, Tabs, Tooltip) |
| Code Editor | CodeMirror 6 |
| Terminal | xterm.js |
| Charts | Recharts |
| Markdown | react-markdown + react-syntax-highlighter |
| Trees | react-arborist |
| Graphs | react-force-graph (2D/3D), Three.js |
| Class Utils | clsx, tailwind-merge, class-variance-authority |

### Design Philosophy

- Minimalist, token-based (CSS variables)
- No gradients, no heavy animations
- System fonts only (no loading delay)
- Dark mode is the default/primary theme
- Configurable base font size (12–24px)

---

## 5. Josh's Feedback

> *Pending — Josh will add specific complaints about pages/elements here.*

---

## Notes for Alex

- All theme tokens live in `web/src/styles/index.css` (lines 1–52)
- Tailwind config at `web/tailwind.config.ts` is minimal — just maps CSS vars
- Each major component has its own `.css` file (30 total, ~21,700 lines of CSS combined)
- The app has 16 distinct page routes; the 9 captured above are the most-used
- Color scheme is heavily Tailwind-influenced (blue accent, neutral grays) with no custom brand palette yet
