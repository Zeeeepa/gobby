import { useCallback, useEffect, useRef } from 'react'
import { cn } from '../../../lib/utils'

interface ResizeHandleProps {
  onResize: (width: number) => void
  panelWidth: number
  minWidth?: number
  maxWidth?: number
}

export function ResizeHandle({ onResize, panelWidth, minWidth = 300, maxWidth = 800 }: ResizeHandleProps) {
  const isDragging = useRef(false)
  const startX = useRef(0)
  const startWidth = useRef(0)

  const cleanupRef = useRef<(() => void) | null>(null)

  const startDrag = useCallback((clientX: number) => {
    isDragging.current = true
    startX.current = clientX
    startWidth.current = panelWidth

    const handleMove = (x: number) => {
      if (!isDragging.current) return
      const delta = startX.current - x
      const newWidth = Math.max(minWidth, Math.min(maxWidth, startWidth.current + delta))
      onResize(newWidth)
    }

    const handleMouseMove = (ev: MouseEvent) => handleMove(ev.clientX)
    const handleTouchMove = (ev: TouchEvent) => { ev.preventDefault(); handleMove(ev.touches[0].clientX) }

    const handleEnd = () => {
      isDragging.current = false
      cleanupRef.current = null
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleEnd)
      document.removeEventListener('touchmove', handleTouchMove)
      document.removeEventListener('touchend', handleEnd)
    }

    cleanupRef.current = handleEnd

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleEnd)
    document.addEventListener('touchmove', handleTouchMove, { passive: false })
    document.addEventListener('touchend', handleEnd)
  }, [onResize, panelWidth, minWidth, maxWidth])

  // Cleanup drag listeners if component unmounts mid-drag
  useEffect(() => {
    return () => { cleanupRef.current?.() }
  }, [])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    startDrag(e.clientX)
  }, [startDrag])

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    e.preventDefault()
    startDrag(e.touches[0].clientX)
  }, [startDrag])

  return (
    <div
      className={cn(
        'w-1 cursor-col-resize hover:bg-accent/50 active:bg-accent transition-colors shrink-0',
        'relative group'
      )}
      onMouseDown={handleMouseDown}
      onTouchStart={handleTouchStart}
    >
      <div className="absolute inset-y-0 -left-1 -right-1" />
    </div>
  )
}
