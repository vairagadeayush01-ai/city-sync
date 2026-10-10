import React from 'react'
import { PriorityBadge, StatusBadge, PriorityBar } from './PriorityBadge'

const CATEGORY_ICONS = {
  'Pothole':        '🕳️',
  'Flooding':       '🌊',
  'Drainage':       '🚰',
  'Street Light':   '💡',
  'Garbage':        '🗑️',
  'Water Supply':   '💧',
  'Building Hazard':'🏚️',
  'Live Wire':      '⚡',
  'Noise':          '🔊',
  'Other':          '📋',
}

export default function TicketCard({ ticket, onClick, compact = false }) {
  const {
    ticket_id,
    category,
    severity,
    severity_tier,
    priority_score = 0,
    status,
    description,
    ward_id,
    submitted_at,
    upvote_count = 0,
    cluster_info,
  } = ticket

  const submittedDate = submitted_at
    ? new Date(submitted_at).toLocaleString('en-IN', {
        day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
      })
    : '—'

  const isCritical = severity_tier === 'Critical'

  return (
    <div
      className={`card ticket-card${isCritical ? ' critical' : ''}`}
      style={{
        cursor: onClick ? 'pointer' : 'default',
        borderColor: isCritical ? 'rgba(239,68,68,0.4)' : undefined,
        boxShadow: isCritical ? 'var(--glow-critical)' : undefined,
        transition: 'all 0.25s',
      }}
      onClick={onClick}
    >
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div className="flex items-center gap-8">
          <span style={{ fontSize: '1.4rem' }}>{CATEGORY_ICONS[category] || '📋'}</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-primary)' }}>
              {category}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {ticket_id} · Ward {ward_id || '—'}
            </div>
          </div>
        </div>
        <div className="flex gap-8 items-center">
          <PriorityBadge tier={severity_tier || 'Low'} score={priority_score} showScore />
          <StatusBadge status={status || 'Pending'} />
        </div>
      </div>

      {/* Description */}
      {!compact && description && (
        <p style={{
          fontSize: '0.875rem',
          color: 'var(--text-secondary)',
          marginBottom: 12,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}>
          {description}
        </p>
      )}

      {/* Priority Bar */}
      <PriorityBar score={priority_score} tier={severity_tier || 'Low'} />

      {/* Footer */}
      <div className="flex justify-between items-center mt-12" style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
        <div className="flex gap-12">
          <span title="Severity">⚠️ Sev {severity}/10</span>
          <span title="Upvotes">👥 {upvote_count} reports</span>
          {cluster_info && (
            <span title="Cluster">🔗 {cluster_info.member_count} linked</span>
          )}
        </div>
        <span>{submittedDate}</span>
      </div>
    </div>
  )
}
