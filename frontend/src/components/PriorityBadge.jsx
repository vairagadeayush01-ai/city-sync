import React from 'react'

const TIER_CONFIG = {
  Critical: { class: 'badge-critical', dot: '#ef4444', label: '🔴 Critical', score: '85+' },
  High:     { class: 'badge-high',     dot: '#f97316', label: '🟠 High',     score: '60-84' },
  Medium:   { class: 'badge-medium',   dot: '#eab308', label: '🟡 Medium',   score: '35-59' },
  Low:      { class: 'badge-low',      dot: '#22c55e', label: '🟢 Low',      score: '<35' },
}

const STATUS_CONFIG = {
  Pending:        { class: 'badge-pending',  icon: '⏳' },
  Processing:     { class: 'badge-pending',  icon: '🔄' },
  'In Progress':  { class: 'badge-progress', icon: '🔧' },
  'Work Complete':{ class: 'badge-progress', icon: '✅' },
  Resolved:       { class: 'badge-resolved', icon: '✓' },
  Rejected:       { class: 'badge-rejected', icon: '✗' },
  'Human Review': { class: 'badge-medium',   icon: '👤' },
}

export function PriorityBadge({ tier, score, showScore = false }) {
  const config = TIER_CONFIG[tier] || TIER_CONFIG.Low
  return (
    <span className={`badge ${config.class}`}>
      <span
        className="status-dot"
        style={{ background: config.dot, width: 7, height: 7 }}
      />
      {tier}
      {showScore && score != null && (
        <span style={{ opacity: 0.7, fontWeight: 400 }}>· {Math.round(score)}</span>
      )}
    </span>
  )
}

export function StatusBadge({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG['Human Review']
  return (
    <span className={`badge ${config.class}`}>
      {config.icon} {status}
    </span>
  )
}

export function PriorityBar({ score, tier }) {
  const maxScore = 120
  const pct = Math.min((score / maxScore) * 100, 100)
  const colorMap = {
    Critical: 'linear-gradient(90deg, #f97316, #ef4444)',
    High:     'linear-gradient(90deg, #eab308, #f97316)',
    Medium:   'linear-gradient(90deg, #3b82f6, #eab308)',
    Low:      'linear-gradient(90deg, #14b8a6, #3b82f6)',
  }
  return (
    <div className="priority-bar-container">
      <div className="priority-bar-track">
        <div
          className="priority-bar-fill"
          style={{
            width: `${pct}%`,
            background: colorMap[tier] || colorMap.Low,
          }}
        />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
        <span>Score {Math.round(score)}</span>
        <span>{tier}</span>
      </div>
    </div>
  )
}

export default PriorityBadge
