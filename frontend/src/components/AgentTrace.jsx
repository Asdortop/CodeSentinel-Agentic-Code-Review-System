import AgentCard from './AgentCard'

export default function AgentTrace({ events }) {
  if (events.length === 0) {
    return (
      <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
        Waiting for agents to start...
      </div>
    )
  }

  return (
    <div>
      {events.map((event, idx) => (
        <AgentCard key={`${event.agent}-${idx}`} event={event} />
      ))}
    </div>
  )
}
