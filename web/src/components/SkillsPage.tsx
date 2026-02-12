import { useState, useCallback, useMemo } from 'react'
import { useSkills } from '../hooks/useSkills'
import type { GobbySkill } from '../hooks/useSkills'
import { SkillsOverview } from './SkillsOverview'
import { SkillsFilters } from './SkillsFilters'
import { SkillsTable } from './SkillsTable'
import { SkillDetail } from './SkillDetail'
import { SkillForm } from './SkillForm'
import type { SkillFormData } from './SkillForm'
import { SkillHubBrowser } from './SkillHubBrowser'
import { SkillImportModal } from './SkillImportModal'

function InstalledIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <line x1="3" y1="3" x2="11" y2="3" />
      <line x1="3" y1="7" x2="11" y2="7" />
      <line x1="3" y1="11" x2="11" y2="11" />
    </svg>
  )
}

function HubIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="7" cy="7" r="5.5" />
      <line x1="7" y1="1.5" x2="7" y2="12.5" />
      <path d="M1.5 7h11" />
      <path d="M2.5 3.5Q7 5.5 11.5 3.5" />
      <path d="M2.5 10.5Q7 8.5 11.5 10.5" />
    </svg>
  )
}

type ViewMode = 'installed' | 'hub'
type OverviewFilter = 'total' | 'enabled' | 'bundled' | 'hubs' | null

export function SkillsPage() {
  const {
    skills,
    stats,
    isLoading,
    filters,
    setFilters,
    createSkill,
    updateSkill,
    deleteSkill,
    toggleSkill,
    searchSkills,
    importSkill,
    exportSkill,
    restoreDefaults,
    scanSkill,
    refreshSkills,
    hubs,
    hubResults,
    fetchHubs,
    searchHub,
    installFromHub,
  } = useSkills()

  const [viewMode, setViewMode] = useState<ViewMode>('installed')
  const [showForm, setShowForm] = useState(false)
  const [editSkill, setEditSkill] = useState<GobbySkill | null>(null)
  const [selectedSkill, setSelectedSkill] = useState<GobbySkill | null>(null)
  const [overviewFilter, setOverviewFilter] = useState<OverviewFilter>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [searchText, setSearchText] = useState('')
  const [showImport, setShowImport] = useState(false)
  const [sourceTypeFilter, setSourceTypeFilter] = useState<string | null>(null)
  const [installing, setInstalling] = useState<string | null>(null)

  const showError = useCallback((msg: string) => {
    setErrorMessage(msg)
    setTimeout(() => setErrorMessage(null), 4000)
  }, [])

  // Apply overview filter + search + source type filter to skills
  const filteredSkills = useMemo(() => {
    let result = skills

    if (overviewFilter === 'enabled') {
      result = result.filter(s => s.enabled)
    } else if (overviewFilter === 'bundled') {
      result = result.filter(s => s.source_type === 'filesystem')
    } else if (overviewFilter === 'hubs') {
      result = result.filter(s => s.hub_name !== null)
    }

    if (sourceTypeFilter) {
      result = result.filter(s => s.source_type === sourceTypeFilter)
    }

    if (searchText) {
      const q = searchText.toLowerCase()
      result = result.filter(s =>
        s.name.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q)
      )
    }

    return result
  }, [skills, overviewFilter, searchText, sourceTypeFilter])

  const handleCreate = useCallback(() => {
    setEditSkill(null)
    setShowForm(true)
  }, [])

  const handleEdit = useCallback((skill: GobbySkill) => {
    setSelectedSkill(null)
    setEditSkill(skill)
    setShowForm(true)
  }, [])

  const handleSave = useCallback(async (data: SkillFormData) => {
    try {
      if (editSkill) {
        await updateSkill(editSkill.id, data)
      } else {
        await createSkill(data)
      }
      setShowForm(false)
      setEditSkill(null)
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Failed to save skill')
    }
  }, [editSkill, createSkill, updateSkill, showError])

  const handleDelete = useCallback(async (skillId: string) => {
    const ok = await deleteSkill(skillId)
    if (!ok) showError('Failed to delete skill')
    if (selectedSkill?.id === skillId) setSelectedSkill(null)
  }, [deleteSkill, showError, selectedSkill])

  const handleToggle = useCallback(async (skillId: string, enabled: boolean) => {
    const ok = await toggleSkill(skillId, enabled)
    if (!ok) showError('Failed to toggle skill')
  }, [toggleSkill, showError])

  const handleExport = useCallback(async (skillId: string) => {
    const result = await exportSkill(skillId)
    if (result) {
      // Create download
      const blob = new Blob([result.content], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = result.filename || 'SKILL.md'
      a.click()
      URL.revokeObjectURL(url)
    }
  }, [exportSkill])

  const handleImport = useCallback(async (source: string) => {
    const result = await importSkill(source)
    if (!result || result.imported === 0) {
      throw new Error('No skills imported')
    }
  }, [importSkill])

  const handleRestore = useCallback(async () => {
    const result = await restoreDefaults()
    if (result) {
      refreshSkills()
    }
  }, [restoreDefaults, refreshSkills])

  const handleSearch = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value
    setSearchText(val)
    if (val.trim()) {
      searchSkills(val)
    } else {
      refreshSkills()
    }
  }, [searchSkills, refreshSkills])

  const handleCategoryChange = useCallback((cat: string | null) => {
    setFilters(prev => ({ ...prev, category: cat }))
  }, [setFilters])

  const handleClearFilters = useCallback(() => {
    setFilters(prev => ({ ...prev, category: null }))
    setSourceTypeFilter(null)
    setOverviewFilter(null)
  }, [setFilters])

  const handleHubInstall = useCallback(async (hubName: string, slug: string) => {
    const key = `${hubName}/${slug}`
    setInstalling(key)
    try {
      await installFromHub(hubName, slug)
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Install failed')
    } finally {
      setInstalling(null)
    }
  }, [installFromHub, showError])

  return (
    <main className="skills-page">
      {errorMessage && (
        <div className="skills-error-toast" onClick={() => setErrorMessage(null)}>
          {errorMessage}
        </div>
      )}

      {/* Toolbar */}
      <div className="skills-toolbar">
        <div className="skills-toolbar-left">
          <h2 className="skills-toolbar-title">Skills</h2>
          <span className="skills-toolbar-count">{stats?.total ?? 0}</span>
        </div>
        <div className="skills-toolbar-right">
          <div className="skills-view-toggle">
            <button
              className={`skills-view-btn ${viewMode === 'installed' ? 'skills-view-btn--active' : ''}`}
              onClick={() => setViewMode('installed')}
              title="Installed"
            >
              <InstalledIcon />
            </button>
            <button
              className={`skills-view-btn ${viewMode === 'hub' ? 'skills-view-btn--active' : ''}`}
              onClick={() => setViewMode('hub')}
              title="Hub"
            >
              <HubIcon />
            </button>
          </div>

          {viewMode === 'installed' && (
            <input
              className="skills-search"
              type="text"
              value={searchText}
              onChange={handleSearch}
              placeholder="Search..."
            />
          )}

          <button className="skills-toolbar-btn" onClick={refreshSkills} title="Refresh">&#x21bb;</button>

          {viewMode === 'installed' && (
            <>
              <button className="skills-toolbar-btn" onClick={() => setShowImport(true)} title="Import">
                <ImportIcon />
              </button>
              <button className="skills-toolbar-btn" onClick={handleRestore} title="Restore Defaults">
                <RestoreIcon />
              </button>
              <button className="skills-new-btn" onClick={handleCreate}>+ New</button>
            </>
          )}
        </div>
      </div>

      {/* Installed View */}
      {viewMode === 'installed' && (
        <>
          <SkillsOverview
            stats={stats}
            activeFilter={overviewFilter}
            onFilter={(f) => setOverviewFilter(f as OverviewFilter)}
          />

          <SkillsFilters
            stats={stats}
            category={filters.category}
            sourceType={sourceTypeFilter}
            onCategoryChange={handleCategoryChange}
            onSourceTypeChange={setSourceTypeFilter}
            onClear={handleClearFilters}
          />

          <div className="skills-content">
            {isLoading ? (
              <div className="skills-loading">Loading skills...</div>
            ) : (
              <SkillsTable
                skills={filteredSkills}
                onSelect={setSelectedSkill}
                onToggle={handleToggle}
                onEdit={handleEdit}
                onDelete={handleDelete}
              />
            )}
          </div>
        </>
      )}

      {/* Hub View */}
      {viewMode === 'hub' && (
        <div className="skills-content">
          <SkillHubBrowser
            hubs={hubs}
            hubResults={hubResults}
            onFetchHubs={fetchHubs}
            onSearch={searchHub}
            onInstall={handleHubInstall}
            installing={installing}
          />
        </div>
      )}

      {/* Detail slide-out */}
      {selectedSkill && (
        <SkillDetail
          skill={selectedSkill}
          onClose={() => setSelectedSkill(null)}
          onEdit={handleEdit}
          onExport={handleExport}
          onScan={scanSkill}
        />
      )}

      {/* Create/Edit modal */}
      {showForm && (
        <SkillForm
          skill={editSkill}
          onSave={handleSave}
          onCancel={() => { setShowForm(false); setEditSkill(null) }}
        />
      )}

      {/* Import modal */}
      {showImport && (
        <SkillImportModal
          onImport={handleImport}
          onClose={() => setShowImport(false)}
        />
      )}
    </main>
  )
}

function ImportIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}

function RestoreIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="1 4 1 10 7 10" />
      <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
    </svg>
  )
}
