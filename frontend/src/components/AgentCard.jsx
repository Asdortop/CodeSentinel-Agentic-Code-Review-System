import { useState } from 'react'

const AGENT_ICONS = {
  RepoFetcher: '📦',
  PlannerAgent: '🗺️',
  SecurityAgent: '🔒',
  QualityAgent: '⚗️',
  DependencyAgent: '📦',
  CriticAgent: '🎯',
  FixSuggesterAgent: '✏️',
  ReEvaluatorAgent: '🔄',
}

const AGENT_COLORS = {
  RepoFetcher: '#6c63ff',
  PlannerAgent: '#a855f7',
  SecurityAgent: '#ef4444',
  QualityAgent: '#f97316',
  DependencyAgent: '#eab308',
  CriticAgent: '#10b981',
  FixSuggesterAgent: '#3b82f6',
  ReEvaluatorAgent: '#ec4899',
}

export default function AgentCard({ event }) {
  const [expanded, setExpanded] = useState(true)
  const { agent, status, message, timestamp, multi_iteration_count } = event
  const icon = AGENT_ICONS[agent] || '🤖'
  const color = AGENT_COLORS[agent] || 'var(--accent)'

  return (
    <div className={`agent-card status-${status}`}>
      <div className="agent-card-header" onClick={() => setExpanded(e => !e)}>
        {/* Agent icon */}
        <div style={{
          width: 28,
          height: 28,
          borderRadius: 6,
          background: `${color}20`,
          border: `1px solid ${color}40`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 13,
          flexShrink: 0,
        }}>
          {icon}
        </div>

        <span className="agent-name">{agent}</span>

        {/* Status indicator */}
        <div className="agent-status-icon">
          {status === 'running' && <div className="spinner" style={{ borderTopColor: color }} />}
          {status === 'complete' && <span className="check-icon">✓</span>}
          {status === 'error' && <span className="error-icon">✗</span>}
        </div>

        {/* Chip */}
        <span className={`agent-chip chip-${status}`}>
          {status}
        </span>

        {/* Expand arrow */}
        <span style={{
          color: 'var(--text-muted)',
          fontSize: 12,
          transition: 'var(--transition)',
          transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
        }}>▶</span>
      </div>

      {expanded && (
        <div className="agent-card-body">
          <div className="agent-message">{message}</div>

          {/* Re-evaluator iteration badge */}
          {agent === 'ReEvaluatorAgent' && event.verified_count !== undefined && (
            <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <span style={{
                fontSize: '0.72rem',
                color: 'var(--success)',
                background: 'var(--success-bg)',
                border: '1px solid var(--success-border)',
                padding: '2px 8px',
                borderRadius: 20,
                fontWeight: 600,
              }}>
                ✓ {event.verified_count} verified
              </span>
              {event.multi_iteration_count > 0 && (
                <span className="agent-iter-badge">
                  🔄 {event.multi_iteration_count} required 2nd iteration
                </span>
              )}
            </div>
          )}

          {/* Planner plan display */}
          {agent === 'PlannerAgent' && event.plan && (
            <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.375rem', flexWrap: 'wrap' }}>
              {event.plan.agents_to_invoke?.map(a => (
                <span key={a} style={{
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  padding: '2px 8px',
                  borderRadius: 20,
                  background: 'var(--accent-dim)',
                  color: 'var(--accent-bright)',
                  border: '1px solid var(--border-accent)',
                  textTransform: 'capitalize',
                }}>
                  {a}
                </span>
              ))}
            </div>
          )}

          {/* Finding count */}
          {event.finding_count !== undefined && (
            <div style={{ marginTop: '0.5rem' }}>
              <span style={{
                fontSize: '0.72rem',
                fontWeight: 600,
                color: event.finding_count > 0 ? 'var(--high)' : 'var(--success)',
                background: event.finding_count > 0 ? 'var(--high-bg)' : 'var(--success-bg)',
                border: `1px solid ${event.finding_count > 0 ? 'var(--high-border)' : 'var(--success-border)'}`,
                padding: '2px 8px',
                borderRadius: 20,
              }}>
                {event.finding_count} finding{event.finding_count !== 1 ? 's' : ''}
              </span>
            </div>
          )}

          {timestamp && (
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
              {new Date(timestamp).toLocaleTimeString()}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
