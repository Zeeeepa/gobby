import { useState } from 'react'
import { TabBar } from '../shared/TabBar'
import { FilesTab } from '../activity/FilesTab'
import { CodeGraphExplorer } from '../code-graph/CodeGraphExplorer'
import './CodePage.css'

interface CodePageProps {
  projectId: string | null
}

const TABS = [
  { id: 'editor', label: 'File Editor' },
  { id: 'graph', label: 'Code Graph' },
]

type CodeTab = 'editor' | 'graph'

export function CodePage({ projectId }: CodePageProps) {
  const [activeTab, setActiveTab] = useState<CodeTab>('editor')

  return (
    <div className="code-page">
      <div className="code-page-header">
        <TabBar
          tabs={TABS}
          activeTab={activeTab}
          onTabChange={(id) => setActiveTab(id as CodeTab)}
        />
      </div>
      <div className="code-page-content">
        {activeTab === 'editor' && (
          <FilesTab projectId={projectId} />
        )}
        {activeTab === 'graph' && (
          <CodeGraphExplorer projectId={projectId} />
        )}
      </div>
    </div>
  )
}
