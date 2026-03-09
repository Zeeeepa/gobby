import type { AdminStatus } from '../../hooks/useDashboard'

interface Props {
  savings: AdminStatus['savings']
}

function formatUsd(value: number): string {
  if (value >= 1) return `$${value.toFixed(2)}`
  if (value >= 0.01) return `$${value.toFixed(3)}`
  if (value > 0) return `$${value.toFixed(4)}`
  return '$0.00'
}

function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}K`
  return String(tokens)
}

const CATEGORY_LABELS: Record<string, string> = {
  compression: 'Compression',
  code_index: 'Code Index',
  discovery: 'Discovery',
  handoff: 'Handoff',
  memory: 'Memory',
}

export function SavingsCard({ savings }: Props) {
  const categories = savings?.categories ?? {}
  const hasSavings = (savings?.today_events ?? 0) > 0

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">Savings</h3>
        {hasSavings && (
          <span className="dash-status-badge dash-status-badge--healthy">
            active
          </span>
        )}
      </div>
      <div className="dash-card-body">
        <div className="dash-stat-grid">
          <div className="dash-stat">
            <span className="dash-stat-value">
              {formatUsd(savings?.today_cost_saved_usd ?? 0)}
            </span>
            <span className="dash-stat-label">Saved Today</span>
          </div>
          <div className="dash-stat">
            <span className="dash-stat-value">
              {formatUsd(savings?.cumulative_cost_saved_usd ?? 0)}
            </span>
            <span className="dash-stat-label">Saved (30d)</span>
          </div>
          <div className="dash-stat">
            <span className="dash-stat-value">
              {formatTokens(savings?.today_tokens_saved ?? 0)}
            </span>
            <span className="dash-stat-label">Tokens Saved</span>
          </div>
          <div className="dash-stat">
            <span className="dash-stat-value">
              {savings?.today_events ?? 0}
            </span>
            <span className="dash-stat-label">Events</span>
          </div>
        </div>
        {Object.keys(categories).length > 0 && (
          <div className="dash-breakdown">
            {Object.entries(categories).map(([cat, data]) => (
              <div key={cat} className="dash-breakdown-row">
                <span className="dash-breakdown-label">
                  {CATEGORY_LABELS[cat] ?? cat}
                </span>
                <span className="dash-breakdown-value">
                  {formatTokens(data.tokens_saved)} tokens
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
