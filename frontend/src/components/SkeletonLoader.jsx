export default function SkeletonLoader() {
  return (
    <div style={{ animation: 'fadeSlideUp 0.3s ease' }}>
      {/* Stats skeleton */}
      <div className="stats-row" style={{ marginBottom: '1.5rem' }}>
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="skeleton" style={{ flex: 1, height: 70, borderRadius: 8 }} />
        ))}
      </div>

      {/* Summary skeleton */}
      <div className="skeleton skeleton-card" style={{ height: 90, marginBottom: '1.5rem' }} />

      {/* Findings skeleton */}
      <div className="skeleton skeleton-card" style={{ height: 16, width: '40%', marginBottom: '1rem' }} />
      {[1, 2, 3, 4].map(i => (
        <div key={i} className="skeleton skeleton-card" style={{ height: 80 + i * 4, marginBottom: '0.875rem' }} />
      ))}
    </div>
  )
}
