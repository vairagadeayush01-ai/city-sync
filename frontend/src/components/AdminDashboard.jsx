import React, { useState, useEffect } from 'react'
import { getMetrics, getLeaderboard, getRoutingMetrics, getVerifyMetrics, listTickets } from '../utils/api'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend,
} from 'recharts'

const COLORS = ['#3b82f6', '#8b5cf6', '#06b6d4', '#14b8a6', '#eab308', '#f97316', '#ef4444', '#22c55e', '#a855f7', '#ec4899']

function MetricCard({ label, value, unit = '', sublabel, trend, color = 'var(--accent-blue)' }) {
  return (
    <div className="card stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={{ background: 'none', WebkitTextFillColor: color, color }}>
        {value}<span style={{ fontSize: '1rem', opacity: 0.6 }}>{unit}</span>
      </div>
      {sublabel && <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{sublabel}</div>}
      {trend != null && (
        <div className={`stat-change ${trend >= 0 ? 'stat-up' : 'stat-down'}`}>
          {trend >= 0 ? '↑' : '↓'} {Math.abs(trend).toFixed(1)}%
        </div>
      )}
    </div>
  )
}

const CUSTOM_TOOLTIP = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="card card-sm" style={{ fontSize: '0.8rem', padding: '8px 12px' }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color }}>{p.name}: {p.value}</div>
      ))}
    </div>
  )
}

export default function AdminDashboard() {
  const [metrics, setMetrics] = useState(null)
  const [leaderboard, setLeaderboard] = useState([])
  const [routingMetrics, setRoutingMetrics] = useState(null)
  const [verifyMetrics, setVerifyMetrics] = useState(null)
  const [ticketsByStatus, setTicketsByStatus] = useState([])
  const [allTickets, setAllTickets] = useState([])
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState(null)

  const fetchAll = async () => {
    try {
      const [m, lb, rm, vm] = await Promise.all([
        getMetrics().catch(() => ({ data: {} })),
        getLeaderboard().catch(() => ({ data: { leaderboard: [] } })),
        getRoutingMetrics(),
        getVerifyMetrics(),
      ])

      setMetrics(m.data)
      setLeaderboard(lb.data.leaderboard || [])
      setRoutingMetrics(rm.data)
      setVerifyMetrics(vm.data)
      setLastRefresh(new Date())

      // Build status breakdown from tickets
      const statusMap = { Submitted: 0, Processing: 0, Pending: 0, 'In Progress': 0, 'Work Complete': 0, Solved: 0, Resolved: 0, Rejected: 0 }
      const res = await listTickets({ page_size: 100 }).catch(() => ({ data: { tickets: [] } }))
      const tickets = res.data.tickets || []
      
      tickets.forEach(t => {
        if (statusMap[t.status] != null) statusMap[t.status]++
        else statusMap['Pending']++
      })
      setTicketsByStatus(Object.entries(statusMap).map(([name, value]) => ({ name, value })))
      setAllTickets(tickets)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 5000)
    return () => clearInterval(interval)
  }, [])

  const categoryData = leaderboard.slice(0, 8).map(item => ({
    name: `${item.category}\n${item.ward_id}`,
    count: item.count,
    category: item.category,
    ward: item.ward_id,
  }))

  const statusColors = {
    Processing: '#a855f7',
    Pending: '#6366f1', 'In Progress': '#06b6d4',
    'Work Complete': '#14b8a6', Solved: '#22c55e', 
    Resolved: '#10b981', Rejected: '#64748b',
  }

  return (
    <div style={{ padding: '24px 0' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>Admin Dashboard</h2>
          <p style={{ fontSize: '0.85rem' }}>CitySync Intelligence Platform · Real-time metrics</p>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            🔄 Refreshes every 5s · {lastRefresh ? `Last: ${lastRefresh.toLocaleTimeString()}` : 'Loading...'}
          </div>
          <button className="btn btn-outline btn-sm" onClick={fetchAll}>↻ Refresh</button>
        </div>
      </div>

      {loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
          {[1,2,3,4].map(i => <div key={i} className="skeleton" style={{ height: 100 }} />)}
        </div>
      ) : (
        <>
          {/* ── Stat Row ──────────────────────────────────────────────────────── */}
          <div className="grid-4" style={{ marginBottom: 24 }}>
            <MetricCard
              label="Total Requests" value={metrics?.request_count ?? '—'}
              sublabel="Gateway submissions" color="#3b82f6"
            />
            <MetricCard
              label="P95 Latency" value={metrics?.p95_latency_ms?.toFixed(0) ?? '—'} unit="ms"
              sublabel="Gateway response" color="#14b8a6"
            />
            <MetricCard
              label="Rate Limit Hits" value={metrics?.rate_limit_hits ?? 0}
              sublabel="429 responses" color="#eab308"
            />
            <MetricCard
              label="Webhook Success" value={routingMetrics?.webhook_success_rate ?? '—'} unit="%"
              sublabel="Last 1 hour" color="#22c55e"
            />
          </div>

          <div className="grid-4" style={{ marginBottom: 32 }}>
            <MetricCard
              label="Step 1 Pass Rate" value={verifyMetrics?.step1_pass_rate ?? '—'} unit="%"
              sublabel="Field worker photos" color="#8b5cf6"
            />
            <MetricCard
              label="Step 2 Pass Rate" value={verifyMetrics?.step2_pass_rate ?? '—'} unit="%"
              sublabel="Citizen confirmations" color="#06b6d4"
            />
            <MetricCard
              label="Webhook Attempts" value={routingMetrics?.total_webhooks_1h ?? '—'}
              sublabel="Last hour" color="#f97316"
            />
            <MetricCard
              label="Routes Loaded" value={routingMetrics?.routes_loaded ?? '—'}
              sublabel="In-memory routing" color="#ec4899"
            />
          </div>

          {/* ── Charts Row ────────────────────────────────────────────────────── */}
          <div className="grid-2" style={{ marginBottom: 32 }}>
            {/* Complaint Frequency Leaderboard */}
            <div className="card">
              <h3 style={{ marginBottom: 16, fontSize: '1rem' }}>🔥 Hotspot Leaderboard (Top 8)</h3>
              {categoryData.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>
                  No frequency data yet · Submit complaints to see hotspots
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={categoryData} margin={{ top: 4, right: 8, bottom: 40, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis
                      dataKey="name"
                      tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                      angle={-30}
                      textAnchor="end"
                      interval={0}
                    />
                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                    <Tooltip content={<CUSTOM_TOOLTIP />} />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {categoryData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Ticket Status Breakdown */}
            <div className="card">
              <h3 style={{ marginBottom: 16, fontSize: '1rem' }}>📊 Ticket Status Breakdown</h3>
              {ticketsByStatus.every(s => s.value === 0) ? (
                <div style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>
                  No tickets yet
                </div>
              ) : (
                <div style={{ display: 'flex', gap: 24, alignItems: 'center' }}>
                  <ResponsiveContainer width="55%" height={220}>
                    <PieChart>
                      <Pie data={ticketsByStatus} cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={3} dataKey="value">
                        {ticketsByStatus.map((entry, i) => (
                          <Cell key={i} fill={statusColors[entry.name] || COLORS[i]} />
                        ))}
                      </Pie>
                      <Tooltip content={<CUSTOM_TOOLTIP />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {ticketsByStatus.map((s, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.82rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ width: 8, height: 8, borderRadius: '50%', background: statusColors[s.name] || COLORS[i], display: 'inline-block' }} />
                          {s.name}
                        </div>
                        <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{s.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ── Active Assignments Tracker ─────────────────────────────────────────────── */}
          <div className="card" style={{ marginBottom: 32 }}>
            <h3 style={{ marginBottom: 16, fontSize: '1rem' }}>👷 Active Field Operations</h3>
            {allTickets.filter(t => t.assigned_to).length === 0 ? (
              <div style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>
                No active field assignments
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                      <th style={{ padding: '12px 8px', color: 'var(--text-muted)' }}>Ticket ID</th>
                      <th style={{ padding: '12px 8px', color: 'var(--text-muted)' }}>Worker</th>
                      <th style={{ padding: '12px 8px', color: 'var(--text-muted)' }}>Category</th>
                      <th style={{ padding: '12px 8px', color: 'var(--text-muted)' }}>Status</th>
                      <th style={{ padding: '12px 8px', color: 'var(--text-muted)' }}>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allTickets.filter(t => t.assigned_to).map(t => (
                      <tr key={t.ticket_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                        <td style={{ padding: '12px 8px', fontFamily: 'monospace' }}>{t.ticket_id}</td>
                        <td style={{ padding: '12px 8px', fontWeight: 600 }}>{t.assigned_to}</td>
                        <td style={{ padding: '12px 8px' }}>
                          <span style={{ padding: '2px 8px', borderRadius: 12, background: 'rgba(255,255,255,0.1)', fontSize: '0.75rem' }}>
                            {t.category}
                          </span>
                        </td>
                        <td style={{ padding: '12px 8px' }}>
                          <span style={{ 
                            padding: '2px 8px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 600,
                            background: t.status === 'In Progress' ? 'rgba(6, 182, 212, 0.15)' : 'rgba(255,255,255,0.1)',
                            color: t.status === 'In Progress' ? '#06b6d4' : 'inherit'
                          }}>
                            {t.status}
                          </span>
                        </td>
                        <td style={{ padding: '12px 8px', color: 'var(--text-muted)', maxWidth: 200, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {t.officer_notes || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* ── AI Pipeline Stats ─────────────────────────────────────────────── */}
          <div className="card" style={{ marginBottom: 24 }}>
            <h3 style={{ marginBottom: 16, fontSize: '1rem' }}>🤖 AI Pipeline Performance</h3>
            <div className="grid-4">
              {[
                { label: 'Classifier', value: metrics?.mock_ai ? 'Mock Mode' : 'Groq Qwen 3.8 27B', sublabel: 'intent+category+severity', icon: '🧠' },
                { label: 'Avg Latency', value: '~380ms', sublabel: 'classification + dedup', icon: '⚡' },
                { label: 'Verifier', value: metrics?.mock_ai ? 'Mock Mode' : 'Groq Qwen Vision', sublabel: 'before/after photo comparison', icon: '👁️' },
                { label: 'Dedup Radius', value: '50m', sublabel: 'PostGIS ST_DWithin', icon: '📍' },
              ].map((item, i) => (
                <div key={i} className="card card-sm" style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                  <span style={{ fontSize: '1.4rem' }}>{item.icon}</span>
                  <div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{item.label}</div>
                    <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.95rem' }}>{item.value}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{item.sublabel}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ── Architecture Layers ────────────────────────────────────────────── */}
          <div className="card">
            <h3 style={{ marginBottom: 16, fontSize: '1rem' }}>🏗 System Architecture — 7 Layers</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                { layer: 'L1', name: 'Citizen Interface', tech: 'React PWA + WhatsApp/SMS', color: '#3b82f6' },
                { layer: 'L2', name: 'Event Streaming', tech: 'Redis Streams (consumer groups)', color: '#8b5cf6' },
                { layer: 'L3', name: 'AI Processing', tech: 'Groq Qwen 3.8 27B + PostGIS dedup + priority scorer', color: '#06b6d4' },
                { layer: 'L3.5', name: 'Routing', tech: 'FastAPI + Celery webhook retry + SendGrid fallback', color: '#14b8a6' },
                { layer: 'L4', name: 'Privacy Vault', tech: 'HMAC-SHA256 + Gaussian DP noise (ε=2.0/0.5)', color: '#eab308' },
                { layer: 'L5', name: 'Persistence', tech: 'PostgreSQL 16+PostGIS + MinIO + Redis sorted sets', color: '#f97316' },
                { layer: 'L5.5', name: 'Verification Engine', tech: 'Groq Qwen vision + PG trigger enforcement', color: '#ef4444' },
                { layer: 'L6', name: 'Presentation', tech: 'React+Vite PWA + Mapbox GL JS + Socket.io', color: '#22c55e' },
              ].map((item) => (
                <div key={item.layer} style={{
                  display: 'flex', alignItems: 'center', gap: 16,
                  padding: '10px 14px',
                  background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)',
                  borderLeft: `3px solid ${item.color}`,
                }}>
                  <span style={{
                    fontFamily: 'monospace', fontWeight: 700, fontSize: '0.8rem',
                    color: item.color, minWidth: 36,
                  }}>
                    {item.layer}
                  </span>
                  <span style={{ fontWeight: 600, fontSize: '0.875rem', minWidth: 180 }}>{item.name}</span>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{item.tech}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
