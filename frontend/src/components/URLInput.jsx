import { useState } from 'react'

export default function URLInput({ onSubmit }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const validate = (v) => {
    if (!v.trim()) return 'Please enter a GitHub repository URL'
    if (!v.includes('github.com')) return 'URL must be a GitHub repository (github.com/...)'
    const parts = v.replace('https://github.com/', '').split('/')
    if (parts.length < 2 || !parts[1]) return 'URL must include owner and repo (e.g. github.com/owner/repo)'
    return ''
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const err = validate(url)
    if (err) { setError(err); return }
    setError('')
    setLoading(true)
    await onSubmit(url.trim())
    setLoading(false)
  }

  const examples = [
    'https://github.com/digininja/DVWA',
    'https://github.com/pallets/flask',
    'https://github.com/expressjs/express',
  ]

  return (
    <div className="hero">
      <div className="hero-eyebrow">🛡️ Multi-Agent Security &amp; Quality Review</div>
      <h1 className="hero-title">
        Code Review, <span>Reimagined</span><br />
        with Agentic AI
      </h1>
      <p className="hero-subtitle">
        Paste any public GitHub repository URL. CodeSentinel deploys specialized AI agents
        to review security, quality, and dependencies — then verifies every fix it suggests.
      </p>

      <form onSubmit={handleSubmit} style={{ width: '100%', maxWidth: 620 }}>
        <div className="url-input-wrapper">
          <input
            id="repo-url-input"
            className="url-input"
            type="text"
            placeholder="https://github.com/owner/repository"
            value={url}
            onChange={e => { setUrl(e.target.value); setError('') }}
            autoFocus
            spellCheck={false}
          />
          <button
            id="analyze-btn"
            className="analyze-btn"
            type="submit"
            disabled={loading}
          >
            {loading ? 'Starting...' : 'Analyze →'}
          </button>
        </div>
        {error && <div className="url-error">⚠ {error}</div>}
      </form>

      <div style={{ marginTop: '1rem', opacity: 0, animation: 'fadeSlideUp 0.6s 0.4s ease forwards' }}>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
          Try an example:
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'center' }}>
          {examples.map(ex => (
            <button
              key={ex}
              onClick={() => { setUrl(ex); setError('') }}
              style={{
                background: 'var(--bg-glass)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-secondary)',
                fontSize: '0.75rem',
                fontFamily: 'JetBrains Mono, monospace',
                padding: '4px 12px',
                cursor: 'pointer',
                transition: 'var(--transition)',
              }}
              onMouseEnter={e => {
                e.target.style.borderColor = 'var(--accent)'
                e.target.style.color = 'var(--accent-bright)'
              }}
              onMouseLeave={e => {
                e.target.style.borderColor = 'var(--border)'
                e.target.style.color = 'var(--text-secondary)'
              }}
            >
              {ex.replace('https://github.com/', '')}
            </button>
          ))}
        </div>
      </div>

      <div className="hero-features">
        {[
          '7 Specialized Agents',
          'Live Agent Trace',
          'Verified Code Fixes',
          'Severity Ranking',
        ].map(f => (
          <div key={f} className="hero-feature">
            <div className="hero-feature-dot" />
            {f}
          </div>
        ))}
      </div>
    </div>
  )
}
