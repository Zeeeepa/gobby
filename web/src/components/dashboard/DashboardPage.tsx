import { useState } from 'react'
import { useDashboard } from '../../hooks/useDashboard'
import { cn } from '../../lib/utils'
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
          <div className="flex items-center gap-2">
            <div className="flex rounded-md border border-border text-xs">
              <button
                className={cn(
                  'px-2 py-1 rounded-l-md transition-colors',
                  projectScope === 'current'
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:bg-muted',
                )}
                onClick={() => setProjectScope('current')}
              >
                Current Project
              </button>
              <button
                className={cn(
                  'px-2 py-1 rounded-r-md transition-colors',
                  projectScope === 'all'
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:bg-muted',
                )}
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
