import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Check, Clock, Truck, ShieldCheck, HelpCircle } from 'lucide-react'
import { getTicket } from '../utils/api'

const STATUS_CONFIG = {
  'Submitted': { icon: <Clock size={16}/>, color: 'var(--text-muted)', label: 'Received' },
  'Processing': { icon: <Clock size={16}/>, color: 'var(--accent-blue)', label: 'Analyzing' },
  'Pending': { icon: <ShieldCheck size={16}/>, color: 'var(--accent-blue)', label: 'AI Classified' },
  'In Progress': { icon: <Truck size={16}/>, color: 'var(--accent-cyan)', label: 'In Transit' },
  'Work Complete': { icon: <Clock size={16}/>, color: 'var(--tier-high)', label: 'Working on it' },
  'Solved': { icon: <Check size={16}/>, color: 'var(--tier-low)', label: 'Solved!' },
  'Resolved': { icon: <Check size={16}/>, color: 'var(--tier-low)', label: 'Confirmed' },
  'Rejected': { icon: <HelpCircle size={16}/>, color: 'var(--tier-critical)', label: 'Needs Info' },
}

const STEPS = ['Submitted', 'Processing', 'Pending', 'In Progress', 'Solved', 'Resolved']

export default function StatusTimeline({ ticketId, onStatusChange, isFresh = false }) {
  const [ticket, setTicket] = useState(null)
  const [loading, setLoading] = useState(true)
  const [retryCount, setRetryCount] = useState(0)

  useEffect(() => {
    let interval
    const fetchStatus = async () => {
      try {
        const resp = await getTicket(ticketId)
        setTicket(resp.data)
        if (onStatusChange) onStatusChange(resp.data.status)
        setRetryCount(0)
        setLoading(false)
      } catch (err) {
        if (err.response?.status === 404) {
          setRetryCount(prev => prev + 1)
        }
        // If it's not a fresh report or we've retried a lot, stop loading
        if (!isFresh || retryCount > 5) {
          setLoading(false)
        }
      }
    }

    fetchStatus()
    // Poll faster (3s) for fresh reports to catch them as they hit the DB
    interval = setInterval(fetchStatus, isFresh ? 3000 : 10000)
    return () => clearInterval(interval)
  }, [ticketId, isFresh, retryCount])

  if (loading) {
    return <div className="skeleton" style={{ height: 100, width: '100%' }} />
  }

  if (!ticket) {
    const isSyncing = isFresh && retryCount < 6
    return (
      <div className="card text-center" style={{ borderStyle: 'dashed', borderColor: isSyncing ? 'var(--accent-blue)' : 'var(--tier-critical)', padding: '24px' }}>
        <div className="flex-center mx-auto mb-16" style={{ 
          width: 48, height: 48, borderRadius: '50%', 
          background: isSyncing ? 'rgba(59,130,246,0.1)' : 'rgba(239,68,68,0.1)' 
        }}>
          {isSyncing ? (
            <div className="spinner" style={{ width: 24, height: 24, borderTopColor: 'var(--accent-blue)' }} />
          ) : (
            <HelpCircle size={24} color="var(--tier-critical)" />
          )}
        </div>
        <p style={{ margin: 0, fontWeight: 600 }}>
          {isSyncing ? 'Synchronizing with Database...' : `Ticket ${ticketId} not found.`}
        </p>
        <p className="text-sm mt-8 opacity-70">
          {isSyncing 
            ? 'Our AI is still processing your report. Tracking will start in a few seconds...' 
            : 'Please check the ticket ID and try again.'}
        </p>
      </div>
    )
  }

  const currentStatusIndex = STEPS.indexOf(ticket.status)

  return (
    <div className="status-timeline-container">
      <div className="flex justify-between items-center mb-24">
        <div>
          <div className="text-sm font-bold opacity-60">TICKET STATUS</div>
          <h3 className="m-0" style={{ color: STATUS_CONFIG[ticket.status]?.color }}>
            {STATUS_CONFIG[ticket.status]?.label || ticket.status}
          </h3>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="text-sm font-bold opacity-60 uppercase">Priority</div>
          <div style={{ color: ticket.priority_score > 70 ? 'var(--tier-critical)' : 'var(--tier-low)', fontWeight: 800 }}>
            {ticket.priority_score > 70 ? '⚡ HIGH' : 'NORMAL'}
          </div>
        </div>
      </div>

      <div className="timeline-horizontal" style={{ position: 'relative', display: 'flex', justifyContent: 'space-between', padding: '10px 0' }}>
        {/* Connection Line */}
        <div style={{ position: 'absolute', top: 22, left: 10, right: 10, height: 2, background: 'var(--bg-elevated)', zIndex: 0 }} />
        <motion.div 
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(0, currentStatusIndex) * (100 / (STEPS.length - 1))}%` }}
          style={{ position: 'absolute', top: 22, left: 10, height: 2, background: 'var(--grad-accent)', zIndex: 1 }} 
        />

        {STEPS.map((step, idx) => {
          const isDone = idx < currentStatusIndex || ['Solved', 'Resolved', 'Work Complete'].includes(ticket.status)
          const isActive = idx === currentStatusIndex && !['Solved', 'Resolved', 'Work Complete'].includes(ticket.status)
          const config = STATUS_CONFIG[step] || { icon: <Check size={16}/>, color: 'var(--text-muted)', label: step }

          return (
            <div key={step} style={{ position: 'relative', zIndex: 2, display: 'flex', flexDirection: 'column', alignItems: 'center', width: 60 }}>
              <motion.div
                initial={false}
                animate={{ 
                  scale: isActive ? 1.2 : 1,
                  background: isDone || isActive ? 'var(--grad-accent)' : 'var(--bg-elevated)',
                  boxShadow: isActive ? 'var(--neon-glow)' : 'none'
                }}
                className={`flex-center ${isActive ? 'animate-glow' : ''}`}
                style={{ width: 28, height: 28, borderRadius: '50%', color: isDone || isActive ? '#fff' : 'var(--text-muted)', border: '2px solid var(--bg-base)' }}
              >
                {isDone ? <Check size={14} strokeWidth={3} /> : config.icon}
              </motion.div>
              <div 
                style={{ 
                  marginTop: 12, fontSize: '0.6rem', fontWeight: 800, textAlign: 'center', 
                  color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
                  textTransform: 'uppercase', letterSpacing: '0.05em'
                }}
              >
                {config.label}
              </div>
            </div>
          )
        })}
      </div>

      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{ marginTop: 32, padding: 16, background: 'rgba(59,130,246,0.05)', borderRadius: 12, border: '1px solid var(--border)' }}
      >
        <div className="flex gap-12 items-start">
          <div className="flex-center" style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--bg-elevated)' }}>
            🤖
          </div>
          <div>
            <div style={{ fontSize: '0.8rem', fontWeight: 700, marginBottom: 4 }}>Last Update</div>
            <p style={{ fontSize: '0.85rem', margin: 0 }}>
              {ticket.status === 'Submitted' ? 'We have received your report and are queuing it for AI analysis.' :
               ticket.status === 'Processing' ? 'Our AI is currently de-duplicating and classifying your report. This usually takes < 1s.' : 
               ticket.status === 'Pending' ? `Recognized as ${ticket.category}. Forwarding to the municipal team.` :
               ticket.status === 'In Progress' ? 'On its way! The team has been dispatched to the location.' :
               'Local team is resolving the issue. We\'ll notify you once it\'s done!'}
            </p>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
