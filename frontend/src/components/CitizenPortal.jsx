import React, { useState, useCallback, useRef, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import { Camera, MapPin, Send, Mic, ArrowLeft, CheckCircle, AlertCircle, X, Copy, ExternalLink, Sparkles } from 'lucide-react'
import { submitComplaint, getHistory } from '../utils/api'
import StatusTimeline from './StatusTimeline'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const CATEGORIES = [
  { value: 'Pothole',         icon: '🕳️', desc: 'Broken road surface' },
  { value: 'Flooding',        icon: '🌊', desc: 'Water accumulation' },
  { value: 'Drainage',        icon: '🚰', desc: 'Blocked sewage' },
  { value: 'Street Light',    icon: '💡', desc: 'Lights not working' },
  { value: 'Garbage',         icon: '🗑️', desc: 'Waste buildup' },
  { value: 'Water Supply',    icon: '💧', desc: 'No water/Leakage' },
  { value: 'Live Wire',       icon: '⚡', desc: 'Electrical hazard' },
  { value: 'Other',           icon: '📋', desc: 'Anything else' },
]

function imageToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result.split(',')[1])
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

async function getImageHash(base64) {
  const bytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0))
  const hash = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, '0')).join('')
}

export default function CitizenPortal({ onSubmitted, onAddToast }) {
  const [viewMode, setViewMode] = useState('submit') // 'submit' | 'history'
  const [wizardStep, setWizardStep] = useState(0) // 0: Category, 1: Media, 2: Details
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const [category, setCategory] = useState('')
  const [description, setDescription] = useState('')
  const [imageFile, setImageFile] = useState(null)
  const [imagePreview, setImagePreview] = useState(null)
  const [gpsCoords, setGpsCoords] = useState(null)
  const [isListening, setIsListening] = useState(false)
  const [useMap, setUseMap] = useState(false)

  // ── Handlers ───────────────────────────────────────────────────────────────
  const captureGPS = () => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      (pos) => setGpsCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      (err) => console.error(err)
    )
  }

  const startVoiceInput = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      alert('Voice recognition not supported in this browser.')
      return
    }
    const recognition = new SpeechRecognition()
    recognition.lang = 'en-US'
    recognition.onstart = () => setIsListening(true)
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript
      setDescription(prev => (prev ? prev + ' ' + transcript : transcript))
    }
    recognition.onend = () => setIsListening(false)
    recognition.start()
  }

  const { getRootProps, getInputProps } = useDropzone({
    onDrop: (files) => {
      const file = files[0]
      if (file) {
        setImageFile(file)
        setImagePreview(URL.createObjectURL(file))
        setWizardStep(2) // Auto-advance to details after photo
      }
    },
    accept: { 'image/*': ['.jpg', '.jpeg', '.png'] },
    maxFiles: 1
  })

  const handleFinalSubmit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      // If a manual category is selected, prefix it. Otherwise let AI resolve from pure description.
      const finalDescription = category ? `${category}: ${description}` : description
      const payload = {
        description: finalDescription,
        latitude: gpsCoords?.lat || null,
        longitude: gpsCoords?.lng || null,
      }
      if (imageFile) {
        const b64 = await imageToBase64(imageFile)
        payload.image_base64 = b64
        payload.sha256_hash = await getImageHash(b64)
      }
      const resp = await submitComplaint(payload)
      const { message, ticket_id, status } = resp.data

      // Detect duplicates or closed tickets based on message/status
      if (message && (message.includes('boosted') || message.includes('📈'))) {
        onAddToast({ message: `📈 Similar issue found nearby! Boosted priority for TKT-${ticket_id}.`, type: 'info' })
      } else if (status === 'Resolved' || status === 'Solved') {
        onAddToast({ message: `💡 This was recently solved. If it's back, please wait 24h.`, type: 'info' })
      } else {
        onAddToast({ message: `✅ Reported! Ticket ID: ${ticket_id}`, type: 'success' })
      }

      setResult(resp.data)
      onSubmitted?.(resp.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  // ── Render Helpers ──────────────────────────────────────────────────────────
  const nextStep = () => setWizardStep(prev => prev + 1)
  const prevStep = () => setWizardStep(prev => prev - 1)

  if (result) {
    return (
      <motion.div 
        initial={{ opacity: 0, y: 20 }} 
        animate={{ opacity: 1, y: 0 }} 
        className="flex-col gap-24"
      >
        <div className="card text-center" style={{ padding: '32px 24px', background: 'var(--grad-hero)', border: 'none' }}>
          <div className="flex-center mx-auto mb-16" style={{ width: 64, height: 64, borderRadius: '50%', background: 'var(--tier-low)', color: 'white' }}>
            <CheckCircle size={32} />
          </div>
          <h2 className="mb-4" style={{ color: 'white' }}>Report Received!</h2>
          <p style={{ color: 'rgba(255,255,255,0.8)', fontSize: '0.9rem' }}>
            Your issue has been logged and sent to the municipal team.
          </p>
        </div>

        <div className="flex-col gap-12">
          <div className="flex justify-between items-center px-8">
            <span className="text-xs font-bold opacity-60 uppercase">Ticket Token</span>
            <span className="text-xs font-bold opacity-60 uppercase">Live Tracking</span>
          </div>
          <div className="card card-sm bg-surface flex justify-between items-center">
            <code className="text-accent font-bold" style={{ fontSize: '1.2rem' }}>{result.ticket_id}</code>
            <button 
              className="btn btn-ghost btn-sm" 
              onClick={() => {
                navigator.clipboard.writeText(result.ticket_id)
                alert('Ticket ID copied to clipboard!')
              }}
            >
              <Copy size={16} className="mr-4" /> Copy
            </button>
          </div>
        </div>

        <div className="card bg-elevated">
          <StatusTimeline ticketId={result.ticket_id} isFresh={true} />
        </div>

        <div className="flex gap-12 mt-8">
          <button className="btn btn-primary btn-full" onClick={() => window.location.reload()}>
            New Report
          </button>
          <button className="btn btn-outline btn-full" onClick={() => window.location.href = '/track'}>
            <ExternalLink size={16} className="mr-8" /> Track All
          </button>
        </div>
      </motion.div>
    )
  }

  const variants = {
    center: { x: 0, opacity: 1 },
    exit: (direction) => ({ x: direction < 0 ? 300 : -300, opacity: 0 })
  }

  return (
    <div className="citizen-portal">
      {/* View Toggle */}
      <div className="flex gap-16 mb-24" style={{ borderBottom: '1px solid var(--border)', paddingBottom: 16 }}>
        <button 
          className={`btn ${viewMode === 'submit' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setViewMode('submit')}
        >
          Submit New Report
        </button>
        <button 
          className={`btn ${viewMode === 'history' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setViewMode('history')}
        >
          My History
        </button>
      </div>

      {viewMode === 'history' ? (
        <ReportHistory />
      ) : (
        <>
          {/* Progress Bar */}
          <div style={{ marginBottom: 32, height: 4, background: 'var(--bg-elevated)', borderRadius: 2 }}>
            <motion.div 
              animate={{ width: `${(wizardStep + 1) * 33.3}%` }} 
              style={{ height: '100%', background: 'var(--grad-accent)', borderRadius: 2 }} 
            />
          </div>

          <AnimatePresence mode="wait" custom={wizardStep}>
        {wizardStep === 0 && (
          <motion.div
            key="step0" custom={wizardStep} variants={variants} initial="enter" animate="center" exit="exit"
            className="flex-col gap-20"
          >
            <div className="text-center">
              <h2 className="mb-4">What's the issue?</h2>
              <p>Select a category that matches your problem.</p>
            </div>
            <div className="card card-glass mb-24 p-20 flex-col gap-12" style={{ border: description ? '1px solid var(--neon-blue)' : '1px solid var(--border)' }}>
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-8">
                  <Sparkles size={16} color="var(--neon-blue)" />
                  <span className="text-xs font-bold uppercase opacity-70">Describe issue directly</span>
                </div>
                {description.length > 5 && (
                  <motion.button 
                    initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                    className="btn btn-primary btn-sm" 
                    onClick={() => { if (!category) setCategory(''); nextStep(); }}
                  >
                    Continue <Send size={14} className="ml-4" />
                  </motion.button>
                )}
              </div>
              <textarea 
                className="textarea" 
                placeholder="e.g. My street's water line is leaking since morning..." 
                style={{ minHeight: 80, fontSize: '0.9rem', background: 'rgba(0,0,0,0.2)' }}
                value={description}
                onChange={e => setDescription(e.target.value)}
              />
            </div>

            <div className="flex-center mb-16 px-24">
              <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
              <div style={{ padding: '0 16px', fontSize: '0.7rem', fontWeight: 700, opacity: 0.5, textTransform: 'uppercase' }}>Or Select Category</div>
              <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            </div>

            <div className="grid-2" style={{ gap: 12 }}>
              {CATEGORIES.map(cat => (
                <button
                  key={cat.value}
                  className={`card card-sm flex-col items-center gap-8 ${category === cat.value ? 'animate-glow' : ''}`}
                  style={{ 
                    cursor: 'pointer', textAlign: 'center', 
                    border: category === cat.value ? '2px solid var(--neon-blue)' : '1px solid var(--border)' 
                  }}
                  onClick={() => { setCategory(cat.value); nextStep() }}
                >
                  <span style={{ fontSize: '2rem' }}>{cat.icon}</span>
                  <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>{cat.value}</div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{cat.desc}</div>
                </button>
              ))}
            </div>
          </motion.div>
        )}

        {wizardStep === 1 && (
          <motion.div
            key="step1" custom={wizardStep} variants={variants} initial="enter" animate="center" exit="exit"
            className="flex-col gap-20"
          >
            <div className="flex items-center gap-12 mb-4">
              <button onClick={prevStep} className="btn btn-ghost btn-sm p-0"><ArrowLeft size={20}/></button>
              <h2 className="m-0">Add a Photo</h2>
            </div>
            {imagePreview ? (
              <div className="relative">
                <img src={imagePreview} className="dropzone-preview" style={{ height: 350 }} />
                <button 
                  className="btn btn-danger btn-sm absolute top-8 right-8" 
                  onClick={() => { setImageFile(null); setImagePreview(null) }}
                >
                  <X size={16}/> Remove
                </button>
                <div className="mt-16 flex gap-12">
                  <button className="btn btn-primary btn-full" onClick={nextStep}>Looks Good</button>
                </div>
              </div>
            ) : (
              <div {...getRootProps()} className="dropzone animate-float" style={{ minHeight: 300, background: 'rgba(59,130,246,0.05)' }}>
                <input {...getInputProps()} />
                <Camera size={48} className="mb-16 text-muted" />
                <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>Tap to Take a Photo</div>
                <p className="text-sm">Or drag and drop here</p>
                <button className="btn btn-outline mt-16" onClick={nextStep}>Skip Photo</button>
              </div>
            )}
          </motion.div>
        )}

        {wizardStep === 2 && (
          <motion.div
            key="step2" custom={wizardStep} variants={variants} initial="enter" animate="center" exit="exit"
            className="flex-col gap-20"
          >
            <div className="flex items-center gap-12 mb-4">
              <button onClick={prevStep} className="btn btn-ghost btn-sm p-0"><ArrowLeft size={20}/></button>
              <h2 className="m-0">Final Details</h2>
            </div>

            <div className="form-group relative">
              <label className="form-label">Say or type a few words</label>
              <textarea
                className="textarea"
                placeholder="What exactly is the problem?"
                value={description}
                onChange={e => setDescription(e.target.value)}
                style={{ paddingRight: 48 }}
              />
              <button 
                type="button" 
                className={`absolute bottom-12 right-12 btn btn-sm ${isListening ? 'btn-danger' : 'btn-ghost'}`}
                onClick={startVoiceInput}
                title="Tap to speak"
              >
                <Mic size={20} className={isListening ? 'animate-pulse' : ''} />
              </button>
            </div>

            {/* Location section */}
            <div className="card card-sm bg-surface">
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-8">
                  <MapPin size={20} color={gpsCoords ? 'var(--tier-low)' : 'var(--text-muted)'} />
                  <span style={{ fontSize: '0.85rem' }}>
                    {gpsCoords ? 'Location captured ✓' : 'Add location for faster help'}
                  </span>
                </div>
                <div className="flex gap-8">
                  {!gpsCoords && (
                    <button className="btn btn-teal btn-sm" onClick={captureGPS}>GPS</button>
                  )}
                  <button 
                    className={`btn btn-sm ${useMap ? 'btn-primary' : 'btn-outline'}`} 
                    onClick={() => setUseMap(!useMap)}
                  >
                    {useMap ? 'Hide Map' : '🗺️ Pick on Map'}
                  </button>
                </div>
              </div>
              {gpsCoords && (
                <div style={{ marginTop: 8, fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                  📍 {gpsCoords.lat.toFixed(5)}, {gpsCoords.lng.toFixed(5)}
                </div>
              )}
            </div>

            {useMap && (
              <LocationPickerMap gpsCoords={gpsCoords} setGpsCoords={setGpsCoords} />
            )}

            {/* Privacy notice */}
            <div style={{
              background: 'rgba(59, 130, 246, 0.06)',
              border: '1px solid rgba(59, 130, 246, 0.15)',
              borderRadius: 'var(--radius-md)',
              padding: '12px 16px',
              fontSize: '0.78rem',
              color: 'var(--text-muted)',
            }}>
              🔒 <strong style={{ color: 'var(--text-secondary)' }}>Privacy Protected</strong>
              · Your identity is HMAC-hashed · GPS is ±30m fuzzed for officers · Photos are AES-256 encrypted · 90-day TTL
            </div>

            <button 
              className="btn btn-primary btn-lg mt-16 animate-glow" 
              onClick={handleFinalSubmit}
              disabled={submitting || !description.trim()}
            >
              {submitting ? 'Sending...' : 'Report Now 🚨'}
            </button>

            {error && <div className="text-center text-sm" style={{ color: 'var(--tier-critical)' }}>{error}</div>}
          </motion.div>
        )}
      </AnimatePresence>
        </>
      )}
    </div>
  )
}

// ── Report History Component ────────────────────────────────────────────────

function ReportHistory() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getHistory()
      .then(data => {
        setHistory(data.tickets)
      })
      .catch(err => console.error(err))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="flex-center p-24"><div className="spinner" /></div>

  if (history.length === 0) {
    return (
      <div className="card text-center text-muted p-32">
        <p>You haven't submitted any reports yet.</p>
      </div>
    )
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex-col gap-16">
      {history.map(t => (
        <div key={t.ticket_id} className="card flex-col gap-12" style={{ padding: '16px 20px' }}>
          <div className="flex justify-between items-start">
            <div>
              <span className="text-xs font-bold opacity-60 uppercase">TICKET ID</span>
              <div className="font-mono text-accent" style={{ fontSize: '1.1rem' }}>{t.ticket_id}</div>
            </div>
            <div className="badge flex items-center gap-4 py-4 px-8 rounded-full" style={{
              background: t.status === 'Resolved' || t.status === 'Solved' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
              color: t.status === 'Resolved' || t.status === 'Solved' ? '#10B981' : '#EF4444'
            }}>
              {t.status === 'Resolved' || t.status === 'Solved' ? <CheckCircle size={14}/> : <AlertCircle size={14}/>}
              {t.status}
            </div>
          </div>
          
          <div>
            <div className="font-bold text-lg mb-4">{t.category}</div>
            <div className="text-sm opacity-80" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
              {t.description}
            </div>
          </div>
          
          <div className="flex justify-between items-center mt-8 text-xs opacity-60">
            <span>Submitted: {new Date(t.submitted_at).toLocaleDateString()}</span>
            {t.updated_at && <span>Last updated: {new Date(t.updated_at).toLocaleDateString()}</span>}
          </div>
        </div>
      ))}
    </motion.div>
  )
}

// ── Location Picker Map Component ────────────────────────────────────────────
function LocationPickerMap({ gpsCoords, setGpsCoords }) {
  const mapContainerRef = useRef(null)
  const mapRef = useRef(null)
  const markerRef = useRef(null)

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return

    const defaultCenter = gpsCoords ? [gpsCoords.lat, gpsCoords.lng] : [19.0760, 72.8777]

    const map = L.map(mapContainerRef.current, {
      zoomControl: true,
      attributionControl: false
    }).setView(defaultCenter, gpsCoords ? 15 : 11)

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19
    }).addTo(map)

    // If we already have coords, place a marker
    if (gpsCoords) {
      const icon = L.divIcon({
        className: 'custom-icon',
        html: '<div style="width:20px;height:20px;border-radius:50%;background:rgba(99,102,241,0.4);border:3px solid #6366f1;box-shadow:0 0 12px rgba(99,102,241,0.6);"></div>',
        iconSize: [20, 20],
        iconAnchor: [10, 10]
      })
      markerRef.current = L.marker([gpsCoords.lat, gpsCoords.lng], { icon }).addTo(map)
    }

    // Click to set location
    map.on('click', (e) => {
      const { lat, lng } = e.latlng
      setGpsCoords({ lat, lng })

      const icon = L.divIcon({
        className: 'custom-icon',
        html: '<div style="width:20px;height:20px;border-radius:50%;background:rgba(99,102,241,0.4);border:3px solid #6366f1;box-shadow:0 0 12px rgba(99,102,241,0.6);"></div>',
        iconSize: [20, 20],
        iconAnchor: [10, 10]
      })

      if (markerRef.current) {
        markerRef.current.setLatLng([lat, lng])
      } else {
        markerRef.current = L.marker([lat, lng], { icon }).addTo(map)
      }
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
      markerRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Update marker when gpsCoords change externally (e.g. from "Use My Current Location")
  useEffect(() => {
    if (!mapRef.current || !gpsCoords) return

    const icon = L.divIcon({
      className: 'custom-icon',
      html: '<div style="width:20px;height:20px;border-radius:50%;background:rgba(99,102,241,0.4);border:3px solid #6366f1;box-shadow:0 0 12px rgba(99,102,241,0.6);"></div>',
      iconSize: [20, 20],
      iconAnchor: [10, 10]
    })

    if (markerRef.current) {
      markerRef.current.setLatLng([gpsCoords.lat, gpsCoords.lng])
    } else {
      markerRef.current = L.marker([gpsCoords.lat, gpsCoords.lng], { icon }).addTo(mapRef.current)
    }

    mapRef.current.flyTo([gpsCoords.lat, gpsCoords.lng], 15, { duration: 1 })
  }, [gpsCoords])

  return (
    <div
      ref={mapContainerRef}
      style={{
        width: '100%',
        height: 280,
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--border)',
        overflow: 'hidden',
      }}
    />
  )
}
