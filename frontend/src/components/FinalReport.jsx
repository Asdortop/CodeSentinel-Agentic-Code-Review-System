import { useState } from 'react'
import FindingCard from './FindingCard'

const SEVERITY_ORDER = { Critical: 0, High: 1, Medium: 2, Low: 3 }

export default function FinalReport({ report, repoUrl }) {
  const [filter, setFilter] = useState('All')

  const {
    repo_name,
    summary,
    total_critical,
    total_high,
    total_medium,
    total_low,
    findings = [],
    verified_fixes = [],
  } = report

  // Build fix lookup
  const fixMap = {}
  for (const vf of verified_fixes) {
    fixMap[vf.finding_id] = vf
  }

  const filters = ['All', 'Critical', 'High', 'Medium', 'Low']
  const filtered = findings
    .filter(f => filter === 'All' || f.severity === filter)
    .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 4) - (SEVERITY_ORDER[b.severity] ?? 4))

  const totalIssues = total_critical + total_high + total_medium + total_low

  return (
    <div style={{ animation: 'fadeSlideUp 0.4s ease' }}>
      {/* Repo Header */}
      <div className="repo-header">
        <div className="repo-name">
          📁
          <a href={repoUrl} target="_blank" rel="noopener noreferrer">
            {repo_name}
          </a>
        </div>
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          {totalIssues} total issue{totalIssues !== 1 ? 's' : ''} found
        </div>
      </div>

      {/* Severity Stats */}
      <div className="stats-row">
        {[
          { label: 'Critical', count: total_critical },
          { label: 'High', count: total_high },
          { label: 'Medium', count: total_medium },
          { label: 'Low', count: total_low },
        ].map(({ label, count }) => (
          <div key={label} className={`stat-card stat-${label}`}>
            <div className="stat-number">{count}</div>
            <div className="stat-label">{label}</div>
          </div>
        ))}
      </div>

      {/* Executive Summary */}
      {summary && (
        <div className="executive-summary">
          <h3>Executive Summary</h3>
          <p>{summary}</p>
        </div>
      )}

      {/* Findings */}
      <div className="findings-section">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.875rem' }}>
          <h3 style={{ margin: 0 }}>Findings</h3>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            {filtered.length} of {findings.length}
          </div>
        </div>

        {/* Filter row */}
        <div className="filter-row">
          {filters.map(f => (
            <button
              key={f}
              className={`filter-btn ${filter === f ? 'active' : ''}`}
              onClick={() => setFilter(f)}
            >
              {f}
              {f !== 'All' && (
                <span style={{ marginLeft: 5, opacity: 0.75 }}>
                  {f === 'Critical' ? total_critical :
                   f === 'High' ? total_high :
                   f === 'Medium' ? total_medium : total_low}
                </span>
              )}
            </button>
          ))}
        </div>

        {filtered.length === 0 ? (
          <div className="no-findings">
            <div className="no-findings-icon">✨</div>
            <h3>{filter === 'All' ? 'No issues found!' : `No ${filter} severity issues`}</h3>
          </div>
        ) : (
          filtered.map(finding => (
            <FindingCard
              key={finding.id}
              finding={finding}
              verifiedFix={fixMap[finding.id] || null}
            />
          ))
        )}
      </div>
    </div>
  )
}
