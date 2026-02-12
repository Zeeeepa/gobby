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

**Result:** PENDING — testing needed
