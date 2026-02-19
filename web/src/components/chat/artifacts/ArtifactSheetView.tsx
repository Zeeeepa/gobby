import { useMemo, useState } from 'react'

interface ArtifactSheetViewProps {
  content: string
}

function parseCSV(text: string): string[][] {
  const rows: string[][] = []
  let cells: string[] = []
  let current = ''
  let inQuotes = false
  const trimmed = text.trim()
  for (let i = 0; i < trimmed.length; i++) {
    const char = trimmed[i]
    if (inQuotes) {
      if (char === '"' && trimmed[i + 1] === '"') { current += '"'; i++ }
      else if (char === '"') inQuotes = false
      else current += char
    } else {
      if (char === '"') inQuotes = true
      else if (char === ',') { cells.push(current); current = '' }
      else if (char === '\r' && trimmed[i + 1] === '\n') { cells.push(current); current = ''; rows.push(cells); cells = []; i++ }
      else if (char === '\n') { cells.push(current); current = ''; rows.push(cells); cells = [] }
      else current += char
    }
  }
  cells.push(current)
  if (cells.length > 0 || current !== '') rows.push(cells)
  return rows
}

export function ArtifactSheetView({ content }: ArtifactSheetViewProps) {
  const rows = useMemo(() => parseCSV(content), [content])
  const [sortCol, setSortCol] = useState<number | null>(null)
  const [sortAsc, setSortAsc] = useState(true)
  const headers = rows.length > 0 ? rows[0] : []
  const data = useMemo(() => rows.slice(1), [rows])
  const sorted = useMemo(() => {
    if (sortCol === null) return data
    return [...data].sort((a, b) => {
      const va = a[sortCol] || ''
      const vb = b[sortCol] || ''
      const cmp = va.localeCompare(vb, undefined, { numeric: true })
      return sortAsc ? cmp : -cmp
    })
  }, [data, sortCol, sortAsc])

  if (rows.length === 0) return <div className="p-4 text-muted-foreground">Empty data</div>

  const handleSort = (col: number) => {
    if (sortCol === col) setSortAsc(!sortAsc)
    else { setSortCol(col); setSortAsc(true) }
  }

  return (
    <div className="h-full overflow-auto">
      <table className="min-w-full border-collapse text-sm">
        <thead className="sticky top-0 bg-muted">
          <tr>
            {headers.map((h, i) => (
              <th
                key={i}
                className="border border-border px-3 py-1.5 text-left text-xs font-medium text-muted-foreground cursor-pointer hover:bg-muted/80"
                onClick={() => handleSort(i)}
              >
                {h}
                {sortCol === i && <span className="ml-1">{sortAsc ? '\u25B2' : '\u25BC'}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, ri) => (
            <tr key={ri} className="hover:bg-muted/30">
              {row.map((cell, ci) => (
                <td key={ci} className="border border-border px-3 py-1 text-foreground">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
