import { useState } from 'react'
import { useDashboard } from '../../hooks/useDashboard'
import { SystemHealthCard } from './SystemHealthCard'
import { TasksCard } from './TasksCard'
import { SessionsCard } from './SessionsCard'
import { MemoryCard } from './MemoryCard'
import { SavingsCard } from './SavingsCard'
import { UsageCard } from './UsageCard'
import { MetricsChartsCard } from './MetricsChartsCard'
import { TimeRangePills, rangeToHours, type TimeRange } from './TimeRangePills'
import './DashboardPage.css'

function formatTime(date: Date | null): string {
  if (!date) return ''
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function DashboardPage() {
  const { data, isLoading, error, lastUpdated } = useDashboard()
  const [timeRange, setTimeRange] = useState<TimeRange>('all')
  const [projectScope, setProjectScope] = useState<'current' | 'all'>('all')

  const hours = rangeToHours(timeRange)
  const projectId = projectScope === 'current' ? data?.project_id : undefined

  return (
    <main className="dash-page">
      <div className="dash-toolbar">
        <div className="dash-toolbar-left">
          <h2 className="dash-toolbar-title">Dashboard</h2>
        </div>
        <div className="dash-toolbar-right">
          <div className="dash-toolbar-filters">
            <div className="dash-project-toggle">
              <button
                className={`dash-time-range-btn${projectScope === 'current' ? ' dash-time-range-btn--active' : ''}`}
                onClick={() => setProjectScope('current')}
              >
                Current Project
              </button>
              <button
                className={`dash-time-range-btn${projectScope === 'all' ? ' dash-time-range-btn--active' : ''}`}
                onClick={() => setProjectScope('all')}
              >
                All Projects
              </button>
            </div>
            <TimeRangePills value={timeRange} onChange={setTimeRange} />
          </div>
          {lastUpdated && (
            <span className="dash-toolbar-updated">
              Updated {formatTime(lastUpdated)}
            </span>
          )}
        </div>
      </div>

      <div className="dash-content">
        {isLoading && !data ? (
          <div className="dash-loading">Loading dashboard...</div>
        ) : error && !data ? (
          <div className="dash-error">Failed to load: {error.slice(0, 200)}</div>
        ) : data ? (
          <div className="dash-grid">
            {/* Row 1: System + donut cards */}
            <SystemHealthCard data={data} />
            <TasksCard hours={hours} projectId={projectId} />
            <SessionsCard hours={hours} projectId={projectId} />

            {/* Row 2: Savings + Usage + Memory */}
            <SavingsCard hours={hours} projectId={projectId} />
            <UsageCard hours={hours} projectId={projectId} />
            <MemoryCard hours={hours} projectId={projectId} />

            {/* Row 3: Metrics charts (full width) */}
            <MetricsChartsCard />
          </div>
        ) : null}
      </div>
    </main>
  )
}
