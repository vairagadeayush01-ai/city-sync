import React, { useState, useEffect, createContext, useContext } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useNavigate, Navigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Shield, Map, Search, AlertCircle, Heart, CheckCircle2, Sun, Moon, User, LogOut, ShieldCheck, Lock, BarChart3, ShieldAlert, Sparkles, Building2, Landmark, Users, FileText, MapPin, ClipboardCheck, BarChart, Activity, Clock, TrendingUp } from 'lucide-react'
import CitizenPortal from './components/CitizenPortal'
import OfficerMap from './components/OfficerMap'
import AdminDashboard from './components/AdminDashboard'
import DeptPortal from './components/DeptPortal'
import StatusTimeline from './components/StatusTimeline'
import VerificationPanel from './components/VerificationPanel'
import LoginPage from './components/LoginPage'
import { useSocket } from './hooks/useSocket'
import { getMe, updateMe } from './utils/api'

// ── Theme Context ──────────────────────────────────────────────────────────────
const ThemeContext = createContext()

export function useTheme() {
  return useContext(ThemeContext)
}

function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('citysync_theme')
    if (saved) return saved
    return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('citysync_theme', theme)
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.content = theme === 'dark' ? '#060a12' : '#f8fafc'
  }, [theme])

  const toggleTheme = () => setTheme(prev => prev === 'dark' ? 'light' : 'dark')

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

// ── Toast Notifications ────────────────────────────────────────────────────────
function Toast({ message, type = 'info', onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 5000)
    return () => clearTimeout(t)
  }, [onClose])

  const icons = {
    info: <AlertCircle size={18} />,
    success: <CheckCircle2 size={18} color="var(--tier-low)" />,
    error: <AlertCircle size={18} color="var(--tier-critical)" />,
    warning: <AlertCircle size={18} color="var(--tier-high)" />
  }

  return (
    <motion.div
      initial={{ x: 100, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 100, opacity: 0 }}
      className={`toast toast-${type}`}
    >
      <span className="flex-center" style={{ width: 24, flexShrink: 0 }}>{icons[type]}</span>
      <div style={{ flex: 1, fontSize: '0.85rem', fontWeight: 500 }}>{message}</div>
      <button className="btn btn-ghost btn-sm" onClick={onClose} style={{ padding: 4 }}>✕</button>
    </motion.div>
  )
}

function ToastContainer({ toasts, removeToast }) {
  return (
    <div className="toast-container">
      <AnimatePresence>
        {toasts.map(t => <Toast key={t.id} {...t} onClose={() => removeToast(t.id)} />)}
      </AnimatePresence>
    </div>
  )
}

// ── User Components ───────────────────────────────────────────────────────────

function ProfileModal({ user, isOpen, onClose, onUpdate, onAddToast }) {
  const [name, setName] = useState(user?.name || '')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (user && isOpen) setName(user.name)
  }, [user, isOpen])

  if (!isOpen) return null

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await updateMe({ name, password: password || undefined })
      onUpdate()
      onAddToast({ message: 'Profile updated successfully!', type: 'success' })
      onClose()
      setPassword('')
    } catch (err) {
      onAddToast({ message: 'Update failed: ' + (err.response?.data?.detail || 'Unknown error'), type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex-center" style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(8px)' }}>
      <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="card" style={{ width: 420, padding: 32 }}>
        <div className="flex justify-between items-center mb-24">
          <h3 className="m-0">User Profile</h3>
          <button className="btn btn-ghost" onClick={onClose} style={{ padding: 4 }}>✕</button>
        </div>
        
        <form onSubmit={handleSubmit} className="flex-col gap-20">
          <div className="form-group">
            <label className="form-label">Full Name</label>
            <div className="relative">
              <User size={16} className="absolute left-3 top-3.5 text-muted" />
              <input className="input pl-10" value={name} onChange={e => setName(e.target.value)} required placeholder="Full Name" />
            </div>
          </div>
          
          <div className="form-group">
            <label className="form-label">Username</label>
            <div className="relative">
              <ShieldCheck size={16} className="absolute left-3 top-3.5 text-muted" />
              <input className="input pl-10" value={user?.username} disabled style={{ opacity: 0.6, cursor: 'not-allowed' }} />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">New Password</label>
            <div className="relative">
              <Lock size={16} className="absolute left-3 top-3.5 text-muted" />
              <input 
                className="input pl-10" 
                type="password" 
                placeholder="••••••••" 
                value={password} 
                onChange={e => setPassword(e.target.value)} 
              />
            </div>
            <p className="text-xs text-muted mt-4">Leave empty to keep existing password</p>
          </div>

          <div className="flex gap-12 mt-12">
            <button type="button" className="btn btn-outline flex-1" onClick={onClose}>Discard</button>
            <button type="submit" className="btn btn-primary flex-1" disabled={loading}>
              {loading ? 'Saving...' : 'Update Details'}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  )
}

function Nav({ user, onLogout, onOpenProfile }) {
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const [isMenuOpen, setIsMenuOpen] = useState(false)

  // Close menu when clicking outside
  useEffect(() => {
    if (!isMenuOpen) return
    const closeMenu = () => setIsMenuOpen(false)
    document.addEventListener('click', closeMenu)
    return () => document.removeEventListener('click', closeMenu)
  }, [isMenuOpen])

  return (
    <nav className="nav">
      <div className="nav-inner">
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          {user ? (
            <div className="relative">
              <motion.button 
                whileHover={{ scale: 1.05 }}
                className="nav-logo-icon" 
                onClick={(e) => {
                  e.stopPropagation()
                  if (onOpenProfile && user.role !== 'public') {
                      setIsMenuOpen(!isMenuOpen)
                  } else {
                      setIsMenuOpen(!isMenuOpen)
                  }
                }}
                style={{ cursor: 'pointer', background: 'var(--grad-accent)', border: 'none', borderRadius: 'var(--radius-md)' }}
              >
                <User size={18} color="#fff" />
              </motion.button>
              
              <AnimatePresence>
                {isMenuOpen && (
                  <motion.div 
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 10 }}
                    className="absolute top-12 left-0 pt-3" 
                    style={{ zIndex: 2005 }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="card card-sm flex-col gap-8 shadow-neon" style={{ minWidth: 200, padding: 16 }}>
                      <div className="text-xs font-bold uppercase opacity-60">Account</div>
                      <div className="text-sm font-bold truncate" style={{ color: 'var(--text-heading)' }}>{user.name}</div>
                      <div className="text-xs text-muted">@{user.username}</div>
                      <div className="badge badge-pending text-xs mt-4" style={{ alignSelf: 'flex-start' }}>{user.role}</div>
                      <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '12px 0' }} />
                      <button className="nav-link p-0 text-left flex items-center gap-8" style={{ color: 'var(--tier-critical)' }} onClick={() => { setIsMenuOpen(false); onLogout(); }}>
                         <LogOut size={14} /> Sign Out
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ) : (
            <motion.button 
              whileHover={{ scale: 1.05 }}
              className="nav-logo-icon" 
              onClick={() => navigate('/login')} 
              style={{ cursor: 'pointer', opacity: 0.8, border: 'none', background: 'var(--bg-elevated)' }}
            >
               <User size={18} color="var(--text-muted)" />
            </motion.button>
          )}

          <NavLink to="/" className="nav-logo" style={{ textDecoration: 'none' }}>
            <span style={{ letterSpacing: '-0.02em', fontWeight: 800 }}>
              CITY<span style={{ color: 'var(--neon-blue)' }}>SYNC</span>
            </span>
          </NavLink>
        </div>

        <div className="nav-links">
          {user?.role === 'citizen' && (
            <>
              <NavLink to="/" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} end>Home</NavLink>
              <NavLink to="/report" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Submit Issue</NavLink>
              <NavLink to="/track" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Track</NavLink>
            </>
          )}
          {user?.role === 'officer' && (
            <>
              <NavLink to="/" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} end>Home</NavLink>
              <NavLink to="/officer" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                <Map size={18} /> Officer Map
              </NavLink>
              <NavLink to="/department" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                <BarChart3 size={18} /> Department
              </NavLink>
            </>
          )}
          {user?.role === 'admin' && (
            <>
              <NavLink to="/" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} end>Home</NavLink>
              <NavLink to="/officer" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                <Map size={18} /> Map
              </NavLink>
              <NavLink to="/admin" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                <ShieldAlert size={18} /> Dashboard
              </NavLink>
            </>
          )}
          {!user && (
            <>
              <NavLink to="/" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} end>Discovery</NavLink>
              <NavLink to="/track" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Track</NavLink>
            </>
          )}
        </div>

        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9, rotate: 180 }}
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label="Toggle Theme"
          >
            {theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}
          </motion.button>
          
          {!user && (
            <button className="btn btn-primary btn-sm" onClick={() => navigate('/login')}>
              Join Platform
            </button>
          )}
        </div>
      </div>
    </nav>
  )
}

// ── Role-Based Home Pages ──────────────────────────────────────────────────────

function CitizenHomePage({ user, onAddToast }) {
  return (
    <div>
      <section className="hero" style={{ paddingTop: 80, paddingBottom: 60 }}>
        <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="hero-eyebrow">
          <span className="status-dot live" style={{ background: 'var(--neon-blue)' }} />
          WELCOME BACK, {user.name.toUpperCase()}
        </motion.div>

        <motion.h1 initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1, duration: 0.6 }} className="hero-title">
          Your City, <span className="highlight">Your Voice.</span>
        </motion.h1>

        <motion.p initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.25 }} className="hero-subtitle">
          Report civic issues, track their progress in real-time, and verify when they're resolved. Every report makes a difference.
        </motion.p>

        <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ delay: 0.35 }} className="hero-actions">
          <NavLink to="/report" className="btn btn-primary btn-lg animate-glow">🚨 Report New Issue</NavLink>
          <NavLink to="/track" className="btn btn-outline btn-lg">📍 Track My Tickets</NavLink>
        </motion.div>
      </section>

      <section style={{ padding: '60px 24px' }}>
        <div className="container" style={{ display: 'flex', gap: 20, overflowX: 'auto', paddingBottom: 20 }}>
          {[
            { icon: <FileText size={22} color="var(--neon-blue)" />, title: 'Submit Issues', desc: 'Report problems with photo & location' },
            { icon: <MapPin size={22} color="var(--neon-purple)" />, title: 'Real-time Tracking', desc: 'Follow your ticket status live' },
            { icon: <ClipboardCheck size={22} color="var(--accent-teal)" />, title: 'Verify Fixes', desc: 'Confirm when issues are resolved' },
            { icon: <Heart size={22} color="var(--neon-pink)" />, title: 'Civic Impact', desc: 'Make your community better' },
          ].map((item, idx) => (
            <motion.div key={idx} initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.1 }} className="card card-sm flex items-center gap-16" style={{ minWidth: 240 }}>
              <div className="flex-center" style={{ width: 42, height: 42, borderRadius: 12, background: 'var(--bg-elevated)' }}>{item.icon}</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.88rem' }}>{item.title}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{item.desc}</div>
              </div>
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  )
}

function OfficerHomePage({ user, onAddToast }) {
  return (
    <div>
      <section className="hero" style={{ paddingTop: 80, paddingBottom: 60 }}>
        <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="hero-eyebrow">
          <span className="status-dot live" style={{ background: 'var(--tier-high)' }} />
          OFFICER CONSOLE — {user.dept_code || 'ALL DEPARTMENTS'}
        </motion.div>

        <motion.h1 initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1, duration: 0.6 }} className="hero-title">
          Welcome, <span className="highlight">Officer {user.name.split(' ')[0]}.</span>
        </motion.h1>

        <motion.p initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.25 }} className="hero-subtitle">
          Manage and dispatch department tickets. View issues on the map, assign field workers, and mark items resolved.
        </motion.p>

        <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ delay: 0.35 }} className="hero-actions">
          <NavLink to="/officer" className="btn btn-primary btn-lg animate-glow" style={{ background: 'linear-gradient(135deg, #f59e0b, #ef4444)' }}>🗺️ Open Map Dashboard</NavLink>
          <NavLink to="/department" className="btn btn-outline btn-lg">📊 Department Portal</NavLink>
        </motion.div>
      </section>

      <section style={{ padding: '60px 24px' }}>
        <div className="container" style={{ display: 'flex', gap: 20, overflowX: 'auto', paddingBottom: 20 }}>
          {[
            { icon: <Map size={22} color="var(--tier-high)" />, title: 'Map View', desc: 'Geo-located issue clusters' },
            { icon: <Users size={22} color="var(--neon-blue)" />, title: 'Dispatch Workers', desc: 'Assign field teams to tickets' },
            { icon: <CheckCircle2 size={22} color="var(--tier-low)" />, title: 'Mark Resolved', desc: 'Update ticket status & close' },
            { icon: <Activity size={22} color="var(--neon-purple)" />, title: 'Dept Metrics', desc: 'Track your department KPIs' },
          ].map((item, idx) => (
            <motion.div key={idx} initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.1 }} className="card card-sm flex items-center gap-16" style={{ minWidth: 240 }}>
              <div className="flex-center" style={{ width: 42, height: 42, borderRadius: 12, background: 'var(--bg-elevated)' }}>{item.icon}</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.88rem' }}>{item.title}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{item.desc}</div>
              </div>
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  )
}

function AdminHomePage({ user, onAddToast }) {
  return (
    <div>
      <section className="hero" style={{ paddingTop: 80, paddingBottom: 60 }}>
        <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="hero-eyebrow">
          <span className="status-dot live" style={{ background: 'var(--neon-purple)' }} />
          SYSTEM ADMINISTRATOR
        </motion.div>

        <motion.h1 initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1, duration: 0.6 }} className="hero-title">
          Admin <span className="highlight">Command Center.</span>
        </motion.h1>

        <motion.p initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.25 }} className="hero-subtitle">
          Full platform oversight — monitor all departments, view real-time metrics, manage users, and oversee the AI pipeline.
        </motion.p>

        <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ delay: 0.35 }} className="hero-actions">
          <NavLink to="/admin" className="btn btn-primary btn-lg animate-glow" style={{ background: 'linear-gradient(135deg, #8b5cf6, #ec4899)' }}>⚡ Open Dashboard</NavLink>
          <NavLink to="/officer" className="btn btn-outline btn-lg">🗺️ Full Map View</NavLink>
        </motion.div>
      </section>

      <section style={{ padding: '60px 24px' }}>
        <div className="container" style={{ display: 'flex', gap: 20, overflowX: 'auto', paddingBottom: 20 }}>
          {[
            { icon: <BarChart size={22} color="var(--neon-purple)" />, title: 'Live Metrics', desc: 'Gateway, AI, routing stats' },
            { icon: <Shield size={22} color="var(--neon-blue)" />, title: 'Full Access', desc: 'All departments, all tickets' },
            { icon: <TrendingUp size={22} color="var(--tier-low)" />, title: 'AI Pipeline', desc: 'Monitor classification accuracy' },
            { icon: <Clock size={22} color="var(--tier-high)" />, title: 'Real-time Feed', desc: 'Webhook logs & event stream' },
          ].map((item, idx) => (
            <motion.div key={idx} initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.1 }} className="card card-sm flex items-center gap-16" style={{ minWidth: 240 }}>
              <div className="flex-center" style={{ width: 42, height: 42, borderRadius: 12, background: 'var(--bg-elevated)' }}>{item.icon}</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.88rem' }}>{item.title}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{item.desc}</div>
              </div>
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  )
}

function PublicHomePage({ onAddToast }) {
  return (
    <div>
      <section className="hero" style={{ paddingTop: 80, paddingBottom: 60 }}>
        <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="hero-eyebrow">
          <span className="status-dot live" style={{ background: 'var(--neon-blue)' }} />
          LIVE CITY MONITORING
        </motion.div>

        <motion.h1 initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1, duration: 0.6 }} className="hero-title">
          Better Cities, <span className="highlight">Together.</span>
        </motion.h1>

        <motion.p initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.25 }} className="hero-subtitle">
          See a problem? Snap a photo and we'll fix it. CitySync automatically sends your report to the right people.
        </motion.p>

        <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ delay: 0.35 }} className="hero-actions">
          <NavLink to="/login" className="btn btn-primary btn-lg animate-glow">🚀 Get Started</NavLink>
          <a href="#how" className="btn btn-outline btn-lg">How It Works</a>
        </motion.div>
      </section>

      <section id="how" style={{ padding: '60px 24px' }}>
        <div className="container" style={{ display: 'flex', gap: 20, overflowX: 'auto', paddingBottom: 20 }}>
          {[
            { icon: <Shield size={22} color="var(--neon-blue)" />, title: 'Identity Secret', desc: 'Secure & Anonymous' },
            { icon: <Map size={22} color="var(--neon-purple)" />, title: 'Smart Routing', desc: 'Directly to Officials' },
            { icon: <Search size={22} color="var(--accent-teal)" />, title: 'Real-time Track', desc: 'Know when it\'s fixed' },
            { icon: <Heart size={22} color="var(--neon-pink)" />, title: 'Civic Love', desc: 'Built for our City' },
          ].map((item, idx) => (
            <motion.div key={idx} initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.1 }} className="card card-sm flex items-center gap-16" style={{ minWidth: 240 }}>
              <div className="flex-center" style={{ width: 42, height: 42, borderRadius: 12, background: 'var(--bg-elevated)' }}>{item.icon}</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.88rem' }}>{item.title}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{item.desc}</div>
              </div>
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  )
}

// ── Dynamic Home Page Router ───────────────────────────────────────────────────
function HomePage({ user, onAddToast }) {
  if (!user) return <PublicHomePage onAddToast={onAddToast} />
  if (user.role === 'citizen') return <CitizenHomePage user={user} onAddToast={onAddToast} />
  if (user.role === 'officer') return <OfficerHomePage user={user} onAddToast={onAddToast} />
  if (user.role === 'admin') return <AdminHomePage user={user} onAddToast={onAddToast} />
  return <PublicHomePage onAddToast={onAddToast} />
}

// ── Pages ──────────────────────────────────────────────────────────────────────
function TrackPage() {
  const [ticketId, setTicketId] = useState('')
  const [tracking, setTracking] = useState(null)
  const [ticketStatus, setTicketStatus] = useState(null)

  const handleTrack = () => {
    const id = ticketId.trim().toUpperCase()
    if (id) setTracking(id)
  }

  return (
    <div className="container" style={{ padding: '80px 24px' }}>
      <h2 className="mb-8">Track Your Ticket</h2>
      <p className="mb-32">Enter your ticket ID to see what's happening.</p>

      <div style={{ display: 'flex', gap: 12, maxWidth: 500, marginBottom: 40 }}>
        <input className="input" placeholder="TKT-XXXXXX" value={ticketId} onChange={e => setTicketId(e.target.value.toUpperCase())} onKeyDown={e => e.key === 'Enter' && ticketId.trim() && handleTrack()} style={{ fontSize: '1.1rem', fontWeight: 700, letterSpacing: '0.05em' }} />
        <button className="btn btn-primary" onClick={handleTrack} disabled={!ticketId.trim()}>Track</button>
      </div>

      <AnimatePresence>
        {tracking && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
            <div className="grid-2" style={{ gap: 24 }}>
              <div className="card"><StatusTimeline ticketId={tracking} onStatusChange={setTicketStatus} /></div>
              <div className="card"><VerificationPanel ticketId={tracking} mode="citizen" currentStatus={ticketStatus} /></div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Protected Route Helper ─────────────────────────────────────────────────────
function RequireAuth({ user, roles, children }) {
  if (!user) return <Navigate to="/login" replace />
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />
  return children
}

// ── Root App ───────────────────────────────────────────────────────────────────
export default function App() {
  const [toasts, setToasts] = useState([])
  const [user, setUser] = useState(null)
  const [isProfileOpen, setIsProfileOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  let tCounter = 0

  const addToast = ({ message, type = 'info' }) => {
    const id = ++tCounter
    setToasts(prev => [...prev, { id, message, type }])
  }
  const removeToast = (id) => setToasts(prev => prev.filter(t => t.id !== id))

  const fetchUser = async () => {
    const token = localStorage.getItem('token')
    if (!token) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      const data = await getMe()
      setUser(data)
    } catch (err) {
      setUser(null)
      localStorage.removeItem('token')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchUser()
  }, [])

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('role')
    setUser(null)
    window.location.href = '/'
  }

  const { lastEvent } = useSocket()
  useEffect(() => {
    if (!lastEvent) return
    if (lastEvent.type === 'priority.boost') {
      addToast({ message: `⚡ High Priority! Ticket ${lastEvent.data.ticket_id}`, type: 'warning' })
    } else if (lastEvent.type === 'resolution.confirmed') {
      addToast({ message: `✅ Issue Solved! ${lastEvent.data.ticket_id}`, type: 'success' })
    }
  }, [lastEvent])

  if (loading) return <div className="flex-center h-screen"><div className="spinner" style={{width: 40, height: 40}} /></div>

  return (
    <ThemeProvider>
      <BrowserRouter>
        <div className="app-layout">
          <Nav user={user} onLogout={handleLogout} onOpenProfile={() => setIsProfileOpen(true)} />
          <main className="page-content">
            <Routes>
              <Route path="/" element={<HomePage user={user} onAddToast={addToast} />} />
              <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
              <Route path="/track" element={<TrackPage />} />
              <Route path="/report" element={
                <RequireAuth user={user} roles={['citizen', 'admin']}>
                  <CitizenPortal onAddToast={addToast} />
                </RequireAuth>
              } />
              <Route path="/officer" element={
                <RequireAuth user={user} roles={['officer', 'admin']}>
                  <div className="container" style={{ padding: '40px 24px' }}><OfficerMap /></div>
                </RequireAuth>
              } />
              <Route path="/department" element={
                <RequireAuth user={user} roles={['officer', 'admin']}>
                  <DeptPortal />
                </RequireAuth>
              } />
              <Route path="/admin" element={
                <RequireAuth user={user} roles={['admin']}>
                  <div className="container" style={{ padding: '40px 24px' }}><AdminDashboard /></div>
                </RequireAuth>
              } />
            </Routes>
          </main>
        </div>
        <ToastContainer toasts={toasts} removeToast={removeToast} />
        <ProfileModal user={user} isOpen={isProfileOpen} onClose={() => setIsProfileOpen(false)} onUpdate={fetchUser} onAddToast={addToast} />
      </BrowserRouter>
    </ThemeProvider>
  )
}
