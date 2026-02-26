# Gobby Design System

## Brand Identity

### Logo Analysis

The Gobby logo establishes a clear personality:
- **Character**: Green goblin with glasses holding a tablet - *friendly nerd who coordinates complex systems*
- **Motif**: Circuit board radiating outward - *orchestration, connections, data flow*
- **Background**: Black - *dark-first design*

### Color Palette

| Color | Hex | Usage |
|-------|-----|-------|
| **Gobby Green** | `#6CBF47` | Primary actions, success states, ready tasks |
| **Circuit Purple** | `#9B59B6` | Features, epic tasks, agent spawning |
| **Circuit Blue** | `#3498DB` | Information, in-progress, links |
| **Circuit Teal** | `#4ECDC4` | Secondary accents, epic tasks |
| **Background** | `#0C0C0C` | Base background |
| **Surface** | `#161616` | Cards, panels |

### Design Direction

**Primary**: Precision & Density + Utility & Function

This means:
- Information-dense layouts for power users
- Monochrome base with semantic color
- Tight spacing within components
- Dark-first aesthetic
- Keyboard-first interactions

Inspired by: **Linear**, **Raycast**, **GitHub**, **Vercel**

---

## Core Principles

### 1. The 4px Grid

All spacing uses a 4px base:
- `4px` - micro (icon gaps)
- `8px` - tight (within components)
- `12px` - standard (between elements)
- `16px` - comfortable (section padding)
- `24px` - generous (between sections)

### 2. Border-First Elevation

For dark mode, use borders over shadows:
```css
border: 0.5px solid rgba(255, 255, 255, 0.08);
```

Shadows only for modals and dropdowns.

### 3. Semantic Color

Gray builds structure. Color only for:
- **Status** (success, warning, error)
- **Actions** (primary buttons, links)
- **Task types** (bug, feature, epic)
- **Provider** (Claude, Gemini, Codex)

### 4. Typography Hierarchy

| Level | Size | Weight | Use |
|-------|------|--------|-----|
| Headline | 24px | 600 | Page titles |
| Title | 16px | 600 | Card headers |
| Body | 14px | 400 | Default text |
| Label | 12px | 500 | Field labels |
| Caption | 11px | 400 | Timestamps, IDs |

**Monospace for data**: Task IDs, token counts, timestamps, code.

### 5. Consistent Depth

Pick ONE approach:
- **Flat** - Borders only (recommended for TUI parity)
- **Subtle** - Single shadow layer
- **Layered** - Multiple shadows (web only)

---

## Color Tokens

### Status Colors

```
open:        #A0A0A0  (gray)
in_progress: #3498DB  (blue)
blocked:     #E74C3C  (red)
closed:      #6CBF47  (green)
failed:      #E74C3C  (red)
escalated:   #F5A623  (orange)
```

### Task Type Colors

```
bug:     #E74C3C  (red)
feature: #9B59B6  (purple)
task:    #3498DB  (blue)
epic:    #4ECDC4  (teal)
chore:   #666666  (gray)
```

### Provider Colors

```
claude: #D97706  (Anthropic orange)
gemini: #4285F4  (Google blue)
codex:  #00A67E  (OpenAI green)
```

### Memory Type Colors

```
fact:       #4CAF50  (green)
preference: #2196F3  (blue)
pattern:    #FF9800  (orange)
context:    #9C27B0  (purple)
```

---

## Component Patterns

### Cards

```
Background: #161616
Border: 0.5px solid rgba(255, 255, 255, 0.08)
Border Radius: 8px
Padding: 16px
```

### Buttons

**Primary**:
```
Background: #6CBF47
Text: #0C0C0C
Border Radius: 6px
Padding: 8px 16px
Hover: #7DCF58
```

**Secondary**:
```
Background: transparent
Border: 1px solid rgba(255, 255, 255, 0.12)
Text: #FAFAFA
Hover: rgba(255, 255, 255, 0.05)
```

### Badges

```
Background: rgba(color, 0.15)
Text: color
Border Radius: 4px
Padding: 2px 8px
Font Size: 11px
Font Weight: 500
```

### Input Fields

```
Background: #111111
Border: 1px solid rgba(255, 255, 255, 0.08)
Border Radius: 6px
Padding: 8px 12px
Focus Border: #6CBF47
```

---

## TUI Color Mapping

For terminal interfaces, map to ANSI 256:

| Token | ANSI 256 | xterm Name |
|-------|----------|------------|
| Primary Green | 113 | `#87d75f` |
| Purple | 134 | `#af5fd7` |
| Blue | 74 | `#5fafd7` |
| Teal | 80 | `#5fd7d7` |
| Red/Error | 203 | `#ff5f5f` |
| Orange/Warning | 214 | `#ffaf00` |
| Gray/Muted | 244 | `#808080` |
| Background | 233 | `#121212` |
| Surface | 235 | `#262626` |
| Text Primary | 255 | `#eeeeee` |
| Text Secondary | 245 | `#8a8a8a` |

### Rich (Python) Color Mapping

```python
GOBBY_THEME = {
    "primary": "green3",
    "purple": "medium_purple3",
    "blue": "sky_blue2",
    "teal": "cyan3",
    "error": "red1",
    "warning": "orange1",
    "muted": "grey58",
    "success": "green3",
}
```

### Textual CSS Variables

```css
$primary: #6CBF47;
$purple: #9B59B6;
$blue: #3498DB;
$teal: #4ECDC4;
$error: #E74C3C;
$warning: #F5A623;
$background: #0C0C0C;
$surface: #161616;
$text: #FAFAFA;
$text-muted: #666666;
```

---

## Keyboard Shortcuts

Standard mappings for both TUI and Web:

| Shortcut | Action |
|----------|--------|
| `Cmd+K` / `Ctrl+K` | Command palette |
| `T` | Tasks view |
| `S` | Sessions view |
| `A` | Agents view |
| `M` | Memory view |
| `D` | Dashboard/Metrics |
| `W` | Workflows view |
| `N` | New (task/agent) |
| `Enter` | Open/expand |
| `Esc` | Back/close |
| `?` | Help/shortcuts |
| `R` | Refresh |
| `Q` | Quit |

---

## Screen Priority

For MVP, implement in this order:

1. **Task Management** - Kanban view, task details, dependencies
2. **Sessions** - Timeline, context, handoff
3. **Workflows** - Active workflow, step progress
4. **Agents** - Spawn tree, status, cancel
5. **Memory** - Search, graph, cross-refs
6. **Metrics** - Tool usage, latency, cost

---

## Mobile Considerations

For remote agent access from phone:

- **Progressive Web App** with offline support
- **Responsive breakpoints**: 320px (phone), 768px (tablet), 1024px+ (desktop)
- **Touch targets**: Minimum 44px
- **Reduced density** on mobile - prioritize status over details
- **Push notifications** for agent completion
- **Simple actions**: Cancel agent, view status, quick task create

---

## Accessibility

- **Contrast ratios**: WCAG AA minimum (4.5:1 for text)
- **Focus indicators**: 2px green ring on all interactive elements
- **Keyboard navigation**: Full app navigable without mouse
- **Screen reader**: ARIA labels on all controls
- **Reduced motion**: Respect `prefers-reduced-motion`
- **Color-blind safe**: Don't rely solely on color - use icons/labels too

---

## File Structure

```
docs/design/
├── design-system.md      # This file
├── tailwind.config.ts    # Tailwind configuration
├── components/           # Component specifications
│   ├── task-card.md
│   ├── session-row.md
│   └── ...
└── screens/              # Screen wireframes
    ├── task-kanban.md
    ├── session-timeline.md
    └── ...
```
