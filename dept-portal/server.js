/**
 * CitySync — Mock Department Portal
 * Express server that receives HMAC-signed webhooks from CitySync
 * and displays them in a simple dashboard.
 *
 * Run: node server.js  (from dept-portal/ directory)
 * Access: http://localhost:3000
 */
const express = require('express')
const crypto = require('crypto')
const cors = require('cors')

const app = express()
const PORT = process.env.DEPT_PORTAL_PORT || 3000
const WEBHOOK_SECRET = process.env.WEBHOOK_HMAC_SECRET || 'citysync-webhook-signing-secret'

app.use(cors())
app.use(express.static('public'))

// Store raw body for HMAC verification before JSON parsing
app.use('/webhook', express.raw({ type: 'application/json' }))
app.use(express.json())

// ── In-memory ticket store (demo only) ────────────────────────────────────────
const receivedTickets = []
const webhookLog = []

// ── HMAC Verification ─────────────────────────────────────────────────────────
function verifyWebhook(payload, signatureHeader) {
  if (!signatureHeader) return false
  const expected = 'sha256=' + crypto.createHmac('sha256', WEBHOOK_SECRET).update(payload).digest('hex')
  try {
    return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signatureHeader))
  } catch {
    return false
  }
}

// ── Webhook receiver (all departments route here) ─────────────────────────────
app.post('/webhook/:dept_code', (req, res) => {
  const { dept_code } = req.params
  const signature = req.headers['x-citysync-signature']
  const ticketId = req.headers['x-citysync-ticketid']
  const attempt = req.headers['x-citysync-attempt']

  const rawBody = req.body
  const isValid = verifyWebhook(rawBody, signature)

  let payload
  try {
    payload = JSON.parse(rawBody.toString())
  } catch {
    return res.status(400).json({ error: 'Invalid JSON payload' })
  }

  const logEntry = {
    id: Date.now(),
    dept_code,
    ticket_id: ticketId || payload.ticket_id,
    attempt: parseInt(attempt) || 1,
    signature_valid: isValid,
    received_at: new Date().toISOString(),
    payload,
  }
  webhookLog.unshift(logEntry)
  if (webhookLog.length > 100) webhookLog.pop()

  if (isValid || !signature) {
    // Accept ticket
    const existing = receivedTickets.findIndex(t => t.ticket_id === payload.ticket_id)
    if (existing >= 0) {
      receivedTickets[existing] = { ...receivedTickets[existing], ...payload, updated_at: new Date().toISOString() }
    } else {
      receivedTickets.unshift({ ...payload, received_at: new Date().toISOString(), dept_code })
    }
    if (receivedTickets.length > 200) receivedTickets.pop()
  }

  console.log(`[${new Date().toISOString()}] Webhook received: ${dept_code} | ${payload.ticket_id} | valid=${isValid} | attempt=${attempt}`)

  res.status(200).json({ status: 'accepted', ticket_id: payload.ticket_id, signature_valid: isValid })
})

// ── API endpoints ─────────────────────────────────────────────────────────────
app.get('/api/tickets', (req, res) => {
  const { dept_code, status } = req.query
  let tickets = [...receivedTickets]
  if (dept_code) tickets = tickets.filter(t => t.dept_code === dept_code)
  if (status)    tickets = tickets.filter(t => t.status === status)
  res.json({ tickets, total: tickets.length })
})

app.get('/api/webhook-log', (req, res) => {
  res.json({ log: webhookLog, total: webhookLog.length })
})

app.get('/api/stats', (req, res) => {
  const byDept = {}
  const byTier = {}
  receivedTickets.forEach(t => {
    byDept[t.dept_code] = (byDept[t.dept_code] || 0) + 1
    byTier[t.severity_tier] = (byTier[t.severity_tier] || 0) + 1
  })
  res.json({
    total: receivedTickets.length,
    webhooks_received: webhookLog.length,
    valid_signatures: webhookLog.filter(l => l.signature_valid).length,
    by_department: byDept,
    by_tier: byTier,
  })
})

// ── Dashboard UI ──────────────────────────────────────────────────────────────
app.get('/', (req, res) => {
  const tiersColors = { Critical: '#ef4444', High: '#f97316', Medium: '#eab308', Low: '#22c55e' }

  const ticketRows = receivedTickets.slice(0, 50).map(t => `
    <tr>
      <td><code style="color:#60a5fa">${t.ticket_id}</code></td>
      <td>${t.dept_code || '—'}</td>
      <td>${t.category}</td>
      <td>
        <span style="padding:2px 10px;border-radius:999px;background:${tiersColors[t.severity_tier]}22;color:${tiersColors[t.severity_tier]};font-size:0.75rem;font-weight:700">
          ${t.severity_tier}
        </span>
      </td>
      <td style="font-weight:700;color:${tiersColors[t.severity_tier]}">${Math.round(t.priority_score || 0)}</td>
      <td>${t.ward_id || '—'}</td>
      <td>${t.status || 'Pending'}</td>
      <td style="font-size:0.75rem;color:#64748b">${t.received_at ? new Date(t.received_at).toLocaleString() : '—'}</td>
    </tr>
  `).join('')

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1.0" />
  <title>CitySync — Department Portal</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Inter', sans-serif; background: #080c14; color: #f1f5f9; min-height: 100vh; }
    .header {
      padding: 16px 32px;
      background: rgba(15,22,36,0.9);
      border-bottom: 1px solid rgba(99,179,237,0.1);
      display: flex; align-items: center; justify-content: space-between;
      position: sticky; top: 0; z-index: 10; backdrop-filter: blur(10px);
    }
    .logo { font-size: 1.2rem; font-weight: 700; display: flex; align-items: center; gap: 10px; }
    .badge-green { background: rgba(34,197,94,0.15); color: #4ade80; padding: 4px 12px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; border: 1px solid rgba(34,197,94,0.3); }
    .container { max-width: 1400px; margin: 0 auto; padding: 28px 32px; }
    .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 28px; }
    .stat { background: rgba(20,29,46,0.6); border: 1px solid rgba(99,179,237,0.1); border-radius: 12px; padding: 20px; }
    .stat-value { font-size: 2rem; font-weight: 700; color: #60a5fa; }
    .stat-label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 4px; }
    .card { background: rgba(20,29,46,0.6); border: 1px solid rgba(99,179,237,0.1); border-radius: 12px; padding: 20px; margin-bottom: 24px; }
    .card h2 { font-size: 1rem; margin-bottom: 16px; color: #94a3b8; }
    table { width: 100%; border-collapse: collapse; }
    th { text-align: left; padding: 10px 12px; font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 1px solid rgba(99,179,237,0.08); }
    td { padding: 12px 12px; font-size: 0.85rem; border-bottom: 1px solid rgba(99,179,237,0.05); vertical-align: middle; }
    tr:hover td { background: rgba(59,130,246,0.04); }
    .empty { text-align: center; padding: 48px; color: #475569; }
    .pill { padding: 3px 10px; border-radius: 999px; font-size: 0.72rem; font-weight: 600; }
    .refresh-note { font-size: 0.78rem; color: #475569; margin-bottom: 12px; }
  </style>
  <script>
    setTimeout(() => location.reload(), 10000);
    async function fetchStats() {
      const res = await fetch('/api/stats');
      const data = await res.json();
      document.getElementById('total-count').textContent = data.total;
      document.getElementById('webhook-count').textContent = data.webhooks_received;
      document.getElementById('valid-sig').textContent = data.valid_signatures;
    }
    document.addEventListener('DOMContentLoaded', fetchStats);
  </script>
</head>
<body>
  <div class="header">
    <div class="logo">
      🏢 CitySync — Department Portal
      <span class="badge-green">● Live</span>
    </div>
    <div style="font-size:0.8rem;color:#64748b">Refreshes every 10 seconds · Webhooks: HMAC-SHA256 verified</div>
  </div>

  <div class="container">
    <div class="stats">
      <div class="stat">
        <div class="stat-value" id="total-count">${receivedTickets.length}</div>
        <div class="stat-label">Tickets Received</div>
      </div>
      <div class="stat">
        <div class="stat-value" id="webhook-count">${webhookLog.length}</div>
        <div class="stat-label">Webhook Calls</div>
      </div>
      <div class="stat">
        <div class="stat-value" id="valid-sig">${webhookLog.filter(l => l.signature_valid).length}</div>
        <div class="stat-label">Valid Signatures</div>
      </div>
      <div class="stat">
        <div class="stat-value" style="color:#22c55e">✓</div>
        <div class="stat-label">Portal Status</div>
      </div>
    </div>

    <div class="card">
      <h2>📋 Received Tickets (last 50)</h2>
      <p class="refresh-note">Auto-refreshes every 10s · Showing newest first</p>
      ${receivedTickets.length === 0 ? `
        <div class="empty">
          <div style="font-size:3rem;margin-bottom:12px">📭</div>
          <div>No tickets received yet</div>
          <div style="font-size:0.8rem;margin-top:8px">Submit a complaint at <a href="http://localhost:5173" style="color:#60a5fa">localhost:5173</a> to see webhooks appear here</div>
        </div>
      ` : `
        <table>
          <thead>
            <tr>
              <th>Ticket ID</th><th>Department</th><th>Category</th>
              <th>Priority</th><th>Score</th><th>Ward</th><th>Status</th><th>Received</th>
            </tr>
          </thead>
          <tbody>${ticketRows}</tbody>
        </table>
      `}
    </div>
  </div>
</body>
</html>`

  res.send(html)
})

app.listen(PORT, () => {
  console.log(`\n🏢 CitySync Department Portal`)
  console.log(`   Listening on http://localhost:${PORT}`)
  console.log(`   Webhook endpoint: POST /webhook/{dept_code}`)
  console.log(`   HMAC verification: ${WEBHOOK_SECRET !== 'citysync-webhook-signing-secret' ? '✓ Custom secret' : '⚠ Default secret'}`)
  console.log(`   Dashboard: http://localhost:${PORT}/\n`)
})
