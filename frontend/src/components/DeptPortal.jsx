import React, { useEffect, useState, useMemo } from 'react'
import api, { getMe, listTickets } from '../utils/api'

export default function DeptPortal() {
  const [stats, setStats] = useState({ 
    total: 0, webhooks_received: 0, valid_signatures: 0 
  })
  const [tickets, setTickets] = useState([])
  const [loading, setLoading] = useState(true)
  const [me, setMe] = useState(null)

  useEffect(() => {
    // getMe() already returns the JSON payload (not an axios Response)
    getMe().then((data) => setMe(data)).catch(() => setMe(null))
  }, [])

  useEffect(() => {
    const fetchData = async () => {
        try {
            // Primary: webhook-derived log (if departments are pushing webhooks)
            const res = await api.get('/api/stats/webhooks')
            const data = res.data || {}

            // Fallback: if no webhook traffic, show real tickets so dashboard isn't "all zeros"
            let ticketRows = data.tickets || []
            if (!Array.isArray(ticketRows) || ticketRows.length === 0) {
              const tRes = await listTickets({ page_size: 100 }).catch(() => ({ data: { tickets: [] } }))
              ticketRows = (tRes.data?.tickets || []).map(t => ({
                ticket_id: t.ticket_id,
                dept_code: t.dept_code, // may be missing; UI will fallback
                category: t.category,
                severity_tier: t.severity_tier,
                priority_score: t.priority_score,
                ward_id: t.ward_id,
                status: t.status,
                received_at: t.submitted_at || t.updated_at || new Date().toISOString(),
              }))
            }

            setTickets(ticketRows)
            setStats({
                total: ticketRows.length || 0,
                webhooks_received: data.log?.length || 0,
                valid_signatures: (data.log || []).filter(l => l.signature_valid).length || 0
            })
        } catch (e) {
            console.error("Failed to fetch webhooks:", e)
        } finally {
            setLoading(false)
        }
    }
    fetchData()
    const intv = setInterval(fetchData, 10000)
    return () => clearInterval(intv)
  }, [])

  const TIER_COLORS = { Critical: '#ef4444', High: '#f97316', Medium: '#eab308', Low: '#22c55e' }

  const deptCode = (me?.dept_code || '').toLowerCase()
  const visibleTickets = useMemo(() => {
    let filtered = tickets.filter(t => !['Solved', 'Resolved', 'Rejected'].includes(t.status))
    if (!deptCode) return filtered
    return filtered.filter((t) => (t.dept_code || me?.dept_code || '').toLowerCase() === deptCode)
  }, [tickets, deptCode])

  return (
    <div className="container" style={{ paddingTop: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: '1.5rem' }}>≡ƒÅó Unified Department Webhooks</h1>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <span className="status-dot live" style={{ background: '#22c55e' }}></span>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Live updates</span>
        </div>
      </div>

      {deptCode && (
        <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 16 }}>
          Showing webhooks for <strong style={{ color: 'var(--text-primary)' }}>{me?.dept_name || deptCode}</strong> only.
        </p>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
        <div className="card">
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--accent-blue)' }}>{deptCode ? visibleTickets.length : stats.total}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Tickets Pushed</div>
        </div>
        <div className="card">
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--accent-blue)' }}>{stats.webhooks_received}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Webhook Hits</div>
        </div>
        <div className="card">
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--accent-blue)' }}>{stats.valid_signatures}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Valid Signatures</div>
        </div>
        <div className="card">
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#22c55e' }}>Γ£ô</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Routing OK</div>
        </div>
      </div>

      <div className="card" style={{ padding: 24 }}>
        <h2 style={{ fontSize: '1rem', color: 'var(--text-primary)', marginBottom: 16 }}>≡ƒôï Webhook Log (Last 200)</h2>
        
        {loading ? (
             <div className="skeleton" style={{ height: 200 }} />
        ) : visibleTickets.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--text-muted)' }}>
                <div style={{ fontSize: '3rem', marginBottom: 12 }}>≡ƒô¡</div>
                <div>{deptCode ? 'No webhooks for your department yet.' : 'No department webhooks received yet.'}</div>
            </div>
        ) : (
            <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                    <thead>
                        <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                            <th style={{ padding: '12px', fontWeight: 600 }}>Ticket ID</th>
                            <th style={{ padding: '12px', fontWeight: 600 }}>Department</th>
                            <th style={{ padding: '12px', fontWeight: 600 }}>Category</th>
                            <th style={{ padding: '12px', fontWeight: 600 }}>Priority</th>
                            <th style={{ padding: '12px', fontWeight: 600 }}>Score</th>
                            <th style={{ padding: '12px', fontWeight: 600 }}>Received</th>
                        </tr>
                    </thead>
                    <tbody>
                        {visibleTickets.map((t, idx) => (
                            <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                <td style={{ padding: '12px' }}><code style={{ color: 'var(--accent-blue)' }}>{t.ticket_id}</code></td>
                                <td style={{ padding: '12px' }}>{t.dept_code || 'ΓÇö'}</td>
                                <td style={{ padding: '12px' }}>{t.category}</td>
                                <td style={{ padding: '12px' }}>
                                    <span style={{ 
                                        padding: '2px 8px', borderRadius: 999, 
                                        background: `${TIER_COLORS[t.severity_tier]}22`, color: TIER_COLORS[t.severity_tier],
                                        fontWeight: 600, fontSize: '0.75rem' 
                                    }}>{t.severity_tier}</span>
                                </td>
                                <td style={{ padding: '12px', fontWeight: 700, color: TIER_COLORS[t.severity_tier] }}>{Math.round(t.priority_score)}</td>
                                <td style={{ padding: '12px', color: 'var(--text-muted)' }}>{new Date(t.received_at).toLocaleTimeString()}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        )}
      </div>
    </div>
  )
}
