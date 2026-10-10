import React, { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LogIn, UserPlus, Lock, User, Phone, Globe, Shield,
  ChevronLeft, Eye, EyeOff, Building2, Landmark, Users,
  ArrowRight, Sparkles, CheckCircle2, AlertCircle
} from 'lucide-react'
import { login, signup } from '../utils/api'

// ── Departments ─────────────────────────────────────────────────────────────
const DEPARTMENTS = [
  { code: 'ROADS',    label: 'Roads & Infrastructure',   icon: '🛣️' },
  { code: 'SWD',      label: 'Stormwater Drainage',      icon: '🌊' },
  { code: 'LIGHTS',   label: 'Street Lighting',          icon: '💡' },
  { code: 'SWM',      label: 'Solid Waste Management',   icon: '🗑️' },
  { code: 'HYD',      label: 'Water Supply',             icon: '💧' },
  { code: 'BLDG',     label: 'Building Hazards',         icon: '🏗️' },
  { code: 'FIRE',     label: 'Fire Department',          icon: '🔥' },
  { code: 'ELEC_EMG', label: 'Electricity / Emergency',  icon: '⚡' },
]

// ── Animated background particles ────────────────────────────────────────────
function FloatingParticles() {
  return (
    <div className="auth-particles">
      {[...Array(20)].map((_, i) => (
        <div
          key={i}
          className="auth-particle"
          style={{
            left: `${Math.random() * 100}%`,
            top: `${Math.random() * 100}%`,
            animationDelay: `${Math.random() * 8}s`,
            animationDuration: `${8 + Math.random() * 12}s`,
            width: `${2 + Math.random() * 4}px`,
            height: `${2 + Math.random() * 4}px`,
            opacity: 0.1 + Math.random() * 0.3,
          }}
        />
      ))}
    </div>
  )
}

// ── Role selector card ────────────────────────────────────────────────────────
function RoleCard({ role, icon: Icon, title, subtitle, gradient, selected, onClick }) {
  return (
    <motion.button
      whileHover={{ scale: 1.04, y: -4 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      className={`auth-role-card ${selected ? 'auth-role-card--active' : ''}`}
      style={{ '--card-gradient': gradient }}
    >
      <div className="auth-role-card__icon" style={{ background: gradient }}>
        <Icon size={24} color="#fff" />
      </div>
      <div className="auth-role-card__text">
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </div>
      <ArrowRight size={18} className="auth-role-card__arrow" />
    </motion.button>
  )
}

// ── Password input with toggle ────────────────────────────────────────────────
function PasswordInput({ value, onChange, placeholder = 'Password', id }) {
  const [show, setShow] = useState(false)
  return (
    <div className="auth-input-wrap">
      <Lock size={16} className="auth-input-icon" />
      <input
        id={id}
        type={show ? 'text' : 'password'}
        placeholder={placeholder}
        className="auth-input"
        value={value}
        onChange={onChange}
        required
        minLength={8}
        autoComplete="current-password"
      />
      <button
        type="button"
        className="auth-input-eye"
        onClick={() => setShow(v => !v)}
        tabIndex={-1}
        aria-label={show ? 'Hide password' : 'Show password'}
      >
        {show ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  )
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function AuthToast({ message, type, onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 4000)
    return () => clearTimeout(t)
  }, [onClose])

  return (
    <motion.div
      initial={{ y: -40, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: -40, opacity: 0 }}
      className={`auth-toast auth-toast--${type}`}
    >
      {type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
      <span>{message}</span>
    </motion.div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  CITIZEN AUTH
// ═══════════════════════════════════════════════════════════════════════════════
function CitizenAuth({ onBack, onSuccess }) {
  const [mode, setMode] = useState('login') // login | signup
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(null)
  const navigate = useNavigate()

  const [loginForm, setLoginForm] = useState({ username: '', password: '' })
  const [signupForm, setSignupForm] = useState({ name: '', phone: '', username: '', password: '' })

  const handleLogin = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await login(loginForm.username, loginForm.password)
      localStorage.setItem('token', res.access_token)
      localStorage.setItem('role', res.role)
      onSuccess?.()
      window.location.href = '/'
    } catch (err) {
      let msg = 'Invalid credentials'
      if (err.response?.data?.detail) {
        msg = Array.isArray(err.response.data.detail) ? err.response.data.detail.map(d => d.msg).join(', ') : err.response.data.detail
      }
      setToast({ message: msg, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const handleSignup = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await signup({ ...signupForm, role: 'citizen' })
      setToast({ message: 'Account created! Please sign in.', type: 'success' })
      setMode('login')
      setLoginForm({ username: signupForm.username, password: '' })
    } catch (err) {
      let msg = 'Registration failed'
      if (err.response?.data?.detail) {
        msg = Array.isArray(err.response.data.detail) ? err.response.data.detail.map(d => d.msg).join(', ') : err.response.data.detail
      }
      setToast({ message: msg, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 60 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -60 }}
      className="auth-panel"
    >
      <AnimatePresence>
        {toast && <AuthToast {...toast} onClose={() => setToast(null)} />}
      </AnimatePresence>

      <button className="auth-back-btn" onClick={onBack}>
        <ChevronLeft size={18} /> Back
      </button>

      <div className="auth-panel__header">
        <div className="auth-panel__badge" style={{ background: 'linear-gradient(135deg, #06b6d4, #3b82f6)' }}>
          <Users size={22} color="#fff" />
        </div>
        <h1>Citizen Portal</h1>
        <p>Report and track civic issues in your community</p>
      </div>

      <div className="auth-tab-bar">
        <button className={`auth-tab ${mode === 'login' ? 'auth-tab--active' : ''}`} onClick={() => setMode('login')}>
          <LogIn size={15} /> Sign In
        </button>
        <button className={`auth-tab ${mode === 'signup' ? 'auth-tab--active' : ''}`} onClick={() => setMode('signup')}>
          <UserPlus size={15} /> Sign Up
        </button>
      </div>

      <AnimatePresence mode="wait">
        {mode === 'login' ? (
          <motion.form
            key="citizen-login"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            onSubmit={handleLogin}
            className="auth-form-fields"
          >
            <div className="auth-input-wrap">
              <User size={16} className="auth-input-icon" />
              <input
                id="citizen-login-username"
                type="text"
                placeholder="Username"
                className="auth-input"
                value={loginForm.username}
                onChange={e => setLoginForm({ ...loginForm, username: e.target.value })}
                required
                autoComplete="username"
              />
            </div>
            <PasswordInput
              id="citizen-login-password"
              value={loginForm.password}
              onChange={e => setLoginForm({ ...loginForm, password: e.target.value })}
            />
            <button className="auth-submit-btn" type="submit" disabled={loading}>
              {loading ? <span className="auth-spinner" /> : <><LogIn size={16} /> Sign In</>}
            </button>
          </motion.form>
        ) : (
          <motion.form
            key="citizen-signup"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            onSubmit={handleSignup}
            className="auth-form-fields"
          >
            <div className="auth-input-wrap">
              <User size={16} className="auth-input-icon" />
              <input
                id="citizen-signup-name"
                type="text"
                placeholder="Full Name"
                className="auth-input"
                value={signupForm.name}
                onChange={e => setSignupForm({ ...signupForm, name: e.target.value })}
                required
              />
            </div>
            <div className="auth-input-wrap">
              <Phone size={16} className="auth-input-icon" />
              <input
                id="citizen-signup-phone"
                type="tel"
                placeholder="Phone Number"
                className="auth-input"
                value={signupForm.phone}
                onChange={e => setSignupForm({ ...signupForm, phone: e.target.value })}
                required
              />
            </div>
            <div className="auth-input-wrap">
              <Globe size={16} className="auth-input-icon" />
              <input
                id="citizen-signup-username"
                type="text"
                placeholder="Username"
                className="auth-input"
                value={signupForm.username}
                onChange={e => setSignupForm({ ...signupForm, username: e.target.value })}
                required
                minLength={3}
              />
            </div>
            <PasswordInput
              id="citizen-signup-password"
              value={signupForm.password}
              onChange={e => setSignupForm({ ...signupForm, password: e.target.value })}
              placeholder="Password (min 8 chars)"
            />
            <button className="auth-submit-btn" type="submit" disabled={loading}>
              {loading ? <span className="auth-spinner" /> : <><UserPlus size={16} /> Create Account</>}
            </button>
          </motion.form>
        )}
      </AnimatePresence>
    </motion.div>
  )
}


// ═══════════════════════════════════════════════════════════════════════════════
//  OFFICER AUTH
// ═══════════════════════════════════════════════════════════════════════════════
function OfficerAuth({ onBack, onSuccess }) {
  const [mode, setMode] = useState('login')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(null)
  const navigate = useNavigate()

  const [loginForm, setLoginForm] = useState({ username: '', password: '' })
  const [signupForm, setSignupForm] = useState({ name: '', phone: '', username: '', password: '', dept_code: '' })

  const handleLogin = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await login(loginForm.username, loginForm.password)
      localStorage.setItem('token', res.access_token)
      localStorage.setItem('role', res.role)
      onSuccess?.()
      window.location.href = '/officer'
    } catch (err) {
      let msg = 'Invalid credentials'
      if (err.response?.data?.detail) {
        msg = Array.isArray(err.response.data.detail) ? err.response.data.detail.map(d => d.msg).join(', ') : err.response.data.detail
      }
      setToast({ message: msg, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const handleSignup = async (e) => {
    e.preventDefault()
    if (!signupForm.dept_code) {
      setToast({ message: 'Please select your department', type: 'error' })
      return
    }
    setLoading(true)
    try {
      await signup({ ...signupForm, role: 'officer' })
      setToast({ message: 'Officer account created! Please sign in.', type: 'success' })
      setMode('login')
      setLoginForm({ username: signupForm.username, password: '' })
    } catch (err) {
      let msg = 'Registration failed'
      if (err.response?.data?.detail) {
        msg = Array.isArray(err.response.data.detail) ? err.response.data.detail.map(d => d.msg).join(', ') : err.response.data.detail
      }
      setToast({ message: msg, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 60 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -60 }}
      className="auth-panel"
    >
      <AnimatePresence>
        {toast && <AuthToast {...toast} onClose={() => setToast(null)} />}
      </AnimatePresence>

      <button className="auth-back-btn" onClick={onBack}>
        <ChevronLeft size={18} /> Back
      </button>

      <div className="auth-panel__header">
        <div className="auth-panel__badge" style={{ background: 'linear-gradient(135deg, #f59e0b, #ef4444)' }}>
          <Shield size={22} color="#fff" />
        </div>
        <h1>Officer Portal</h1>
        <p>Department-specific issue management & dispatch</p>
      </div>

      <div className="auth-tab-bar">
        <button className={`auth-tab ${mode === 'login' ? 'auth-tab--active' : ''}`} onClick={() => setMode('login')}>
          <LogIn size={15} /> Sign In
        </button>
        <button className={`auth-tab ${mode === 'signup' ? 'auth-tab--active' : ''}`} onClick={() => setMode('signup')}>
          <UserPlus size={15} /> Sign Up
        </button>
      </div>

      <AnimatePresence mode="wait">
        {mode === 'login' ? (
          <motion.form
            key="officer-login"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            onSubmit={handleLogin}
            className="auth-form-fields"
          >
            <div className="auth-input-wrap">
              <User size={16} className="auth-input-icon" />
              <input
                id="officer-login-username"
                type="text"
                placeholder="Username"
                className="auth-input"
                value={loginForm.username}
                onChange={e => setLoginForm({ ...loginForm, username: e.target.value })}
                required
              />
            </div>
            <PasswordInput
              id="officer-login-password"
              value={loginForm.password}
              onChange={e => setLoginForm({ ...loginForm, password: e.target.value })}
            />
            <button className="auth-submit-btn auth-submit-btn--officer" type="submit" disabled={loading}>
              {loading ? <span className="auth-spinner" /> : <><LogIn size={16} /> Sign In</>}
            </button>
          </motion.form>
        ) : (
          <motion.form
            key="officer-signup"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            onSubmit={handleSignup}
            className="auth-form-fields"
          >
            <div className="auth-input-wrap">
              <User size={16} className="auth-input-icon" />
              <input
                id="officer-signup-name"
                type="text"
                placeholder="Full Name"
                className="auth-input"
                value={signupForm.name}
                onChange={e => setSignupForm({ ...signupForm, name: e.target.value })}
                required
              />
            </div>
            <div className="auth-input-wrap">
              <Phone size={16} className="auth-input-icon" />
              <input
                id="officer-signup-phone"
                type="tel"
                placeholder="Phone Number"
                className="auth-input"
                value={signupForm.phone}
                onChange={e => setSignupForm({ ...signupForm, phone: e.target.value })}
                required
              />
            </div>
            <div className="auth-input-wrap">
              <Globe size={16} className="auth-input-icon" />
              <input
                id="officer-signup-username"
                type="text"
                placeholder="Username"
                className="auth-input"
                value={signupForm.username}
                onChange={e => setSignupForm({ ...signupForm, username: e.target.value })}
                required
                minLength={3}
              />
            </div>
            <PasswordInput
              id="officer-signup-password"
              value={signupForm.password}
              onChange={e => setSignupForm({ ...signupForm, password: e.target.value })}
              placeholder="Password (min 8 chars)"
            />

            {/* Department picker */}
            <div className="auth-dept-grid">
              {DEPARTMENTS.map(dept => (
                <button
                  key={dept.code}
                  type="button"
                  className={`auth-dept-chip ${signupForm.dept_code === dept.code ? 'auth-dept-chip--active' : ''}`}
                  onClick={() => setSignupForm({ ...signupForm, dept_code: dept.code })}
                >
                  <span>{dept.icon}</span>
                  <span>{dept.label}</span>
                </button>
              ))}
            </div>

            <button className="auth-submit-btn auth-submit-btn--officer" type="submit" disabled={loading}>
              {loading ? <span className="auth-spinner" /> : <><UserPlus size={16} /> Register as Officer</>}
            </button>
          </motion.form>
        )}
      </AnimatePresence>
    </motion.div>
  )
}


// ═══════════════════════════════════════════════════════════════════════════════
//  ADMIN AUTH
// ═══════════════════════════════════════════════════════════════════════════════
function AdminAuth({ onBack, onSuccess }) {
  const [mode, setMode] = useState('login')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(null)
  const navigate = useNavigate()

  const [loginForm, setLoginForm] = useState({ username: '', password: '' })
  const [signupForm, setSignupForm] = useState({ name: '', username: '', password: '' })

  const handleLogin = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await login(loginForm.username, loginForm.password)
      localStorage.setItem('token', res.access_token)
      localStorage.setItem('role', res.role)
      onSuccess?.()
      window.location.href = '/admin'
    } catch (err) {
      let msg = 'Invalid credentials'
      if (err.response?.data?.detail) {
        msg = Array.isArray(err.response.data.detail) ? err.response.data.detail.map(d => d.msg).join(', ') : err.response.data.detail
      }
      setToast({ message: msg, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const handleSignup = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await signup({ ...signupForm, role: 'admin', phone: '0000000000' })
      setToast({ message: 'Admin account created! Please sign in.', type: 'success' })
      setMode('login')
      setLoginForm({ username: signupForm.username, password: '' })
    } catch (err) {
      let msg = 'Registration failed'
      if (err.response?.data?.detail) {
        msg = Array.isArray(err.response.data.detail) ? err.response.data.detail.map(d => d.msg).join(', ') : err.response.data.detail
      }
      setToast({ message: msg, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 60 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -60 }}
      className="auth-panel"
    >
      <AnimatePresence>
        {toast && <AuthToast {...toast} onClose={() => setToast(null)} />}
      </AnimatePresence>

      <button className="auth-back-btn" onClick={onBack}>
        <ChevronLeft size={18} /> Back
      </button>

      <div className="auth-panel__header">
        <div className="auth-panel__badge" style={{ background: 'linear-gradient(135deg, #8b5cf6, #ec4899)' }}>
          <Landmark size={22} color="#fff" />
        </div>
        <h1>Admin Console</h1>
        <p>Full system overview and control</p>
      </div>

      <div className="auth-tab-bar">
        <button className={`auth-tab ${mode === 'login' ? 'auth-tab--active' : ''}`} onClick={() => setMode('login')}>
          <LogIn size={15} /> Sign In
        </button>
        <button className={`auth-tab ${mode === 'signup' ? 'auth-tab--active' : ''}`} onClick={() => setMode('signup')}>
          <UserPlus size={15} /> Sign Up
        </button>
      </div>

      <AnimatePresence mode="wait">
        {mode === 'login' ? (
          <motion.form
            key="admin-login"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            onSubmit={handleLogin}
            className="auth-form-fields"
          >
            <div className="auth-input-wrap">
              <User size={16} className="auth-input-icon" />
              <input
                id="admin-login-username"
                type="text"
                placeholder="Admin Username"
                className="auth-input"
                value={loginForm.username}
                onChange={e => setLoginForm({ ...loginForm, username: e.target.value })}
                required
              />
            </div>
            <PasswordInput
              id="admin-login-password"
              value={loginForm.password}
              onChange={e => setLoginForm({ ...loginForm, password: e.target.value })}
            />
            <button className="auth-submit-btn auth-submit-btn--admin" type="submit" disabled={loading}>
              {loading ? <span className="auth-spinner" /> : <><LogIn size={16} /> Sign In</>}
            </button>
          </motion.form>
        ) : (
          <motion.form
            key="admin-signup"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            onSubmit={handleSignup}
            className="auth-form-fields"
          >
            <div className="auth-input-wrap">
              <User size={16} className="auth-input-icon" />
              <input
                id="admin-signup-name"
                type="text"
                placeholder="Full Name"
                className="auth-input"
                value={signupForm.name}
                onChange={e => setSignupForm({ ...signupForm, name: e.target.value })}
                required
              />
            </div>
            <div className="auth-input-wrap">
              <Globe size={16} className="auth-input-icon" />
              <input
                id="admin-signup-username"
                type="text"
                placeholder="Username"
                className="auth-input"
                value={signupForm.username}
                onChange={e => setSignupForm({ ...signupForm, username: e.target.value })}
                required
                minLength={3}
              />
            </div>
            <PasswordInput
              id="admin-signup-password"
              value={signupForm.password}
              onChange={e => setSignupForm({ ...signupForm, password: e.target.value })}
              placeholder="Password (min 8 chars)"
            />
            <button className="auth-submit-btn auth-submit-btn--admin" type="submit" disabled={loading}>
              {loading ? <span className="auth-spinner" /> : <><UserPlus size={16} /> Register Admin</>}
            </button>
          </motion.form>
        )}
      </AnimatePresence>
    </motion.div>
  )
}


// ═══════════════════════════════════════════════════════════════════════════════
//  MAIN LOGIN PAGE
// ═══════════════════════════════════════════════════════════════════════════════
export default function LoginPage() {
  const [selectedRole, setSelectedRole] = useState(null) // null | citizen | officer | admin
  const navigate = useNavigate()

  return (
    <div className="auth-page">
      <FloatingParticles />

      <div className="auth-glass-container">
        <AnimatePresence mode="wait">
          {!selectedRole ? (
            <motion.div
              key="role-select"
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              className="auth-role-select"
            >
              <div className="auth-brand">
                <motion.div
                  animate={{ rotate: [0, 5, -5, 0] }}
                  transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
                  className="auth-brand__logo"
                >
                  <Sparkles size={28} color="#fff" />
                </motion.div>
                <h1 className="auth-brand__title">
                  CITY<span>SYNC</span>
                </h1>
                <p className="auth-brand__tagline">Smart Civic Intelligence Platform</p>
              </div>

              <h2 className="auth-choose-title">Choose your role</h2>

              <div className="auth-role-cards">
                <RoleCard
                  role="citizen"
                  icon={Users}
                  title="Citizen"
                  subtitle="Report issues, track progress, verify fixes"
                  gradient="linear-gradient(135deg, #06b6d4, #3b82f6)"
                  selected={false}
                  onClick={() => setSelectedRole('citizen')}
                />
                <RoleCard
                  role="officer"
                  icon={Shield}
                  title="Officer"
                  subtitle="Department dispatch, map view, field ops"
                  gradient="linear-gradient(135deg, #f59e0b, #ef4444)"
                  selected={false}
                  onClick={() => setSelectedRole('officer')}
                />
                <RoleCard
                  role="admin"
                  icon={Landmark}
                  title="Admin"
                  subtitle="Full system dashboard & controls"
                  gradient="linear-gradient(135deg, #8b5cf6, #ec4899)"
                  selected={false}
                  onClick={() => setSelectedRole('admin')}
                />
              </div>

              <button
                className="auth-home-link"
                onClick={() => navigate('/')}
              >
                <ChevronLeft size={14} /> Return to Home Page
              </button>
            </motion.div>
          ) : selectedRole === 'citizen' ? (
            <CitizenAuth key="citizen" onBack={() => setSelectedRole(null)} />
          ) : selectedRole === 'officer' ? (
            <OfficerAuth key="officer" onBack={() => setSelectedRole(null)} />
          ) : (
            <AdminAuth key="admin" onBack={() => setSelectedRole(null)} />
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
