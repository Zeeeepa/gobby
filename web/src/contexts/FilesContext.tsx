import { createContext, useContext } from 'react'
import type { ReactNode } from 'react'
import { useFiles } from '../hooks/useFiles'

type FilesContextValue = ReturnType<typeof useFiles>

const FilesContext = createContext<FilesContextValue | null>(null)

export function FilesProvider({ children }: { children: ReactNode }) {
  const files = useFiles()
  return <FilesContext.Provider value={files}>{children}</FilesContext.Provider>
}

export function useFilesContext(): FilesContextValue {
  const ctx = useContext(FilesContext)
  if (!ctx) throw new Error('useFilesContext must be used within FilesProvider')
  return ctx
}
