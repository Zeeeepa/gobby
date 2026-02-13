# 3D Knowledge Graph Animation Bug — Wall of Shame

## Bug
Toggling animation (play button) in the KnowledgeGraph component causes all node labels (SpriteText) to disappear.

## Baseline Behavior
- `nodePositionUpdate` prop toggles between `undefined` (off) and a callback (on)
- `nodeThreeObject` creates SpriteText labels for each node
- `nodeThreeObjectExtend={false}` — custom object replaces default sphere
- When animation is toggled ON, labels vanish

## Attempt 1: Stable callback ref (FAILED)
**Hypothesis:** Switching `nodePositionUpdate` between `undefined` and a function causes react-force-graph-3d to re-initialize nodes, losing custom sprite objects.

**Change:** Used `useRef` to track `animateIdle` state, made `nodePositionUpdate` a stable `useCallback(fn, [])` that reads from the ref. Always passed it as a prop (never `undefined`). Reset scale to (1,1,1) when not animating.

**Result:** Labels still disappeared. The prop stability didn't help — the root cause is elsewhere.

## Attempt 2: Zero prop changes on toggle
**Hypothesis:** Multiple ForceGraph3D props changing simultaneously (`linkDirectionalParticles` 0↔2, `nodePositionUpdate` undefined↔function, plus callback ref instability) triggers the library to rebuild node objects.

**Change:** Made ALL ForceGraph3D props completely static:
- `nodePositionUpdate` — always passed, stable `useCallback(fn, [])`, reads `animateRef.current`
- `linkDirectionalParticles={2}` — always on (particles are decorative)
- Toggle only affects `controls.autoRotate` via imperative ref + breathing via `animateRef`
- No ForceGraph3D props change when animation is toggled

**Result:** FAILED — labels still disappeared. The hypothesis about prop changes was correct for attempt 1 (stabilizing nodePositionUpdate) but didn't address the real issue. The re-render from `setAnimateIdle` was NOT the problem.

## Attempt 3: Preserve SpriteText dimensional scale (FIXED)
**Root Cause Found:** `three-spritetext` sets `.scale` to text dimensions during construction (`this.scale.set(yScale * canvas.width / canvas.height, yScale, 0)`). The breathing effect did `obj.scale.set(1.06, 1.06, 1.06)`, **overwriting** the sprite's dimensional scale (e.g. `(9, 3, 0)`) with near-unity values — making text ~3-9x smaller and essentially invisible.

**Change:** Capture each sprite's original `.scale` on first animated frame (`obj.__origScale = obj.scale.clone()`), then multiply by the breathing factor instead of replacing. When animation stops, restore the original scale.

```typescript
if (!obj.__origScale) obj.__origScale = obj.scale.clone()
const factor = 1 + Math.sin(t * 1.5 + offset) * 0.06
obj.scale.set(
  obj.__origScale.x * factor,
  obj.__origScale.y * factor,
  obj.__origScale.z * factor
)
```

**Result:** FIXED — labels persist through multiple play/pause toggles, verified with Playwright screenshots.
