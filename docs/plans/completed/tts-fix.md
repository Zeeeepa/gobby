# Fix: TTS crashing React and causing page reload

## Context

TTS audio playback in the web chat UI crashes React, reloading the page. The `useVoice` hook has several compounding issues: a synchronous recursive call chain that can stack overflow, missing unmount guards on state setters, no cleanup on conversation switch, AudioContext exhaustion across mount/unmount cycles, and unbounded queue growth.

## Root Cause (Primary)

`playNextChunk` (line 81-108 in `useVoice.ts`) chains audio playback via `source.onended = playNextChunk`. When AudioContext operations throw, the **catch block calls `playNextChunk()` synchronously** — recursing through every queued chunk without yielding the call stack. A long TTS response with many queued chunks → stack overflow → unrecoverable crash → page reload.

The error boundary in `App.tsx` can't catch this because `onended` callbacks and WebSocket handlers fire outside React's lifecycle.

## Fixes (all in `web/src/hooks/useVoice.ts`)

### Fix 1: Break recursive stack overflow in `playNextChunk` (Critical)

Rewrite the catch block to use `setTimeout(playNextChunk, 0)` instead of direct recursion. Add a consecutive error counter (`playErrorCountRef`) — after 3 consecutive failures, drain the queue and stop. Reset on success.

```typescript
// New ref near line 52:
const playErrorCountRef = useRef(0)

// In playNextChunk catch block (replacing lines 103-107):
} catch (err) {
  console.error('Voice: Failed to play audio chunk:', err)
  playErrorCountRef.current += 1
  if (playErrorCountRef.current >= 3) {
    console.warn('Voice: Too many consecutive playback errors, stopping TTS')
    audioQueueRef.current = []
    isPlayingRef.current = false
    playErrorCountRef.current = 0
    if (mountedRef.current) setIsSpeaking(false)
    return
  }
  setTimeout(playNextChunk, 0)  // break the stack
}
```

### Fix 2: Add `mountedRef` guard on state setters

Add `const mountedRef = useRef(true)` near line 39. Set `mountedRef.current = false` at the top of the unmount cleanup (line 293). Guard all `setIsSpeaking()` calls:
- Lines 85, 92 in `playNextChunk`
- Line 126 in `queueAudioChunk`
- Line 151 in `stopTTS`

Also guard `setIsTranscribing` calls in `onSpeechEnd` (lines 236, 251) and `handleVoiceMessage` (lines 315, 320, 323, 325).

### Fix 3: Stop TTS on conversation change

Add after line 309:
```typescript
useEffect(() => {
  stopTTS()
}, [conversationId, stopTTS])
```
Prevents stale audio from the previous conversation playing after a switch. `stopTTS` already handles full cleanup (queue, source, pendingMeta, backend notification).

### Fix 4: Suspend AudioContext instead of closing it

Change the unmount cleanup (line 304-306) from `audioContextRef.current?.close()` to `audioContextRef.current?.suspend()`. Browsers limit to ~6 concurrent AudioContexts. Closing then recreating exhausts this limit across mount/unmount cycles. Suspending allows reuse — the existing `resume()` logic on line 71-73 already handles waking it up.

### Fix 5: Cap audio queue size

Add backpressure before the queue push (line 125):
```typescript
const MAX_AUDIO_QUEUE_SIZE = 50
// In queueAudioChunk, before push:
while (audioQueueRef.current.length >= MAX_AUDIO_QUEUE_SIZE) {
  audioQueueRef.current.shift()
}
```
50 chunks ≈ 25-50s of buffered audio. Prevents memory exhaustion on long responses.

## Files to modify

- `web/src/hooks/useVoice.ts` — all 5 fixes (single file)

## Verification

1. `cd web && npx vitest run` — existing tests pass
2. Manual: open web chat, trigger a long TTS response, switch conversations mid-playback — no crash
3. Manual: trigger TTS, close/reopen the chat tab several times — no AudioContext errors in console
4. Manual: trigger TTS with backend TTS errors (e.g., kill Kokoro) — graceful degradation, no page reload
