import type { ScanResult } from '../hooks/useSkills'

interface SkillScanPanelProps {
  result: ScanResult
}

function severityClass(severity: string): string {
  switch (severity.toUpperCase()) {
    case 'CRITICAL': return 'skill-scan-severity--critical'
    case 'HIGH': return 'skill-scan-severity--high'
    case 'MEDIUM': return 'skill-scan-severity--medium'
    case 'LOW': return 'skill-scan-severity--low'
    default: return 'skill-scan-severity--info'
  }
}

export function SkillScanPanel({ result }: SkillScanPanelProps) {
  return (
    <div className="skill-scan-panel">
      <div className="skill-scan-header">
        <span className={`skill-scan-badge ${result.is_safe ? 'skill-scan-badge--safe' : 'skill-scan-badge--unsafe'}`}>
          {result.is_safe ? 'SAFE' : 'UNSAFE'}
        </span>
        <span className="skill-scan-meta">
          {result.findings_count} finding{result.findings_count !== 1 ? 's' : ''} &middot; {result.scan_duration_seconds}s
        </span>
      </div>

      {result.findings.length > 0 && (
        <div className="skill-scan-findings">
          {result.findings.map((f, i) => (
            <div key={i} className="skill-scan-finding">
              <div className="skill-scan-finding-header">
                <span className={`skill-scan-severity ${severityClass(f.severity)}`}>
                  {f.severity}
                </span>
                <span className="skill-scan-finding-title">{f.title}</span>
              </div>
              {f.description && <p className="skill-scan-finding-desc">{f.description}</p>}
              {f.remediation && (
                <p className="skill-scan-finding-remediation">
                  <strong>Fix:</strong> {f.remediation}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
