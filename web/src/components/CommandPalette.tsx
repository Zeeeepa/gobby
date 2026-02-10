import { useEffect, useRef } from 'react'
import type { CommandInfo } from '../hooks/useSlashCommands'

interface CommandPaletteProps {
  commands: CommandInfo[]
  selectedIndex: number
  onSelect: (command: CommandInfo) => void
}

export function CommandPalette({ commands, selectedIndex, onSelect }: CommandPaletteProps) {
  const listRef = useRef<HTMLDivElement>(null)

  // Scroll selected item into view
  useEffect(() => {
    const list = listRef.current
    if (!list) return
    const selected = list.children[selectedIndex] as HTMLElement | undefined
    selected?.scrollIntoView({ block: 'nearest' })
  }, [selectedIndex])

  if (commands.length === 0) return null

  return (
    <div className="command-palette" ref={listRef}>
      {commands.map((cmd, i) => (
        <div
          key={`${cmd.server}.${cmd.tool}-${cmd.name}`}
          className={`command-item ${i === selectedIndex ? 'command-item-selected' : ''}`}
          onMouseDown={(e) => {
            e.preventDefault() // prevent textarea blur
            onSelect(cmd)
          }}
        >
          <span className="command-name">/{cmd.name}</span>
          <span className="command-brief">{cmd.description}</span>
        </div>
      ))}
    </div>
  )
}
