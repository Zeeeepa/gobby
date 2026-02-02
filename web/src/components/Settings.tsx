import type { Settings } from '../hooks/useSettings'

interface SettingsProps {
  isOpen: boolean
  onClose: () => void
  settings: Settings
  onFontSizeChange: (size: number) => void
  onReset: () => void
}

export function Settings({
  isOpen,
  onClose,
  settings,
  onFontSizeChange,
  onReset,
}: SettingsProps) {
  if (!isOpen) return null

  return (
    <>
      <div className="settings-overlay" onClick={onClose} />
      <div className="settings-panel">
        <div className="settings-header">
          <h2>Settings</h2>
          <button className="close-button" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="settings-content">
          <div className="setting-item">
            <label htmlFor="font-size">
              Font Size: {settings.fontSize}px
            </label>
            <input
              id="font-size"
              type="range"
              min="12"
              max="48"
              step="1"
              value={settings.fontSize}
              onChange={(e) => onFontSizeChange(Number(e.target.value))}
              className="slider"
            />
            <div className="slider-labels">
              <span>12px</span>
              <span>48px</span>
            </div>
          </div>

          <div className="settings-actions">
            <button className="reset-button" onClick={onReset}>
              Reset to Defaults
            </button>
          </div>
        </div>
      </div>
    </>
  )
}

// Settings icon SVG
export function SettingsIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
    </svg>
  )
}
