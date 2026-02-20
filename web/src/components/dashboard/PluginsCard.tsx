interface Props {
  plugins: { enabled: boolean; loaded: number; handlers: number }
}

export function PluginsCard({ plugins }: Props) {
  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">Plugins</h3>
      </div>
      <div className="dash-card-body">
        <div className="dash-plugin-header">
          <span className={`dash-status-badge dash-status-badge--${plugins.enabled ? 'healthy' : 'degraded'}`}>
            {plugins.enabled ? 'Enabled' : 'Disabled'}
          </span>
        </div>
        <div className="dash-plugin-stats">
          <div className="dash-stat">
            <span className="dash-stat-value">{plugins.loaded}</span>
            <span className="dash-stat-label">Loaded</span>
          </div>
          <div className="dash-stat">
            <span className="dash-stat-value">{plugins.handlers}</span>
            <span className="dash-stat-label">Handlers</span>
          </div>
        </div>
      </div>
    </div>
  )
}
