import { useState } from 'react'
import { useSavings, savingsRangeToDays } from '../../hooks/useSavings'
import { TimeRangePills, type TimeRange } from './TimeRangePills'

const RANGE_LABELS: Record<TimeRange, string> = {
  '24h': 'Last 24h',
  '7d': 'Last 7d',
  '30d': 'Last 30d',
  'all': 'All Time',
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
}

export function SavingsCard() {
  const [range, setRange] = useState<TimeRange>('24h')
  const { data } = useSavings(savingsRangeToDays(range))

  const categories = data?.categories ?? {}
  const hasSavings = (data?.total_events ?? 0) > 0

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">Savings</h3>
        <TimeRangePills value={range} onChange={setRange} />
      </div>
      <div className="dash-card-body">
        <div className="dash-stat-grid">
          <div className="dash-stat">
            <span className="dash-stat-value">
              {formatUsd(data?.total_cost_saved_usd ?? 0)}
            </span>
            <span className="dash-stat-label">Saved ({RANGE_LABELS[range]})</span>
          </div>
          <div className="dash-stat">
            <span className="dash-stat-value">
              {formatTokens(data?.total_tokens_saved ?? 0)}
            </span>
            <span className="dash-stat-label">Tokens Saved</span>
          </div>
          <div className="dash-stat">
            <span className="dash-stat-value">
              {data?.total_events ?? 0}
            </span>
            <span className="dash-stat-label">Events</span>
          </div>
        </div>
        {hasSavings && (
          <span className="dash-status-badge dash-status-badge--healthy" style={{ marginTop: 8 }}>
            active
          </span>
        )}
        {Object.keys(categories).length > 0 && (
          <div className="dash-breakdown">
            {Object.entries(categories).map(([cat, catData]) => (
              <div key={cat} className="dash-breakdown-row">
                <span className="dash-breakdown-label">
                  {CATEGORY_LABELS[cat] ?? cat}
                </span>
                <span className="dash-breakdown-value">
                  {formatTokens(catData.tokens_saved)} tokens
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
