# Frontend Style Guide

Design standards, tokens, and patterns for the Gobby web UI.

## Overview

Gobby's frontend is a single-page React application at `web/` built with:

- **React 18** + **TypeScript 5** for components and type safety
- **Vite 6** for builds and dev server
- **Tailwind CSS 4** for utility-first styling
- **Radix UI** for accessible headless primitives (Dialog, Select, Tabs, Tooltip)
- **class-variance-authority (CVA)** for component variant management
- **clsx + tailwind-merge** via the `cn()` utility for class merging

The design philosophy is **minimalist, accessible, and token-based**. No gradients, no heavy animations, no opinionated UI frameworks. Colors are solid, transitions are subtle, and the entire theme is driven by CSS custom properties so dark/light mode switching is instant.

## Design Tokens

All theme values live as CSS custom properties in `web/src/styles/index.css`. Dark mode is the default (`:root`), light mode is applied via the `[data-theme="light"]` selector on `<html>`.

### Core Palette

| Token | Dark | Light | Usage |
|-------|------|-------|-------|
| `--bg-primary` | `#0a0a0a` | `#ffffff` | Page background |
| `--bg-secondary` | `#141414` | `#f5f5f5` | Cards, sidebars, panels |
| `--bg-tertiary` | `#1a1a1a` | `#e5e5e5` | Hover states, muted areas |
| `--text-primary` | `#e5e5e5` | `#171717` | Body text, headings |
| `--text-secondary` | `#a3a3a3` | `#525252` | Secondary labels, descriptions |
| `--text-muted` | `#737373` | `#a3a3a3` | Timestamps, placeholders, hints |
| `--accent` | `#3b82f6` | `#2563eb` | Links, active tabs, primary actions |
| `--accent-hover` | `#2563eb` | `#1d4ed8` | Accent hover state |
| `--accent-foreground` | `#fff` | `#fff` | Text on accent backgrounds |
| `--border` | `#262626` | `#d4d4d4` | All borders and dividers |

### Semantic Colors

These colors communicate status and intent:

| Token | Dark | Light | Usage |
|-------|------|-------|-------|
| `--color-destructive` | `#7f1d1d` | `#fecaca` | Destructive action backgrounds |
| `--color-destructive-foreground` | `#f87171` | `#dc2626` | Destructive action text/icons |
| `--color-error` | `#f87171` | `#dc2626` | Error messages |
| `--color-warning` | `#78350f` | `#fef3c7` | Warning backgrounds |
| `--color-warning-foreground` | `#f59e0b` | `#d97706` | Warning text |
| `--color-success` | `#14532d` | `#dcfce7` | Success backgrounds |
| `--color-success-foreground` | `#22c55e` | `#16a34a` | Success text/icons |

### Message Backgrounds

Chat messages use role-specific backgrounds:

| Token | Dark | Light | Role |
|-------|------|-------|------|
| `--user-bg` | `#1e3a5f` | `#dbeafe` | User messages |
| `--assistant-bg` | `#1a1a1a` | `#f5f5f5` | Assistant messages |
| `--system-bg` | `#2d1f1f` | `#fef2f2` | System/error messages |
| `--code-bg` | `#0d0d0d` | `#f0f0f0` | Code blocks |

### Status Badge Colors

Status badges use color-coded backgrounds with matching foreground text. In dark mode, backgrounds are deep saturated tones. In light mode, use `rgba()` tinted backgrounds at 0.08-0.12 opacity:

| Status | Dark BG | Dark FG | Light BG | Light FG |
|--------|---------|---------|----------|----------|
| Success/Active | `#052e16` | `#4ade80` | `rgba(34, 197, 94, 0.12)` | `#16a34a` |
| Error/Failed | `#450a0a` | `#f87171` | `rgba(239, 68, 68, 0.12)` | `#dc2626` |
| Warning/Pending | `#451a03` | `#fbbf24` | `rgba(245, 158, 11, 0.12)` | `#b45309` |
| Info/Running | `#0c4a6e` | `#38bdf8` | `rgba(59, 130, 246, 0.12)` | `#2563eb` |
| Agent/Purple | `#1e1b4b` | `#a78bfa` | `rgba(139, 92, 246, 0.12)` | `#7c3aed` |

### Layout Tokens

| Token | Value | Notes |
|-------|-------|-------|
| `--sidebar-width` | `260px` | Collapses to `40px` on mobile |
| `--font-size-base` | `16px` | User-adjustable from 12-48px via settings |

## Typography

### Font Stacks

| Purpose | Variable | Stack |
|---------|----------|-------|
| UI text | `--font-sans` | `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` |
| Code | `--font-mono` | `"SF Mono", "Fira Code", "JetBrains Mono", monospace` |

### Size Scale

All sizes are relative to `--font-size-base` using `calc()`:

| Name | Multiplier | ~px at 16px | Usage |
|------|-----------|-------------|-------|
| Micro | `* 0.65` | 10px | Small count badges |
| XS | `* 0.75` | 12px | Uppercase labels, status text |
| SM | `* 0.8` | 13px | Secondary text, metadata |
| Body SM | `* 0.875` | 14px | Standard body text |
| Base | `* 1` | 16px | Default size |
| LG | `* 1.125` | 18px | Section headings |
| XL | `* 1.25` | 20px | Page titles |
| H3 | `1.25em` | — | Rendered markdown H3 |
| H2 | `1.5em` | — | Rendered markdown H2 |
| H1 | `1.75em` | — | Rendered markdown H1 |

In custom CSS, use `calc(var(--font-size-base) * N)`. In Tailwind, use `text-xs`, `text-sm`, `text-base`, `text-lg`.

### Font Weights

| Weight | Value | Usage |
|--------|-------|-------|
| Normal | 400 | Default body text |
| Medium | 500 | Active states, interactive labels |
| Semibold | 600 | Headings, badges, button text |
| Bold | 700 | Strong emphasis |

### Line Heights

| Value | Usage |
|-------|-------|
| 1.2 | Headings, badges |
| 1.4 | Small/secondary text |
| 1.5 | Standard content |
| 1.6 | Body text (set on `body`) |

## Spacing & Layout

Gobby uses Tailwind's default spacing scale (base unit 4px = `1` in Tailwind = `0.25rem`).

### Common Gap Values

| Tailwind | CSS | Usage |
|----------|-----|-------|
| `gap-1.5` | `0.375rem` (6px) | Tight groups (icon + label) |
| `gap-2` | `0.5rem` (8px) | Standard element spacing |
| `gap-3` | `0.75rem` (12px) | Section element spacing |
| `gap-4` | `1rem` (16px) | Section padding, major gaps |
| `gap-6` | `1.5rem` (24px) | Page-level padding |

### Layout Dimensions

| Element | Dimension | Notes |
|---------|-----------|-------|
| Sidebar | `260px` wide | `40px` when collapsed |
| Chat container | `max-width: 900px` | Centered with `margin: 0 auto` |
| Header | `padding: 1rem 1.5rem` | Fixed at top |
| Messages | `padding: 1rem` | Scrollable region |

### Border Radius

| Value | Usage |
|-------|-------|
| `0.25rem` (4px) | Inline code, small elements |
| `0.375rem` (6px) | Small buttons, inputs |
| `0.5rem` (8px) | Cards, messages, containers |
| `9999px` | Pill badges, status indicators |
| `50%` | Circular avatars, dot indicators |

## Components

### UI Primitives

8 shared components live in `web/src/components/chat/ui/`:

#### Button

CVA-based button with variants and sizes.

```tsx
import { Button } from './chat/ui/Button'

<Button variant="primary">Save</Button>
<Button variant="destructive" size="sm">Delete</Button>
<Button variant="ghost" size="icon"><MyIcon /></Button>
<Button variant="outline">Cancel</Button>
```

| Variant | Appearance |
|---------|-----------|
| `default` | Foreground bg, background text (inverted) |
| `primary` | Accent bg, white text |
| `destructive` | Destructive bg + foreground |
| `outline` | Transparent with border |
| `ghost` | Transparent, hover shows muted bg |

| Size | Dimensions |
|------|-----------|
| `sm` | `h-8 px-3 text-xs` |
| `md` | `h-9 px-4` (default) |
| `lg` | `h-10 px-6 text-base` |
| `icon` | `h-9 w-9` (square) |

#### Badge

Status badges with semantic variants.

```tsx
import { Badge } from './chat/ui/Badge'

<Badge variant="success">Connected</Badge>
<Badge variant="error">Failed</Badge>
<Badge variant="warning">Pending</Badge>
<Badge variant="info">Running</Badge>
<Badge>Default</Badge>
```

#### Dialog

Radix-based modal dialog with overlay.

```tsx
import { Dialog, DialogTrigger, DialogContent, DialogTitle, DialogDescription } from './chat/ui/Dialog'

<Dialog>
  <DialogTrigger asChild><Button>Open</Button></DialogTrigger>
  <DialogContent>
    <DialogTitle>Confirm Action</DialogTitle>
    <DialogDescription>Are you sure?</DialogDescription>
    {/* content */}
  </DialogContent>
</Dialog>
```

#### Other Primitives

- **Input** — Standard text input with consistent styling
- **Textarea** — Auto-resizing textarea
- **Select** — Radix-based select with trigger, content, and item components
- **ScrollArea** — Wrapper with custom scrollbar styling
- **Tooltip** — Radix tooltip with provider, trigger, and content

### CVA Pattern

New components that need variants should follow the established CVA pattern:

```tsx
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '../../../lib/utils'

const myVariants = cva(
  'base-classes-shared-by-all-variants',
  {
    variants: {
      variant: {
        default: 'classes-for-default',
        primary: 'classes-for-primary',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        md: 'h-9 px-4',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'md',
    },
  }
)

interface MyComponentProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof myVariants> {}

export function MyComponent({ className, variant, size, ...props }: MyComponentProps) {
  return <div className={cn(myVariants({ variant, size, className }))} {...props} />
}
```

### The `cn()` Utility

Located at `web/src/lib/utils.ts`. Always use it to merge classes:

```tsx
import { cn } from '../../../lib/utils'

// Merges and deduplicates Tailwind classes
<div className={cn('p-4 bg-background', isActive && 'border-accent', className)} />
```

### When to Use What

| Need | Use |
|------|-----|
| Accessible dialog/modal | Radix `Dialog` wrapper in `chat/ui/Dialog.tsx` |
| Accessible select/dropdown | Radix `Select` wrapper in `chat/ui/Select.tsx` |
| Accessible tooltip | Radix `Tooltip` wrapper in `chat/ui/Tooltip.tsx` |
| Tab interface | Radix `Tabs` (imported directly) |
| Simple modal/overlay | Custom CSS overlay (for lightweight cases only) |
| Button with variants | `Button` from `chat/ui/Button.tsx` |
| Status indicator | `Badge` from `chat/ui/Badge.tsx` |

## Styling Approach

### Tailwind-First

Use Tailwind utility classes as the default for all styling:

```tsx
// Good: Tailwind classes
<div className="flex items-center gap-2 p-4 bg-background border border-border rounded-lg">
  <span className="text-sm text-muted-foreground">Label</span>
</div>

// Bad: Custom CSS for basic layout
// .my-container { display: flex; align-items: center; gap: 0.5rem; }
```

### CSS Variables for Theme Values

Reference CSS variables through Tailwind's extended color names:

```tsx
// Good: Tailwind semantic names (mapped to CSS vars in tailwind.config.ts)
<div className="bg-background text-foreground border-border" />
<div className="bg-muted text-muted-foreground" />
<div className="text-accent" />

// Also good: Direct CSS var reference when Tailwind doesn't have a mapping
<div style={{ background: 'var(--user-bg)' }} />

// Bad: Raw hex values
<div className="bg-[#0a0a0a] text-[#e5e5e5]" />
```

### BEM for Feature-Scoped CSS

When Tailwind isn't sufficient (complex selectors, keyframe animations, data-attribute styling), use BEM naming in a co-located CSS file:

```css
/* MyFeature.css */
.my-feature { ... }
.my-feature__header { ... }
.my-feature__item { ... }
.my-feature__item--active { ... }
.my-feature-badge--success { ... }
```

Import the CSS file at the top of the component:

```tsx
import './MyFeature.css'
```

### Light Mode Overrides

Every component that uses hardcoded dark-mode colors must include a light mode override in `web/src/styles/index.css`. The pattern:

```css
/* Default (dark mode) */
.my-status { background: #052e16; color: #4ade80; }

/* Light mode override */
[data-theme="light"] .my-status {
  background: rgba(34, 197, 94, 0.12);
  color: #16a34a;
}
```

Light mode backgrounds use `rgba()` at 0.08-0.12 opacity for a tinted effect, paired with a solid foreground color.

### Tinted Backgrounds

For accent-tinted backgrounds, use `color-mix()`:

```css
background: color-mix(in srgb, var(--accent) 10%, var(--bg-secondary));
```

## Icons

Gobby uses inline SVG components. No icon library is installed.

### Pattern

```tsx
export function SearchIcon({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  )
}
```

### Rules

- `viewBox="0 0 24 24"` standard
- Stroke-based: `fill="none"`, `stroke="currentColor"`, `strokeWidth="2"`
- Use `currentColor` so the icon inherits the parent's `color`
- Default size 12-14px, accept optional `size` prop
- Shared/reusable icons go in `web/src/components/Icons.tsx`
- One-off icons can be defined inline in the component that uses them

## Animation & Transitions

### Standard Timings

| Duration | Easing | Usage |
|----------|--------|-------|
| `0.1s` | `ease` | Quick hover effects (background, color) |
| `0.15s` | `ease` | Standard UI transitions (buttons, tabs, borders) |
| `0.2s` | `ease-out` | Panel/modal entrance, slide-in effects |
| `0.3s` | `ease` | Width transitions, larger layout shifts |

### CSS Transitions

```css
/* Standard hover transition */
.my-element {
  transition: all 0.15s ease;
}

/* Specific properties (better performance) */
.my-element {
  transition: background 0.15s, border-color 0.15s;
}
```

### Radix State-Driven Animations

Radix components use `data-[state=...]` selectors for animations:

```tsx
className="data-[state=open]:animate-in data-[state=closed]:animate-out
           data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
```

### Keyframe Animations

Defined in `web/src/styles/index.css`:

| Name | Duration | Usage |
|------|----------|-------|
| `spin` | 0.8s linear | Loading spinners |
| `pulse` | 1.5s ease-in-out | Tool call indicators |
| `fadeIn` | 0.2s ease | Element appearance |
| `slideIn` | 0.2s ease-out | Panel entrance from right |
| `pulse-recording` | 1.5s ease-in-out | Recording indicator with ring |
| `speaking-wave` | 1.2s ease-in-out | Voice speaking bars |

## Dark/Light Mode

### How It Works

1. User selects theme in Settings (dark, light, or system)
2. `useSettings.ts` stores preference in localStorage + API
3. Theme is applied to `<html>` via `document.documentElement.setAttribute('data-theme', theme)`
4. CSS variables swap values based on the `[data-theme="light"]` selector
5. All Tailwind color classes resolve through CSS variables, so they update automatically

### Adding Theme-Aware Styles

**Option 1: Use CSS variables (preferred)**

```css
.my-component {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border);
}
```

This works in both themes automatically.

**Option 2: Tailwind semantic classes (preferred in JSX)**

```tsx
<div className="bg-muted text-foreground border-border" />
```

**Option 3: Manual overrides (when needed)**

```css
.my-component { background: #1a1a2e; color: #e0e0ff; }
[data-theme="light"] .my-component { background: #f0f0ff; color: #1a1a2e; }
```

Always test both themes when adding new styled elements.

## State Management Patterns

### Hook-First Architecture

State is managed through custom hooks in `web/src/hooks/`. No global state managers are used.

```tsx
// Each hook is self-contained
const { messages, sendMessage, isStreaming } = useChat(sessionId)
const { settings, updateSettings } = useSettings()
const { tasks, createTask } = useTasks(projectId)
```

### Dual Persistence

Settings and some state use a write-through pattern:

1. Write to localStorage immediately (fast, offline-friendly)
2. Write to API best-effort (authoritative, syncs across tabs)
3. On mount, fetch from API and overwrite localStorage

```tsx
// Pattern from useSettings.ts
const saveSettings = (newSettings) => {
  localStorage.setItem('settings', JSON.stringify(newSettings))
  fetch('/api/settings', { method: 'PUT', body: JSON.stringify(newSettings) })
    .catch(console.error) // Best-effort
}
```

### Data Fetching

Direct `fetch()` calls inside `useEffect` or callback functions. No data-fetching library.

```tsx
useEffect(() => {
  fetch(`/api/sessions/${sessionId}`)
    .then(r => r.json())
    .then(setSession)
    .catch(console.error)
}, [sessionId])
```

### Tab Routing

Navigation uses a simple `useState` in `App.tsx`:

```tsx
const [activeTab, setActiveTab] = useState<string>('chat')
```

Pages are lazy-loaded with `React.lazy()` and rendered conditionally:

```tsx
{activeTab === 'chat' ? <ChatPage /> : activeTab === 'tasks' ? <TasksPage /> : ...}
```

## File Organization

```
web/src/
├── components/              # React components (PascalCase)
│   ├── chat/
│   │   ├── ui/             # Shared UI primitives (Button, Badge, Dialog, etc.)
│   │   ├── artifacts/      # Artifact renderers (code, image, text, sheet)
│   │   ├── ChatInput.tsx
│   │   ├── MessageList.tsx
│   │   ├── MessageItem.tsx
│   │   └── styles.css      # Chat-specific styles
│   ├── tasks/              # Task management components
│   ├── agents/             # Agent management components
│   ├── sessions/           # Session management components
│   ├── source-control/     # Git/version control UI
│   ├── command-browser/    # Slash command palette
│   ├── Icons.tsx           # Shared icon components
│   ├── Sidebar.tsx         # Navigation sidebar
│   ├── Settings.tsx        # Settings panel
│   └── <PageName>.tsx      # Top-level page components
├── hooks/                   # Custom React hooks (camelCase)
│   ├── useChat.ts          # Chat state and WebSocket
│   ├── useSettings.ts      # User preferences
│   ├── useTasks.ts         # Task operations
│   └── ...
├── types/                   # TypeScript type definitions
│   ├── chat.ts
│   └── artifacts.ts
├── styles/                  # Global CSS
│   ├── index.css           # Theme tokens, base styles, light mode overrides
│   └── source-control.css
├── lib/                     # Utility functions
│   └── utils.ts            # cn() utility
├── App.tsx                  # Root component, tab routing, lazy loading
└── main.tsx                 # React entry point
```

### Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Component files | PascalCase | `ChatPage.tsx`, `TaskDetail.tsx` |
| Hook files | camelCase with `use` prefix | `useChat.ts`, `useSettings.ts` |
| CSS classes | kebab-case / BEM | `.code-block-header`, `.pipeline-badge--completed` |
| TypeScript types | PascalCase | `ChatMessage`, `TaskCreateDefaults` |
| Functions | camelCase | `handleSubmit`, `fetchDetail` |

### Where to Put New Code

| Creating... | Location |
|-------------|----------|
| Shared UI primitive | `web/src/components/chat/ui/` |
| Feature-specific component | `web/src/components/<feature>/` |
| New page/tab | `web/src/components/<PageName>.tsx` (+ lazy load in `App.tsx`) |
| Custom hook | `web/src/hooks/use<Name>.ts` |
| Shared icon | `web/src/components/Icons.tsx` |
| Global styles | `web/src/styles/index.css` |
| Feature-scoped CSS | Co-located `<Feature>.css` next to the component |
| Type definitions | `web/src/types/` |

## Z-Index Scale

| Z-Index | Layer | Examples |
|---------|-------|---------|
| 1 | Minor overlays | Subtle layering |
| 10 | Panels | Terminal panels, basic modals |
| 20 | Chat overlays | Chat-related floating elements |
| 50 | Sidebars | Sidebar, source control panels |
| 100 | Popovers | Dropdowns, modals, toasts |
| 200 | Full-screen | Full-screen overlays |
| 1000 | Critical | Error toasts, critical modals |

## Anti-Patterns & Common Mistakes

### Do NOT

- **Add new dependencies** without explicit approval — no new UI libraries, state managers, routers, animation libraries, or icon packs
- **Use CSS-in-JS** (styled-components, emotion) — styling is Tailwind + CSS files
- **Use inline styles** except for dynamic computed values (widths, positions)
- **Use raw hex colors** — use CSS variables or Tailwind semantic names
- **Use gradients** — the design uses solid colors exclusively
- **Add React Router** — navigation is tab-based via `useState`
- **Create global state providers** — use custom hooks with local state
- **Use `!important` in CSS** — Tailwind config has `important: true` so utilities already win
- **Skip light mode** — every new themed style needs a `[data-theme="light"]` override
- **Import new icon libraries** — use inline SVGs following the established pattern

### Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using `bg-[#0a0a0a]` | Use `bg-background` |
| Using `text-[#e5e5e5]` | Use `text-foreground` |
| Forgetting light mode | Add `[data-theme="light"]` override |
| Creating a new `<Modal>` | Use the existing Radix `Dialog` wrapper |
| Adding `style={{ color: 'red' }}` | Use `text-destructive-foreground` or `text-[var(--color-error)]` |
| Creating a new global context | Write a custom hook in `hooks/` |
| Using `className="..." + "..."` | Use `cn()` for class merging |
