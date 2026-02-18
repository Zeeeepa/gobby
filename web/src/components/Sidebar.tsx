import React from 'react'

interface NavItem {
  id: string
  label: string
  icon: React.ReactNode
  separator?: boolean
}

interface SidebarProps {
  items: NavItem[]
  activeItem: string
  isOpen: boolean
  pinned: boolean
  onItemSelect: (itemId: string) => void
  onClose: () => void
  onTogglePin: () => void
}

export function Sidebar({ items, activeItem, isOpen, pinned, onItemSelect, onClose, onTogglePin }: SidebarProps) {
  return (
    <>
      {isOpen && !pinned && <div className="sidebar-overlay" onClick={onClose} />}
      <nav className={`sidebar ${isOpen ? 'open' : ''} ${pinned ? 'pinned' : ''}`}>
        <div className="sidebar-header">
          <button
            type="button"
            className="sidebar-collapse-btn"
            onClick={onClose}
            aria-label="Collapse menu"
          >
            <CollapseIcon />
          </button>
          <button
            type="button"
            className="sidebar-pin-btn"
            onClick={onTogglePin}
            aria-label={pinned ? 'Unpin sidebar' : 'Pin sidebar'}
            title={pinned ? 'Unpin sidebar' : 'Pin sidebar'}
          >
            <PinIcon pinned={pinned} />
          </button>
        </div>
        <div className="sidebar-nav">
          {items.map((item) => (
            <React.Fragment key={item.id}>
              {item.separator && <hr className="sidebar-separator" />}
              <button
                className={`sidebar-item ${activeItem === item.id ? 'active' : ''}`}
                onClick={() => {
                  onItemSelect(item.id)
                  if (!pinned) onClose()
                }}
              >
                <span className="sidebar-item-icon">{item.icon}</span>
                <span className="sidebar-item-label">{item.label}</span>
              </button>
            </React.Fragment>
          ))}
        </div>
      </nav>
    </>
  )
}

function CollapseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="11 17 6 12 11 7" />
      <polyline points="18 17 13 12 18 7" />
    </svg>
  )
}

function PinIcon({ pinned }: { pinned: boolean }) {
  if (pinned) {
    // Filled pin (pinned state)
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 2l0 4" />
        <path d="M8 6h8l-1 8h-6z" />
        <path d="M9 14l-1 8" />
        <path d="M15 14l1 8" />
      </svg>
    )
  }
  // Outline pin (unpinned state) - rotated 45deg to look "loose"
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ transform: 'rotate(45deg)' }}>
      <path d="M12 2l0 4" />
      <path d="M8 6h8l-1 8h-6z" />
      <path d="M9 14l-1 8" />
      <path d="M15 14l1 8" />
    </svg>
  )
}
