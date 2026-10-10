import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
})

// Inject bearer token from localStorage
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Auto-refresh token from response (gateway issues fresh tokens on certain actions)
api.interceptors.response.use((response) => {
  const newToken = response.data?.bearer_token
  if (newToken) localStorage.setItem('token', newToken)
  return response
})

const VERIFY_URL = import.meta.env.VITE_VERIFY_URL || 'http://localhost:8002'

export const verifyApi = axios.create({
  baseURL: VERIFY_URL,
  timeout: 15000,
})

// Inject bearer token from localStorage for Verification API
verifyApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── Auth APIs ────────────────────────────────────────────────────────────────
export const login  = (username, password) => api.post('/api/auth/login', { username, password }).then(r => r.data)
export const signup = (payload)            => api.post('/api/auth/signup', payload).then(r => r.data)
export const getMe  = ()                   => api.get('/api/auth/me').then(r => r.data)
export const updateMe = (payload)          => api.put('/api/auth/me', payload).then(r => r.data)

// ── Complaint APIs ─────────────────────────────────────────────────────────────
export const submitComplaint = (payload) => api.post('/api/submit', payload)
export const getTicket       = (ticketId) => api.get(`/api/tickets/${ticketId}`)
export const getHistory      = () => api.get('/api/tickets/history').then(r => r.data)
export const listTickets     = (params)   => api.get('/api/tickets', { params })
export const upvoteTicket    = (ticketId) => api.post(`/api/upvote?ticket_id=${ticketId}`)

// ── Verification APIs ──────────────────────────────────────────────────────────
export const getVerificationStatus = (ticketId) => verifyApi.get(`/api/verify/${ticketId}`)
export const submitStep2           = (payload)  => verifyApi.post('/api/verify/step2', payload)

// ── Assignment APIs ─────────────────────────────────────────────────────────────
export const assignTicket          = (ticketId, payload) => api.post(`/api/tickets/${ticketId}/assign`, payload)
export const markTicketSolved      = (ticketId) => api.post(`/api/tickets/${ticketId}/resolve`)

// ── Metrics APIs ───────────────────────────────────────────────────────────────
export const getMetrics     = () => api.get('/api/stats/gateway')
export const getLeaderboard = () => api.get('/api/frequency/leaderboard')
export const getRoutingMetrics = () =>
  axios.get(`${import.meta.env.VITE_ROUTING_URL || 'http://localhost:8001'}/api/routing/metrics`, { timeout: 5000 }).catch(() => ({ data: {} }))
export const getVerifyMetrics = () =>
  axios.get(`${import.meta.env.VITE_VERIFY_URL || 'http://localhost:8002'}/api/verify/metrics`, { timeout: 5000 }).catch(() => ({ data: {} }))

// ── Demo ───────────────────────────────────────────────────────────────────────
export const getDemoTokens = () => api.get('/api/demo-tokens')

export default api
