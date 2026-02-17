import type { DiffResult } from '../../hooks/useSourceControl'

interface Props {
  diff: DiffResult
}

export function DiffViewer({ diff }: Props) {
  return (
    <div className="sc-diff">
      {diff.files.length > 0 && (
        <div className="sc-diff__files">
          <h4 className="sc-diff__files-title">
            {diff.files.length} file{diff.files.length !== 1 ? 's' : ''} changed
          </h4>
          <div className="sc-diff__file-list">
            {diff.files.map((f) => (
              <div key={f.path} className="sc-diff__file">
                <span className={`sc-diff__file-status sc-diff__file-status--${f.status}`}>
                  {f.status}
                </span>
                <span className="sc-diff__file-path">{f.path}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {diff.patch && (
        <div className="sc-diff__patch">
          <pre className="sc-diff__patch-content">
            {diff.patch.split('\n').map((line, i) => {
              let className = 'sc-diff__line'
              if (line.startsWith('+') && !line.startsWith('+++')) {
                className += ' sc-diff__line--added'
              } else if (line.startsWith('-') && !line.startsWith('---')) {
                className += ' sc-diff__line--removed'
              } else if (line.startsWith('@@')) {
                className += ' sc-diff__line--hunk'
              } else if (line.startsWith('diff ')) {
                className += ' sc-diff__line--header'
              }
              return (
                <div key={i} className={className}>
                  {line}
                </div>
              )
            })}
          </pre>
        </div>
      )}

      {!diff.patch && diff.files.length === 0 && (
        <p className="sc-text-muted">No differences found</p>
      )}
    </div>
  )
}
