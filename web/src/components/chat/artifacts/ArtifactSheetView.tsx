import { useMemo, useState } from 'react'

interface ArtifactSheetViewProps {
  content: string
}

function parseCSV(text: string): string[][] {
  const rows: string[][] = []
  const lines = text.trim().split(/\r?\n/)
  for (const line of lines) {
    const cells: string[] = []
    let current = ''
    let inQuotes = false
    for (let i = 0; i < line.length; i++) {
      const char = line[i]
      if (inQuotes) {
        if (char === '"' && line[i + 1] === '"') { current += '"'; i++ }
        else if (char === '"') inQuotes = false
        else current += char
      } else {
        if (char === '"') inQuotes = true
        else if (char === ',') { cells.push(current); current = '' }
        else current += char
      }
    }
    cells.push(current)
    rows.push(cells)
  }
  return rows
}

export function ArtifactSheetView({ content }: ArtifactSheetViewProps) {
  const rows = useMemo(() => parseCSV(content), [content])
  const [sortCol, setSortCol] = useState<number | null>(null)
  const [sortAsc, setSortAsc] = useState(true)

  if (rows.length === 0) return <div className="p-4 text-muted-foreground">Empty data</div>

  const headers = rows[0]
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
