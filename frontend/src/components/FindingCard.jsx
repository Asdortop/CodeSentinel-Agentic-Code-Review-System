import { useState } from 'react'
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter'
import { atomOneDark } from 'react-syntax-highlighter/dist/esm/styles/hljs'
import python from 'react-syntax-highlighter/dist/esm/languages/hljs/python'
import javascript from 'react-syntax-highlighter/dist/esm/languages/hljs/javascript'
import bash from 'react-syntax-highlighter/dist/esm/languages/hljs/bash'

SyntaxHighlighter.registerLanguage('python', python)
SyntaxHighlighter.registerLanguage('javascript', javascript)
SyntaxHighlighter.registerLanguage('bash', bash)

function detectLanguage(file) {
  if (!file) return 'bash'
  if (file.endsWith('.py')) return 'python'
  if (file.endsWith('.js') || file.endsWith('.jsx') || file.endsWith('.ts') || file.endsWith('.tsx')) return 'javascript'
  return 'bash'
}

const AGENT_LABEL = {
  security: '🔒 Security',
  quality: '⚗️ Quality',
  dependency: '📦 Dependency',
}

export default function FindingCard({ finding, verifiedFix }) {
  const [expanded, setExpanded] = useState(
    finding.severity === 'Critical' || finding.severity === 'High'
  )

  const { id, file, line, issue, severity, reasoning, agent } = finding
  const lang = detectLanguage(file)

  return (
    <div
      className={`finding-card severity-${severity} ${expanded ? 'expanded' : ''}`}
      id={`finding-${id}`}
    >
      {/* Header */}
      <div className="finding-header" onClick={() => setExpanded(e => !e)}>
        <div className="finding-header-left">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
            <span className={`severity-badge badge-${severity}`}>{severity}</span>
            {verifiedFix && verifiedFix.status === 'verified' && (
              <span className="verified-tag">✓ Fix Verified</span>
            )}
          </div>
          <div className="finding-issue">{issue}</div>
          <div className="finding-meta">
            <span className="finding-file">
              {file}{line ? `:${line}` : ''}
            </span>
            {agent && (
              <span className="finding-agent">
                {AGENT_LABEL[agent] || agent}
              </span>
            )}
          </div>
        </div>
        <span className="finding-expand-icon">▶</span>
      </div>

      {/* Body */}
      {expanded && (
        <div className="finding-body">
          <div className="finding-reasoning">
            <strong>Analysis:</strong> {reasoning}
          </div>

          {/* Verified Fix */}
          {verifiedFix && (verifiedFix.original_code || verifiedFix.final_fix) && (
            <div className="fix-block">
              {verifiedFix.status === 'verified' ? (
                <div className="verified-tag">
                  ✓ Verified by Re-evaluator
                  {verifiedFix.iterations > 1 && (
                    <span className="iter-badge" style={{ marginLeft: 6 }}>
                      ({verifiedFix.iterations} iterations)
                    </span>
                  )}
                </div>
              ) : (
                <div className="failed-tag">
                  ⚠ Fix could not be fully verified
                </div>
              )}

              {verifiedFix.original_code && (
                <div className="diff-block" style={{ marginBottom: '0.75rem' }}>
                  <div className="diff-tab">
                    <span className="diff-label before">Before</span>
                  </div>
                  <SyntaxHighlighter
                    language={lang}
                    style={atomOneDark}
                    className="diff-code"
                    customStyle={{
                      background: '#0d1117',
                      borderRadius: 0,
                      margin: 0,
                      fontSize: '0.78rem',
                      maxHeight: 220,
                    }}
                  >
                    {verifiedFix.original_code}
                  </SyntaxHighlighter>
                </div>
              )}

              {verifiedFix.final_fix && (
                <div className="diff-block">
                  <div className="diff-tab">
                    <span className="diff-label after">After (Fix)</span>
                  </div>
                  <SyntaxHighlighter
                    language={lang}
                    style={atomOneDark}
                    className="diff-code"
                    customStyle={{
                      background: '#0d1f0d',
                      borderRadius: 0,
                      margin: 0,
                      fontSize: '0.78rem',
                      maxHeight: 220,
                    }}
                  >
                    {verifiedFix.final_fix}
                  </SyntaxHighlighter>
                </div>
              )}

              {verifiedFix.explanation && (
                <div className="fix-explanation">
                  💡 {verifiedFix.explanation}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
