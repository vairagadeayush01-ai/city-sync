import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, AlertTriangle, ThumbsUp, ThumbsDown, Camera, X } from 'lucide-react'
import { submitStep2, getTicket } from '../utils/api'

export default function VerificationPanel({ ticketId, mode = 'citizen', currentStatus }) {
  const [step, setStep] = useState('idle') // idle | submitting | done | error
  const [result, setResult] = useState(null)
  const [response, setResponse] = useState('YES')
  const [photo, setPhoto] = useState(null)
  const [photoPreview, setPhotoPreview] = useState(null)
  const [ticketStatus, setTicketStatus] = useState(currentStatus || null)
  const [error, setError] = useState(null)

  // Poll ticket status to know when to show the verification form
  useEffect(() => {
    if (!ticketId) return
    if (currentStatus) { setTicketStatus(currentStatus); return }
    const fetchStatus = async () => {
      try {
        const res = await getTicket(ticketId)
        setTicketStatus(res.data?.status || null)
      } catch (_) {}
    }
    fetchStatus()
    const interval = setInterval(fetchStatus, 8000)
    return () => clearInterval(interval)
  }, [ticketId, currentStatus])

  const handlePhotoChange = (e) => {
    const file = e.target.files[0]
    if (file) {
      setPhoto(file)
      setPhotoPreview(URL.createObjectURL(file))
    }
  }

  const handleCitizenSubmit = async () => {
    setStep('submitting')
    setError(null)
    try {
      let photoBase64 = null
      if (photo && response === 'PHOTO') {
        const reader = new FileReader()
        photoBase64 = await new Promise((res, rej) => {
          reader.onload = () => res(reader.result.split(',')[1])
          reader.onerror = rej
          reader.readAsDataURL(photo)
        })
      }

      const apiRes = await submitStep2({
        ticket_id: ticketId,
        citizen_response: response === 'PHOTO' ? 'NO' : response,
        photo_base64: photoBase64,
        role: mode,
        timestamp: new Date().toISOString()
      })
      setResult(apiRes.data)
      setStep('done')
    } catch (err) {
      if (err.response?.data?.detail) {
        setError(err.response.data.detail)
      } else {
        setError('Connection error. Please try again.')
      }
      setStep('error')
    }
  }

  const isWorkComplete = ticketStatus === 'Work Complete' || ticketStatus === 'Solved'
  const isResolved = ticketStatus === 'Resolved'
  const isClosed = ticketStatus === 'Resolved' || ticketStatus === 'Rejected'

  // Completed / closed state
  if (step === 'done' || isClosed) {
    return (
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card" style={{ textAlign: 'center', padding: 32 }}>
        <CheckCircle size={48} color="var(--tier-low)" style={{ margin: '0 auto 12px' }} />
        <h3 style={{ color: isResolved ? 'var(--tier-low)' : 'var(--accent-blue)', marginBottom: 8 }}>
          {isResolved || step === 'done' ? 'Verification Submitted!' : 'Issue Reopened'}
        </h3>
        <p className="text-sm">Thank you for helping keep the city clean!</p>
        {result?.resolution_method && (
          <div style={{
            marginTop: 16, padding: '8px 16px',
            background: 'rgba(34,197,94,0.1)',
            border: '1px solid rgba(34,197,94,0.3)',
            borderRadius: 'var(--radius-md)',
            fontSize: '0.8rem', color: 'var(--tier-low)',
          }}>
            Resolution: {result.resolution_method} · Ticket closed
          </div>
        )}
      </motion.div>
    )
  }

  // Only show citizen verification when field team has marked it complete
  if (mode === 'citizen') {
    if (ticketStatus === 'Resolved') {
      return (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card" style={{ textAlign: 'center', padding: 24 }}>
          <CheckCircle size={40} color="var(--tier-low)" style={{ margin: '0 auto 8px' }} />
          <h3 style={{ color: 'var(--tier-low)', marginBottom: 4 }}>Issue Resolved</h3>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>This complaint has been resolved and closed.</p>
        </motion.div>
      )
    }

    if (!isWorkComplete) {
      // Status-aware waiting messages
      const statusMessages = {
        'Pending':       { icon: '📥', msg: 'Your complaint has been received and is in the queue.' },
        'Processing':    { icon: '🤖', msg: 'AI is classifying your complaint and routing it to the right department.' },
        'In Progress':   { icon: '🔧', msg: 'A field team is working on the issue. You\'ll be notified when work is complete.' },
        'Human Review':  { icon: '👁', msg: 'Your complaint is under manual review by our team.' },
        'Rejected':      { icon: '❌', msg: 'This complaint was flagged as spam or duplicate.' },
        null:            { icon: '⏳', msg: 'Loading ticket status...' },
      }
      const { icon, msg } = statusMessages[ticketStatus] ?? { icon: '⏳', msg: 'Checking ticket status...' }
      return (
        <div className="card" style={{
          background: 'rgba(59,130,246,0.04)',
          border: '1px solid rgba(59,130,246,0.15)',
          padding: '20px 24px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: '1.8rem' }}>{icon}</span>
            <div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: 4 }}>
                Verification not yet available
              </div>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', margin: 0 }}>
                {msg}
              </p>
            </div>
          </div>
          {ticketStatus && ticketStatus !== 'Rejected' && ticketStatus !== 'Resolved' && (
            <div style={{ marginTop: 14, fontSize: '0.75rem', color: 'var(--text-muted)', paddingTop: 12, borderTop: '1px solid var(--border)' }}>
              ⏳ The <strong>Step 2 — Confirm Resolution</strong> form will appear here once the field team marks the work as complete.
            </div>
          )}
        </div>
      )
    }

    // Status is Work Complete — show the confirmation form
    return (
      <div className="card" style={{ border: '1px solid var(--accent-teal)', background: 'rgba(20, 184, 166, 0.03)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <div style={{ width: 40, height: 40, borderRadius: 12, background: 'var(--grad-teal)', boxShadow: 'var(--glow-teal)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <CheckCircle color="white" size={24} />
          </div>
          <div>
            <h4 style={{ margin: 0 }}>Step 2 — Confirm Resolution</h4>
            <p className="text-sm" style={{ margin: 0 }}>The field team has marked your complaint as complete. Please confirm.</p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
          {['YES', 'NO', 'PHOTO'].map(opt => (
            <button
              key={opt}
              className={`btn ${response === opt ? 'btn-primary' : 'btn-outline'} btn-full`}
              onClick={() => setResponse(opt)}
            >
              {opt === 'YES' ? <><ThumbsUp size={16} /> Yes, Fixed</> : opt === 'NO' ? <><ThumbsDown size={16} /> Not Fixed</> : <><Camera size={16} /> Send Photo</>}
            </button>
          ))}
        </div>

        {response === 'PHOTO' && (
          <div style={{ marginBottom: 20 }}>
            <label className="form-label" style={{ display: 'block', marginBottom: 8 }}>
              Upload a photo showing current state
            </label>
            <input type="file" accept="image/*" onChange={handlePhotoChange} className="input" style={{ padding: 8 }} />
            {photoPreview && (
              <img src={photoPreview} alt="preview" style={{ marginTop: 8, width: '100%', height: 150, objectFit: 'cover', borderRadius: 'var(--radius-md)' }} />
            )}
          </div>
        )}

        <div style={{
          padding: '10px 14px', background: 'rgba(59,130,246,0.06)',
          borderRadius: 'var(--radius-md)', fontSize: '0.78rem',
          color: 'var(--text-muted)', marginBottom: 16,
        }}>
          <AlertTriangle size={12} style={{ display: 'inline', marginRight: 4 }} />
          72-hour window · If no response, ticket auto-closes as "timeout"
        </div>

        <button
          className="btn btn-teal btn-full"
          disabled={step === 'submitting' || (response === 'PHOTO' && !photo)}
          onClick={handleCitizenSubmit}
        >
          {step === 'submitting' ? (
            <><div className="spinner" style={{ borderTopColor: '#fff' }} /> Submitting...</>
          ) : 'Submit Response'}
        </button>

        {error && (
          <div style={{ color: 'var(--tier-critical)', marginTop: 12, fontSize: '0.875rem', textAlign: 'center' }}>
            ✗ {error}
          </div>
        )}
      </div>
    )
  }

  // Fallback — officer/fieldworker quick-verify view
  return (
    <div className="card" style={{ border: '1px solid var(--accent-teal)', background: 'rgba(20, 184, 166, 0.03)' }}>
      <div className="flex gap-12 items-start mb-20">
        <div style={{ width: 40, height: 40, borderRadius: 12, background: 'var(--grad-teal)', boxShadow: 'var(--glow-teal)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <CheckCircle color="white" size={24} />
        </div>
        <div>
          <h4 style={{ margin: 0 }}>Is it fixed?</h4>
          <p className="text-sm" style={{ margin: 0 }}>Please tell us if you're happy with the resolution.</p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12 }}>
        {isWorkComplete ? (
          <>
            <button 
              className="btn btn-teal btn-full" 
              onClick={() => { setResponse('YES'); handleCitizenSubmit(); }}
              disabled={step === 'submitting'}
            >
              <ThumbsUp size={18} /> Yes, All Good!
            </button>
            <button 
              className="btn btn-outline btn-full" 
              onClick={() => { setResponse('NO'); handleCitizenSubmit(); }}
              disabled={step === 'submitting'}
              style={{ borderColor: 'var(--tier-critical)', color: 'var(--tier-critical)' }}
            >
              <ThumbsDown size={18} /> Not Fixed
            </button>
          </>
        ) : (
          <div className="w-full text-center p-12 card bg-surface text-sm opacity-70 border-dashed" style={{ borderColor: 'var(--border)' }}>
            Verification will unlock once the field team updates the status to <strong>Work Complete</strong>.
          </div>
        )}
      </div>

      {error && <div className="mt-12 text-center text-xs" style={{ color: 'var(--tier-critical)' }}>{error}</div>}
      
      <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
        <AlertTriangle size={12} style={{ display: 'inline', marginRight: 4 }} /> 
        Final confirmation is required before we can officially close this ticket.
      </div>
    </div>
  )
}
