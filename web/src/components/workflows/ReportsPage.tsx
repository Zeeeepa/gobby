import { useState, useCallback } from 'react'
import { ReportingTab } from './ReportingTab'
import './PipelinesPage.css'

export function ReportsPage({ projectId }: { projectId?: string }) {
  const [searchText, setSearchText] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [refreshing, setRefreshing] = useState(false)

  const handleRefresh = useCallback(() => {
    setRefreshing(true)
    setRefreshKey(k => k + 1)
    setTimeout(() => setRefreshing(false), 600)
  }, [])

  return (
    <main className="workflows-page">
      <div className="workflows-toolbar">
        <div className="workflows-toolbar-left">
          <h2 className="workflows-toolbar-title">Reports</h2>
        </div>
        <div className="workflows-tab-row-right">
          <input
            className="workflows-search"
            type="text"
            placeholder="Search executions..."
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
          />
          <button
            type="button"
            className={`workflows-toolbar-btn ${refreshing ? 'workflows-toolbar-btn--spinning' : ''}`}
            onClick={handleRefresh}
            title="Refresh"
          >
            &#x21bb;
          </button>
        </div>
      </div>

      <ReportingTab
        searchText={searchText}
        projectId={projectId}
        refreshKey={refreshKey}
      />
    </main>
  )
}
