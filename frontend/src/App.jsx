import { useState, useCallback } from 'react'
import URLInput from './components/URLInput'
import AgentTrace from './components/AgentTrace'
import FinalReport from './components/FinalReport'
import SkeletonLoader from './components/SkeletonLoader'
import '../src/index.css'

export default function App() {
  const [status, setStatus] = useState('idle') // idle | loading | complete | error
  const [events, setEvents] = useState([])
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [repoUrl, setRepoUrl] = useState('')

  const startReview = useCallback(async (url) => {
    setStatus('loading')
    setEvents([])
    setReport(null)
    setError(null)
    setRepoUrl(url)

    try {
      const response = await fetch('/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_url: url }),
      })

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() // keep incomplete line

        let eventType = 'agent_update'
        let dataLine = null

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            dataLine = line.slice(6)
          } else if (line === '') {
            // End of event
            if (dataLine) {
              try {
                const parsed = JSON.parse(dataLine)
                if (eventType === 'report_complete') {
                  setReport(parsed)
                  setStatus('complete')
                } else if (eventType === 'error') {
                  setError(parsed.message || 'An unknown error occurred')
                  setStatus('error')
                } else {
                  setEvents(prev => {
                    // Update existing event or add new
                    const idx = prev.findIndex(
                      e => e.agent === parsed.agent && e.status === 'running'
                    )
                    if (idx >= 0 && parsed.status !== 'running') {
                      const updated = [...prev]
                      updated[idx] = parsed
                      return updated
                    }
                    // Don't add duplicate running events
                    const alreadyRunning = prev.some(
                      e => e.agent === parsed.agent && e.status === 'running'
                    )
                    if (alreadyRunning && parsed.status === 'running') return prev
                    return [...prev, parsed]
                  })
                }
              } catch {
                // ignore parse errors
              }
            }
            eventType = 'agent_update'
            dataLine = null
          }
        }
      }

      // If stream ended without report_complete
      if (status !== 'complete' && status !== 'error') {
        setStatus(report ? 'complete' : 'error')
        if (!report) setError('Stream ended unexpectedly.')
      }
    } catch (err) {
      setError(err.message || 'Connection failed. Is the backend running?')
      setStatus('error')
    }
  }, [])

  const reset = () => {
    setStatus('idle')
    setEvents([])
    setReport(null)
    setError(null)
    setRepoUrl('')
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-logo">
          <div className="logo-icon">🛡️</div>
          CodeSentinel
        </div>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          {status !== 'idle' && (
            <button className="new-review-btn" onClick={reset}>
              ← New Review
            </button>
          )}
          <span className="header-badge">Powered by Gemini 2.0 Flash</span>
        </div>
      </header>

      <div className="main-layout">
        {status === 'idle' && (
          <URLInput onSubmit={startReview} />
        )}

        {status !== 'idle' && (
          <div className="review-layout">
            {/* Left panel — Agent Trace */}
            <div className="panel">
              <div className="panel-header">
                <div className="panel-header-icon" style={{ background: 'rgba(108,99,255,0.15)' }}>
                  ⚡
                </div>
                <h2>Agent Trace</h2>
                {status === 'loading' && (
                  <span className="panel-badge">Live</span>
                )}
                {status === 'complete' && (
                  <span className="panel-badge" style={{ background: 'var(--success-bg)', color: 'var(--success)' }}>
                    Done
                  </span>
                )}
              </div>
              <div className="panel-body">
                <AgentTrace events={events} />
              </div>
            </div>

            {/* Right panel — Report */}
            <div className="panel panel-right">
              <div className="panel-header">
                <div className="panel-header-icon" style={{ background: 'rgba(16,185,129,0.15)' }}>
                  📋
                </div>
                <h2>Review Report</h2>
                {status === 'loading' && !report && (
                  <span className="panel-badge">Processing...</span>
                )}
              </div>
              <div className="panel-body">
                {status === 'error' && (
                  <div className="error-panel">
                    <span className="error-panel-icon">🚨</span>
                    <div>
                      <div className="error-panel-title">Review Failed</div>
                      <div className="error-panel-msg">{error}</div>
                    </div>
                  </div>
                )}
                {status === 'loading' && !report && (
                  <SkeletonLoader />
                )}
                {report && (
                  <FinalReport report={report} repoUrl={repoUrl} />
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
