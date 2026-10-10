import React, { useEffect, useRef, useState } from 'react'
import { useTickets } from '../hooks/useTickets'
import { useSocket } from '../hooks/useSocket'
import { PriorityBadge, StatusBadge } from './PriorityBadge'
import { assignTicket, markTicketSolved } from '../utils/api'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// India center as fallback (will auto-fit to markers)
const DEFAULT_CENTER = [20.5937, 78.9629]

const TIER_COLORS = {
  Critical: '#ef4444',
  High:     '#f97316',
  Medium:   '#eab308',
  Low:      '#22c55e',
}

export default function OfficerMap() {
  const mapContainer = useRef(null)
  const mapRef = useRef(null)
  const markersRef = useRef({})
  const [mapReady, setMapReady] = useState(false)
  const [selectedTicket, setSelectedTicket] = useState(null)

  const { tickets, loading, addOrUpdateTicket } = useTickets({ status: 'Submitted,Processing,Pending,In Progress', page_size: 100 })
  const { connected, lastEvent } = useSocket('all')

  const activeTickets = tickets.filter(t => ['Submitted', 'Processing', 'Pending', 'In Progress'].includes(t.status))
  const ticketsWithLocation = activeTickets.filter(t => t.location?.lat && t.location?.lng)

  // ── Initialize Map ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return

    const map = L.map(mapContainer.current, {
      zoomControl: false,
      attributionControl: false
    }).setView(DEFAULT_CENTER, 5)

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19
    }).addTo(map)

    mapRef.current = map
    setMapReady(true)

    return () => {
      map.remove()
      mapRef.current = null
      setMapReady(false)
    }
  }, [])

  // ── Add / update markers ────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current) return
    if (tickets.length === 0) return

    const validTickets = ticketsWithLocation
    if (validTickets.length === 0) return

    const bounds = []

    validTickets.forEach(ticket => {
      const { ticket_id, location, severity_tier, priority_score } = ticket
      const color = TIER_COLORS[severity_tier] || TIER_COLORS.Low
      const size = Math.max(14, Math.min(32, 10 + (priority_score || 0) / 5))

      const iconHtml = `
        <div style="
          width: ${size}px; height: ${size}px;
          border-radius: 50%;
          background: ${color}50;
          border: 2.5px solid ${color};
          box-shadow: 0 0 ${size}px ${color}80, 0 0 6px ${color};
          cursor: pointer;
          transition: all 0.3s;
          position: relative;
        ">
          <div style="
            position: absolute;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            width: ${size * 0.35}px; height: ${size * 0.35}px;
            border-radius: 50%;
            background: ${color};
          "></div>
        </div>`

      const icon = L.divIcon({
        className: '',
        html: iconHtml,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2]
      })

      bounds.push([ticket.location.lat, ticket.location.lng])

      if (markersRef.current[ticket_id]) {
        markersRef.current[ticket_id].setIcon(icon)
        markersRef.current[ticket_id].setLatLng([ticket.location.lat, ticket.location.lng])
      } else {
        const marker = L.marker([ticket.location.lat, ticket.location.lng], { icon })
          .addTo(mapRef.current)
          .on('click', () => setSelectedTicket(ticket))
        markersRef.current[ticket_id] = marker
      }
    })

    // Auto-fit map to show all markers
    if (bounds.length > 0) {
      mapRef.current.fitBounds(bounds, { padding: [50, 50], maxZoom: 13 })
    }
  }, [tickets, mapReady])

  // ── Real-time WebSocket updates ─────────────────────────────────────────────
  useEffect(() => {
    if (!lastEvent) return
    if (lastEvent.type === 'ticket.update' || lastEvent.type === 'priority.boost') {
      addOrUpdateTicket(lastEvent.data)
    }
  }, [lastEvent, addOrUpdateTicket])

  return (
    <div style={{ position: 'relative', height: 'calc(100vh - 120px)' }}>
      <div ref={mapContainer} style={{ width: '100%', height: '100%', borderRadius: 'var(--radius-lg)' }} />

      {/* Overlay Controls */}
      <div style={{ position: 'absolute', top: 16, left: 16, display: 'flex', flexDirection: 'column', gap: 8, zIndex: 1000 }}>
        <div className="card card-sm" style={{ minWidth: 200, background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span className={`status-dot${connected ? ' live' : ''}`} style={{ background: connected ? '#22c55e' : '#f97316' }} />
            <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>{connected ? 'Live' : 'Connecting...'}</span>
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 6 }}>
            {tickets.length} tickets · {ticketsWithLocation.length} mapped
          </div>
          {ticketsWithLocation.length > 0 && (
            <button
              className="btn btn-outline btn-sm"
              style={{ fontSize: '0.72rem', padding: '3px 8px' }}
              onClick={() => {
                if (mapRef.current && ticketsWithLocation.length > 0) {
                  const bounds = ticketsWithLocation.map(t => [t.location.lat, t.location.lng])
                  mapRef.current.fitBounds(bounds, { padding: [50, 50], maxZoom: 13 })
                }
              }}
            >
              📍 Fit All Markers
            </button>
          )}
        </div>
      </div>

      {/* Ongoing Tasks Sidebar (Left) */}
      <div style={{ 
        position: 'absolute', top: 180, left: 16, bottom: 24, width: 280, 
        zIndex: 1000, display: 'flex', flexDirection: 'column', gap: 12,
        pointerEvents: 'none' // allow clicking through to map if needed, but inner cards must re-enable
      }}>
        <div className="card" style={{ 
          flex: 1, background: 'rgba(15, 23, 42, 0.85)', backdropFilter: 'blur(12px)', 
          border: '1px solid var(--border)', display: 'flex', flexDirection: 'column',
          pointerEvents: 'auto', padding: 0, overflow: 'hidden'
        }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', background: 'rgba(255,255,255,0.03)' }}>
            <div style={{ fontSize: '0.7rem', fontWeight: 800, color: 'var(--accent-cyan)', letterSpacing: '0.05em', marginBottom: 2 }}>ONGOING TASKS</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {tickets.filter(t => t.status === 'In Progress').length} tasks in field
            </div>
          </div>
          
          <div style={{ flex: 1, overflowY: 'auto', padding: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {tickets.filter(t => t.status === 'In Progress').length === 0 ? (
              <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                No active tasks in progress.
              </div>
            ) : (
              tickets.filter(t => t.status === 'In Progress').map(t => (
                <div 
                  key={t.ticket_id} 
                  className="card card-sm clickable" 
                  onClick={() => {
                    setSelectedTicket(t);
                    if (mapRef.current) mapRef.current.flyTo([t.location.lat, t.location.lng], 15);
                  }}
                  style={{ 
                    padding: 10, background: selectedTicket?.ticket_id === t.ticket_id ? 'rgba(6, 182, 212, 0.1)' : 'var(--bg-elevated)',
                    border: `1px solid ${selectedTicket?.ticket_id === t.ticket_id ? 'var(--accent-cyan)' : 'var(--border)'}`,
                    transition: 'all 0.2s'
                  }}
                >
                  <div style={{ display: 'flex', justify: 'between', marginBottom: 6 }}>
                    <span style={{ fontSize: '0.7rem', fontWeight: 700, fontFamily: 'monospace' }}>{t.ticket_id}</span>
                    <PriorityBadge tier={t.severity_tier} style={{ transform: 'scale(0.8)', transformOrigin: 'right center' }} />
                  </div>
                  <div style={{ fontSize: '0.8rem', fontWeight: 600, marginBottom: 8, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {t.category}
                  </div>
                  <button 
                    className="btn btn-sm" 
                    style={{ width: '100%', py: 4, fontSize: '0.72rem', background: '#22c55e', color: 'white', border: 'none' }}
                    onClick={(e) => {
                      e.stopPropagation();
                      markTicketSolved(t.ticket_id).then(() => addOrUpdateTicket({ ...t, status: 'Solved' }));
                    }}
                  >
                    ✅ Mark Solved
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Department Quick Tabs */}
      <div style={{ position: 'absolute', top: 16, right: 16, display: 'flex', gap: 6, zIndex: 1000, background: 'var(--bg-elevated)', padding: 6, borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
        <span style={{ fontSize: '0.70rem', color: 'var(--text-muted)', fontWeight: 600, alignSelf: 'center', margin: '0 4px' }}>DEMO SCOPE:</span>
        <button className="btn btn-sm btn-ghost" style={{ padding: '4px 8px', fontSize: '0.75rem' }} onClick={() => { localStorage.setItem('citysync_role', 'officer'); window.location.reload(); }}>All</button>
        <button className="btn btn-sm btn-ghost" style={{ padding: '4px 8px', fontSize: '0.75rem' }} onClick={() => { localStorage.setItem('citysync_role', 'dept_fire'); window.location.reload(); }}>Fire</button>
        <button className="btn btn-sm btn-ghost" style={{ padding: '4px 8px', fontSize: '0.75rem' }} onClick={() => { localStorage.setItem('citysync_role', 'dept_swd'); window.location.reload(); }}>SWD</button>
        <button className="btn btn-sm btn-ghost" style={{ padding: '4px 8px', fontSize: '0.75rem' }} onClick={() => { localStorage.setItem('citysync_role', 'dept_roads'); window.location.reload(); }}>Roads</button>
      </div>

      {selectedTicket && (
        <div style={{ position: 'absolute', bottom: 24, right: 24, width: 360, zIndex: 1000 }}>
          <TicketDetailPanel
            key={selectedTicket.ticket_id}
            ticket={selectedTicket}
            onClose={() => setSelectedTicket(null)}
            onAssigned={(tid) => {
              // The socket event usually handles this, but we can optimistically update
              addOrUpdateTicket({ ...selectedTicket, status: 'In Progress' })
            }}
          />
        </div>
      )}
    </div>
  )
}

function OfficerTicketRow({ ticket, onClick, selected }) {
  const { ticket_id, category, severity_tier, priority_score, status, ward_id, upvote_count } = ticket
  return (
    <div
      className="card card-sm"
      style={{
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        borderColor: selected ? 'var(--accent-blue)' : undefined,
        transition: 'all 0.2s',
      }}
      onClick={onClick}
    >
      {/* Priority dot */}
      <div style={{
        width: 14, height: 14, borderRadius: '50%', flexShrink: 0,
        background: TIER_COLORS[severity_tier] || '#22c55e',
        boxShadow: `0 0 8px ${TIER_COLORS[severity_tier] || '#22c55e'}80`,
      }} />

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-primary)' }}>
          {category} · Ward {ward_id || '—'}
        </div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          {ticket_id} · {upvote_count} reports
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
        <span style={{
          fontFamily: 'monospace', fontWeight: 700, fontSize: '1rem',
          color: TIER_COLORS[severity_tier] || '#22c55e',
        }}>
          {Math.round(priority_score)}
        </span>
        <StatusBadge status={status} />
      </div>
    </div>
  )
}

// ── All complaint categories ──────────────────────────────────────────────────
const CATEGORIES = [
  'Roads & Footpaths', 'Water Supply', 'Sewage & Drainage', 'Garbage & Waste',
  'Street Lighting', 'Electricity', 'Parks & Gardens', 'Noise Pollution',
  'Air Pollution', 'Flooding', 'Stray Animals', 'Illegal Construction',
  'Traffic & Signals', 'Public Transport', 'Healthcare', 'Education', 'Other',
]

// Field Crew roster (in production, pull from /api/field-workers)
const FIELD_CREWS = [
  { id: 'crew_fire_1', name: 'Fire Crew 1 - Fort Station', dept: 'Fire', icon: '🚒' },
  { id: 'crew_swd_1', name: 'SWD Drainage Crew Alpha', dept: 'Water', icon: '🌊' },
  { id: 'crew_roads_1', name: 'Roads Asphalt Crew', dept: 'Roads', icon: '🚧' },
  { id: 'crew_sanitation_1', name: 'Sanitation Cleanup Crew', dept: 'Garbage', icon: '🗑️' },
  { id: 'crew_police_1', name: 'Police Patrol Unit 7', dept: 'Police', icon: '🚓' },
  { id: 'crew_general_1', name: 'General Field Crew Beta', dept: 'General', icon: '👷' },
]

function TicketDetailPanel({ ticket, onClose, onAssigned }) {
  const { ticket_id, category, severity_tier, priority_score, status, description, ward_id, severity, upvote_count, assigned_to: initialAssigned, officer_notes: initialNotes } = ticket

  const [showAssign, setShowAssign]     = useState(false)
  const [selCategory, setSelCategory]   = useState(category || 'Other')
  const [selSeverity, setSelSeverity]   = useState(severity || 5)
  const [selWorker, setSelWorker]       = useState(null)
  const [notes, setNotes]               = useState(initialNotes || '')
  const [assignState, setAssignState]   = useState('idle') // idle | loading | success | error
  const [assignMsg, setAssignMsg]       = useState('')

  // Initialize selected crew if already assigned
  useEffect(() => {
    if (initialAssigned) {
      const worker = FIELD_CREWS.find(w => w.id === initialAssigned || w.name === initialAssigned)
      if (worker) setSelWorker(worker)
    }
  }, [initialAssigned])

  const handleAssign = async () => {
    if (!selWorker) return
    setAssignState('loading')
    try {
      const res = await assignTicket(ticket_id, {
        assignee_id: selWorker.id,
        category: selCategory,
        severity: selSeverity,
        notes,
      })
      setAssignMsg(res.data.message)
      setAssignState('success')
      if (onAssigned) onAssigned(ticket_id)
    } catch (err) {
      setAssignMsg(err?.response?.data?.detail || 'Assignment failed')
      setAssignState('error')
    }
  }

  const handleMarkSolved = async () => {
    try {
      await markTicketSolved(ticket_id)
      setAssignMsg('Ticket has been successfully resolved and is pending citizen verification.')
      setAssignState('success')
      if (onAssigned) onAssigned(ticket_id)
    } catch (err) {
      alert(err?.response?.data?.detail || 'Failed to mark as solved')
    }
  }

  if (assignState === 'success') {
    return (
      <div className="card" style={{ boxShadow: 'var(--shadow-elevated)', textAlign: 'center', padding: 32 }}>
        <div style={{ fontSize: '2.5rem', marginBottom: 8 }}>✅</div>
        <h3 style={{ color: 'var(--tier-low)', marginBottom: 8 }}>Assigned!</h3>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: 16 }}>{assignMsg}</p>
        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', padding: '8px 12px', background: 'rgba(34,197,94,0.08)', borderRadius: 'var(--radius-md)' }}>
          Ticket status updated to <strong>In Progress</strong>
        </div>
        <button className="btn btn-outline btn-sm" style={{ marginTop: 16 }} onClick={onClose}>Close</button>
      </div>
    )
  }

  return (
    <div className="card" style={{ boxShadow: 'var(--shadow-elevated)', maxHeight: '80vh', overflowY: 'auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <h3 style={{ fontSize: '1rem' }}>{category}</h3>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <PriorityBadge tier={severity_tier} score={priority_score} showScore />
        <StatusBadge status={status} />
      </div>
      {description && <p style={{ fontSize: '0.82rem', marginBottom: 12, color: 'var(--text-secondary)' }}>{description.split('[Assigned')[0].trim()}</p>}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 16 }}>
        <span>🗺 Ward: {ward_id || '—'}</span>
        <span>⚡ Severity: {severity}/10</span>
        <span>👥 Reports: {upvote_count}</span>
        <span>🆔 {ticket_id}</span>
      </div>

      {!showAssign ? (
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn btn-primary btn-sm btn-full"
            onClick={() => setShowAssign(true)}
          >
            👷 Assign Field Crew
          </button>
        </div>
      ) : (
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
          <div style={{ fontWeight: 700, fontSize: '0.85rem', marginBottom: 12 }}>📋 Assignment Form</div>

          {/* Category override */}
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
              CATEGORY
            </label>
            <select
              className="input"
              style={{ fontSize: '0.82rem', padding: '6px 10px', cursor: 'pointer' }}
              value={selCategory}
              onChange={e => setSelCategory(e.target.value)}
            >
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          {/* Severity */}
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
              SEVERITY: <strong style={{ color: selSeverity >= 8 ? '#ef4444' : selSeverity >= 5 ? '#f97316' : '#22c55e' }}>{selSeverity}/10</strong>
            </label>
            <input
              type="range" min={1} max={10} value={selSeverity}
              onChange={e => setSelSeverity(Number(e.target.value))}
              style={{ width: '100%', accentColor: selSeverity >= 8 ? '#ef4444' : selSeverity >= 5 ? '#f97316' : '#22c55e' }}
            />
          </div>

          {/* Field Crew picker */}
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
              ASSIGN TO CREW
            </label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 200, overflowY: 'auto' }}>
              {FIELD_CREWS.map(w => (
                <button
                  key={w.id}
                  onClick={() => setSelWorker(w)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '8px 12px', borderRadius: 'var(--radius-md)',
                    background: selWorker?.id === w.id ? 'rgba(99,102,241,0.2)' : 'var(--bg-card)',
                    border: `1px solid ${selWorker?.id === w.id ? 'var(--accent-blue)' : 'var(--border)'}`,
                    cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s',
                  }}
                >
                  <span style={{ fontSize: '1.2rem' }}>{w.icon}</span>
                  <div>
                    <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)' }}>{w.name}</div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{w.dept}</div>
                  </div>
                  {selWorker?.id === w.id && <span style={{ marginLeft: 'auto', color: 'var(--accent-blue)', fontSize: '0.9rem' }}>✓</span>}
                </button>
              ))}
            </div>
          </div>

          {/* Notes */}
          <div style={{ marginBottom: 14 }}>
            <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
              NOTES (optional)
            </label>
            <textarea
              className="input"
              rows={2}
              placeholder="Any special instructions for the field crew..."
              value={notes}
              onChange={e => setNotes(e.target.value)}
              style={{ resize: 'vertical', fontSize: '0.82rem' }}
            />
          </div>

          {assignState === 'error' && (
            <div style={{ color: 'var(--tier-critical)', fontSize: '0.8rem', marginBottom: 10 }}>
              ✗ {assignMsg}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="btn btn-outline btn-sm"
              style={{ flex: 1 }}
              onClick={() => { setShowAssign(false); setAssignState('idle') }}
            >
              Cancel
            </button>
            <button
              className="btn btn-primary btn-sm"
              style={{ flex: 2 }}
              disabled={!selWorker || assignState === 'loading'}
              onClick={handleAssign}
            >
              {assignState === 'loading' ? (
                <><div className="spinner" style={{ borderTopColor: '#fff', width: 12, height: 12 }} /> Assigning...</>
              ) : `Assign to ${selWorker?.name?.split(' ')[0] || '...'}`}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
