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
  onItemSelect: (itemId: string) => void
  onClose: () => void
}

export function Sidebar({ items, activeItem, isOpen, onItemSelect, onClose }: SidebarProps) {
  return (
    <>
      {isOpen && <div className="sidebar-overlay" onClick={onClose} />}
      <nav className={`sidebar ${isOpen ? 'open' : ''}`}>
        <div className="sidebar-nav">
          {items.map((item) => (
            <React.Fragment key={item.id}>
              {item.separator && <hr className="sidebar-separator" />}
              <button
                className={`sidebar-item ${activeItem === item.id ? 'active' : ''}`}
                onClick={() => {
                  onItemSelect(item.id)
                  onClose()
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
